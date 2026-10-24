"""The generator.

Every profile is a product of four factors, then capped and rescaled:

    P_m(t) = L_m * S(t) * M_m(t - tau_m) * R_m(t - tau_m)

where

    P_m(t)   demand for carrier m at hour t, kW
    L_m      level, set so the annual energy matches the spec exactly
    S(t)     calendar factor: month x hour of the week, mean one
    M_m(t)   on/off state, 1 when running and `off_level` when idle
    R_m(t)   residual fluctuation, lognormal AR(1) with mean one
    tau_m    carrier m's lag in hours

Why a product rather than a sum
-------------------------------
A multiplicative factor is dimensionless, so the same rhythm transfers between a
200 kW site and a 20 MW one without retuning. Additive noise does not: "plus or
minus 50 kW" means something different at each scale, and it can drive the load
negative. Every factor here is positive and has mean one, so the level `L_m`
alone sets the energy and nothing downstream can drift it.

The calendar is never shifted, and shared unless the spec gives a carrier one
of its own. A factory's opening hours are common to its carriers -- heat and
production refrigeration do not take the weekend off at different times -- so
only the *process fluctuation* carries a lag. Cold rooms that run through the
weekend are the exception a carrier's own calendar is for. The shift
wraps around the end of the year, so it only reorders the hours: lagging a
carrier leaves every one of its own statistics (load factor, spread,
persistence, annual energy) exactly unchanged. The lag therefore changes only
how the carriers relate to one another.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .classes import ProcessClass, get_class
from .spec import ALL_CARRIERS, CARRIERS, COLUMN_NAMES, DemandSpec

__all__ = ["generate", "build_profiles", "solve_correlation_knob",
           "carrier_load_factors", "matched_load_factor"]


# =============================================================================
# Primitives
# =============================================================================


def correlated_ar1(n: int, n_series: int, phi: float, sigma: float,
                   correlation: float, rng: np.random.Generator) -> np.ndarray:
    """`n_series` Gaussian AR(1) paths sharing a cross-series correlation.

    Each path follows ``z(t) = phi*z(t-1) + eps(t)`` with the innovations
    correlated across paths through a Cholesky factor. The innovation standard
    deviation carries a factor ``sqrt(1 - phi^2)``: an AR(1) driven by
    innovations of variance ``s^2`` settles at stationary variance
    ``s^2/(1 - phi^2)``, so this choice makes the stationary variance exactly
    ``sigma^2``. Starting the path from a draw of that stationary distribution
    then removes the burn-in entirely, which matters because at ``phi = 0.97``
    the burn-in would be several hundred hours of a year.
    """
    target = np.full((n_series, n_series), float(correlation))
    np.fill_diagonal(target, 1.0)
    # Nearest positive-definite nudge. With three series and |r| < 1 this is a
    # formality, but a correlation pushed to exactly 1 would fail Cholesky.
    eigenvalues, eigenvectors = np.linalg.eigh(target)
    eigenvalues = np.clip(eigenvalues, 1e-10, None)
    target = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
    scale = np.sqrt(np.diag(target))
    target = target / np.outer(scale, scale)
    chol = np.linalg.cholesky(target)

    innovation_sd = sigma * np.sqrt(1.0 - phi**2)
    shocks = (chol @ rng.standard_normal((n_series, n))) * innovation_sd

    z = np.empty((n_series, n), dtype=float)
    z[:, 0] = rng.standard_normal(n_series) * sigma
    for t in range(1, n):
        z[:, t] = phi * z[:, t - 1] + shocks[:, t]
    return z


def lognormal_from_latent(z: np.ndarray, sigma: float) -> np.ndarray:
    """Latent to a positive multiplicative factor of mean one.

    For ``z ~ N(0, sigma^2)`` the expectation of ``exp(z)`` is
    ``exp(sigma^2/2)``, which is above one and grows with the spread. Taking it
    out keeps ``E[R] = 1`` exactly, so widening the noise cannot inflate the
    annual energy.
    """
    return np.exp(z - 0.5 * sigma**2)


def onoff_from_latent(latent: np.ndarray, off_fraction: float,
                      off_level: float) -> np.ndarray:
    """Persistent, cross-correlated on/off masks from Gaussian latent series.

    Cutting a correlated Gaussian series at a threshold to make a binary one is
    called a Gaussian copula. The binary state inherits both the persistence of
    the latent series and its correlation with the other carriers, with no
    table of switching probabilities to fit. Cutting at the quantile measured
    on the series itself makes the off fraction exactly `off_fraction`.

    Giving every carrier the same mask would force their correlation to one,
    which is the artefact this package exists to avoid.
    """
    if off_fraction <= 0.0:
        return np.ones_like(latent)
    cut = np.quantile(latent, off_fraction, axis=-1, keepdims=True)
    return np.where(latent > cut, 1.0, float(off_level))


def cap_to_rated_capacity(profile: np.ndarray, target_load_factor: float,
                          max_iterations: int = 2000,
                          tolerance: float = 1e-12) -> np.ndarray:
    """Impose a rated capacity while preserving annual energy.

    A plant cannot draw more than it has installed, so its load duration curve
    has a hard ceiling; a lognormal tail has none. Capping lowers the mean,
    which lowers the cap, so cap and rescale are alternated:

        P~ = min(P, mean(P)/eta);   P <- P~ * E / sum(P~)

    The map is a contraction: each pass shrinks the excess over the cap by
    about the share of steps held at the cap. A shipped class holds 1-2 % of
    its hours there and converges in a few passes; a tight rating can hold a
    third of them, and needs a few dozen. It runs until the peak is within
    `tolerance` of the cap. At the fixed point the load factor is `eta` and the
    energy is `E`, both exactly. This is what makes the *extreme quantiles*
    right: the coefficient of variation can be correct while the top of the
    load duration curve is badly wrong.
    """
    if not 0.0 < target_load_factor < 1.0:
        return profile

    out = np.array(profile, dtype=float)
    energy = float(out.sum())
    if energy <= 0:
        return out
    for _ in range(max_iterations):
        mean = float(out.mean())
        if mean <= 0:
            break
        cap = mean / target_load_factor
        if out.max() <= cap * (1.0 + tolerance):
            break
        out = np.minimum(out, cap)
        total = float(out.sum())
        if total > 0:
            out *= energy / total
    return out


def residual_cv_for(target_cv: float, shape: np.ndarray) -> float:
    """Residual spread that lands the *finished* profile on `target_cv`.

    Shape and residual are independent with the residual at mean one, so

        1 + CV_total^2 = (1 + CV_shape^2) * (1 + CV_residual^2)

    Variances do not add here -- one plus the squared coefficient of variation
    multiplies. Fitting the residual directly on a measured series and then
    multiplying the calendar back in double-counts the calendar's own spread.
    """
    shape_mean = float(np.mean(shape))
    if shape_mean <= 0:
        return float(target_cv)
    shape_cv = float(np.std(shape) / shape_mean)
    ratio = (1.0 + target_cv**2) / (1.0 + shape_cv**2)
    return float(np.sqrt(max(ratio - 1.0, 1e-12)))


def step_hours(index: pd.DatetimeIndex) -> float:
    """Length of one step, in hours, inferred from the index.

    Everything resolution-dependent is derived from this rather than assumed,
    so the same spec can be rendered hourly or quarter-hourly.
    """
    if len(index) < 2:
        return 1.0
    # Through seconds rather than the raw integers: pandas 3 stores timestamps
    # at microsecond resolution by default, pandas 2 at nanosecond.
    deltas = np.asarray((index[1:] - index[:-1]).total_seconds())
    # Median rather than the first gap, so a daylight-saving seam or a single
    # missing step does not redefine the resolution.
    return float(np.median(deltas)) / 3600.0


def rescale_persistence(phi_hourly: float, hours_per_step: float) -> float:
    """Convert an hourly AR(1) coefficient to one for a step of another length.

    Persistence is a property of *time*, not of the sampling grid. An AR(1)
    autocorrelation decays as ``phi^k`` over k steps, so a series sampled every
    ``h`` hours must use

        phi_step = phi_hourly ** h

    to keep the same correlation at the same wall-clock separation. Without this
    a quarter-hourly profile would carry four times the memory in real time, and
    its excursions would last four times as long as the site it was calibrated
    on.
    """
    if not 0.0 < phi_hourly < 1.0:
        return float(np.clip(phi_hourly, 0.0, 0.995))
    return float(np.clip(phi_hourly ** float(hours_per_step), 0.0, 0.9995))


def _shift(values: np.ndarray, lag: int) -> np.ndarray:
    """Circularly shift a series forward by `lag` hours.

    Circular rather than truncating so the year stays complete and stationary.
    Because a circular shift is a permutation, every marginal statistic of the
    shifted series is identical to the unshifted one.
    """
    return values if lag == 0 else np.roll(values, lag)


# =============================================================================
# The generator
# =============================================================================


def _carrier_shapes(process: ProcessClass, spec: DemandSpec,
                    index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """The class's calendar, and each carrier's: its own where the spec gives one."""
    class_shape = process.calendar(index)
    shapes = np.vstack([spec.calendars[carrier].factors(index)
                        if carrier in spec.calendars else class_shape
                        for carrier in ALL_CARRIERS])
    return class_shape, shapes


def _stochastic_factors(process: ProcessClass, spec: DemandSpec,
                        index: pd.DatetimeIndex, knob: float,
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calendars, masks and residuals, before any lag is applied."""
    n = len(index)
    rng = np.random.default_rng(spec.seed)
    class_shape, shapes = _carrier_shapes(process, spec, index)
    phi = rescale_persistence(process.target_lag1, step_hours(index))

    # Two independent sets of correlated latents: one drives the on/off state,
    # the other the variation within a run. Both carry the cross-carrier
    # correlation, so no carrier is a copy of another.
    mask_latent = correlated_ar1(n, len(ALL_CARRIERS), phi, 1.0, knob, rng)
    masks = onoff_from_latent(mask_latent, process.off_fraction,
                              process.off_level)

    # The residual supplies only the spread the class's own calendar and mask
    # have not. It is set on the class's calendar even for a carrier given a
    # calendar of its own, so that carrier keeps the class's fluctuation within
    # its running hours.
    reference = class_shape * masks[0]
    cv = residual_cv_for(process.target_cv, reference)
    sigma = float(np.sqrt(np.log1p(cv**2)))
    residual_latent = correlated_ar1(n, len(ALL_CARRIERS), phi, sigma, knob, rng)
    residuals = lognormal_from_latent(residual_latent, sigma)
    return shapes, masks, residuals


_REFERENCE_YEAR = pd.date_range("2025-01-01", periods=8760, freq="h")


@lru_cache(maxsize=1024)
def _reference_uncapped(process: ProcessClass, calendar=None, seed: int = 0,
                        ) -> tuple[np.ndarray, bool]:
    """Uncapped hourly years of a class, one per carrier, and whether it has
    no fluctuation.

    On the class's calendar or another, drawn with a fixed seed and independent
    carriers, so whatever is derived from it depends on the class and the
    calendar alone. A class whose spread is no more than its calendar's and
    on/off state's own (the shipped `batch`) has no fluctuation left: its
    profile is a step function.
    """
    from .spec import DemandSpec as _Spec
    calendars = ({} if calendar is None
                 else {carrier: calendar for carrier in ALL_CARRIERS})
    probe = _Spec(process_class=process, seed=seed, calendars=calendars)
    shapes, masks, residuals = _stochastic_factors(process, probe,
                                                   _REFERENCE_YEAR, 0.0)
    no_fluctuation = bool(np.std(residuals[0]) < 1e-3)
    return shapes * masks * residuals, no_fluctuation


def matched_load_factor(base: ProcessClass, new: ProcessClass,
                        calendar=None) -> float:
    """The load factor whose cap clips as many hours on `new` as on `base`.

    A shipped class's cap holds 1-2 % of its hours at the peak. Changing the
    calendar or the on/off state changes the uncapped profile, and so the cap
    that clips that same share: on one uncapped reference year of each, with p
    the share the base's cap holds,

        c   = the (1 - p) quantile of the new uncapped profile P
        eta = mean(min(P, c)) / c

    which is a fixed point of the cap iteration. `calendar` puts the new class
    on another calendar, as a carrier given its own.

    A base with no fluctuation beyond its calendar and on/off state gives a
    step function, which no cap can clip by a small share, and whose own load
    factor (mean over peak) moves by a few per cent with where the stops fall.
    The new class then takes 1 % above the highest such load factor over eight
    reference years and four carriers: the cap trims the highest step slightly,
    and is reached in practice whatever the seed.
    """
    references, base_is_steps = _reference_uncapped(base)
    reference = references[0]
    capped = cap_to_rated_capacity(reference, base.target_load_factor)
    share = float(np.mean(capped >= capped.max() * (1.0 - 1e-9)))
    if base_is_steps:
        own = [float(row.mean() / row.max())
               for seed in range(8)
               for row in _reference_uncapped(new, calendar, seed)[0]]
        return float(min(1.01 * max(own), 0.99))
    profile = _reference_uncapped(new, calendar)[0][0]
    if share <= 0.0 or share >= 1.0:
        return float(np.mean(profile) / np.max(profile))
    cap = float(np.quantile(profile, 1.0 - share))
    return float(np.mean(np.minimum(profile, cap)) / cap)


def carrier_load_factors(spec: DemandSpec, total_hours: float = 8760.0,
                         ) -> dict[str, float]:
    """The load factor each carrier's cap holds.

    A rated carrier's load factor is its mean demand over its rating,

        eta_m = E_m * 1000 / (T * P_m)

    with E_m its annual energy (MWh), T the hours in the year and P_m its
    rating (kW). A rating at or below the mean demand cannot deliver the annual
    energy, and raises.

    In order, a carrier takes: its rating, if it has one; else the load factor
    the spec gives it; else, on a calendar of its own, the load factor whose
    cap clips as many hours on that calendar as the class's cap does on the
    class's (`matched_load_factor`); else the class's load factor.
    """
    process = get_class(spec.process_class)
    energies = dict(spec.annual_mwh_by_carrier(), waste=spec.waste_mwh)
    factors = {}
    for carrier in ALL_CARRIERS:
        rating = spec.rated_kw.get(carrier)
        if rating is None and carrier in spec.load_factor:
            factors[carrier] = float(spec.load_factor[carrier])
            continue
        if rating is None and carrier in spec.calendars:
            factors[carrier] = matched_load_factor(process, process,
                                                   spec.calendars[carrier])
            continue
        if rating is None:
            factors[carrier] = process.target_load_factor
            continue
        if energies[carrier] <= 0.0:
            raise ValueError(
                f"rated_kw names {carrier}, which this site does not have")
        mean_kw = energies[carrier] * 1000.0 / total_hours
        if rating <= mean_kw:
            raise ValueError(
                f"rated_kw for {carrier} ({rating:.0f} kW) is at or below its "
                f"mean demand ({mean_kw:.0f} kW): no plant of that rating can "
                f"deliver {energies[carrier]:.0f} MWh in a year")
        factors[carrier] = mean_kw / rating
    return factors


def build_profiles(spec: DemandSpec, index: pd.DatetimeIndex,
                   knob: float | None = None, check: bool = True,
                   load_factors: dict[str, float] | None = None,
                   ) -> pd.DataFrame:
    """Hourly demand in kW for one site, one column per carrier.

    Parameters
    ----------
    spec
        What to generate.
    index
        Hourly timestamps. A full year is usual but any length works.
    knob
        Correlation between the carriers' latent series, which the generator
        sets internally. Leave as ``None`` to solve for the value that delivers
        `spec.carrier_correlation` in the finished profiles; pass a number to
        use it directly, which is what the solver itself does.
    check
        Compare what was delivered with what was asked, and issue a
        `TargetMissedWarning` for each miss, with its cause. See
        `loadcast.delivery_report`.
    load_factors
        Load factor of each carrier's cap, in place of the ones the spec
        implies. The correlation solver uses it; leave it as ``None``.
    """
    process = get_class(spec.process_class)
    hours_per_step = step_hours(index)
    # Energy divided by *elapsed hours*, not by the number of steps, so the mean
    # power is the same whether the year is rendered in 8760 steps or 35040.
    total_hours = float(len(index)) * hours_per_step
    if load_factors is None:
        load_factors = carrier_load_factors(spec, total_hours)
    if knob is None:
        # With fewer than two carriers there is no cross-carrier correlation to
        # deliver, and solving for one would only cost time.
        knob = (_solve_knob(spec, hours_per_step, load_factors)[0]
                if len(spec.active_carriers) > 1 else 0.0)

    shapes, masks, residuals = _stochastic_factors(process, spec, index, knob)
    composition = spec.composition

    columns: dict[str, np.ndarray] = {}
    for position, carrier in enumerate(ALL_CARRIERS):
        # Waste heat is not part of the composition: it is a by-product sized
        # off the heat demand, so its energy comes from a different place.
        energy_mwh = (spec.waste_mwh if carrier == "waste"
                      else spec.annual_mwh * float(composition[position]))
        if energy_mwh <= 0.0:
            # A carrier the site does not have. The column stays so the frame's
            # schema does not depend on the spec.
            columns[COLUMN_NAMES[carrier]] = np.zeros(len(index))
            continue

        # A lag is given in hours and applied in steps.
        lag = int(round(spec.carrier_lag_h.get(carrier, 0) / hours_per_step))
        # The calendar is unshifted; only the process fluctuation carries the
        # lag.
        profile = (shapes[position]
                   * _shift(masks[position], lag)
                   * _shift(residuals[position], lag))
        profile = cap_to_rated_capacity(profile, load_factors[carrier])

        target_kw = energy_mwh * 1000.0 / total_hours
        mean = float(profile.mean())
        columns[COLUMN_NAMES[carrier]] = (
            profile * (target_kw / mean) if mean > 0 else np.zeros(len(index))
        )

    frame = pd.DataFrame(columns, index=index)
    if check:
        from .checks import warn_misses
        warn_misses(spec, frame)
    return frame


def generate(spec: DemandSpec | None = None, year: int = 2025,
             freq: str = "h", **kwargs) -> pd.DataFrame:
    """Generate one year of demand at the requested resolution.

    The convenience entry point. Either pass a `DemandSpec`, or pass its fields
    directly as keyword arguments:

        generate(annual_mwh=10_000, heat_to_cold=7.4, elec_share=0.2)
        generate(annual_mwh=10_000, freq="15min")     # quarter-hourly

    `freq` is any pandas offset alias -- ``"h"``, ``"30min"``, ``"15min"``. The
    persistence is rescaled so an excursion lasts the same number of *hours* at
    any resolution, and the energy is divided by elapsed hours rather than by
    step count, so the mean power is unchanged.

    Whatever it cannot deliver as asked -- a load factor the cap cannot hold, a
    spread the calendar leaves no room for, a correlation below the floor -- it
    reports in a `TargetMissedWarning` that says why. `delivery_report` gives
    the full comparison as a table.

    Two caveats apply to sub-hourly output. The process classes were calibrated
    on hourly meters, so their spread and persistence describe hourly
    behaviour; asking for 15-minute steps draws those hourly statistics on a
    finer grid rather than adding measured sub-hourly structure. And the
    calendar resolves to the hour of day, so every step within an hour carries
    the same calendar factor: all sub-hourly variation comes from the residual.
    """
    if spec is None:
        spec = DemandSpec(**kwargs)
    elif kwargs:
        raise TypeError("pass either a DemandSpec or its fields, not both")
    # Right-open on the next new year, so the year is complete and has no
    # duplicated final step at any resolution.
    index = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq=freq)[:-1]
    return build_profiles(spec, index)


# =============================================================================
# The correlation knob
# =============================================================================

# Solved knob and the reachable range, keyed by everything that sets them: the
# class itself (not its name, so a class rebuilt under the same name is solved
# afresh), the target, the seed, the step, and the heat and cold caps and
# calendars.
_KNOB_CACHE: dict[tuple, tuple[float, float, float]] = {}


def _solve_knob(spec: DemandSpec, hours_per_step: float = 1.0,
                load_factors: dict[str, float] | None = None,
                tolerance: float = 0.005, max_iterations: int = 20,
                ) -> tuple[float, float, float]:
    """The knob, and the lowest and highest heat-cold correlation reachable."""
    process = get_class(spec.process_class)
    if load_factors is None:
        load_factors = carrier_load_factors(spec, 8760.0)
    thermal = ("heat", "cold")
    key = (process, round(spec.correlation_target, 6), int(spec.seed),
           round(float(hours_per_step), 6),
           tuple(round(load_factors[c], 9) for c in thermal),
           tuple(spec.calendars.get(c) for c in thermal))
    if key in _KNOB_CACHE:
        return _KNOB_CACHE[key]

    target = spec.correlation_target
    # Solve on a spec with no lag, so the target is the correlogram's peak, and
    # with both thermal carriers present whatever the real spec asks for. The
    # caps travel as load factors, which do not depend on the probe's energies.
    probe = DemandSpec(
        annual_mwh=spec.annual_mwh,
        heat_to_cold=2.0,
        elec_share=0.2,
        process_class=process,
        carrier_correlation=target,
        seed=spec.seed,
        calendars={c: spec.calendars[c] for c in thermal if c in spec.calendars},
    )
    # A year at the target resolution, so the solved knob belongs to the same
    # persistence the real call will use.
    periods = max(2000, int(round(8760.0 / max(hours_per_step, 1e-9))))
    index = pd.date_range("2025-01-01", periods=periods,
                          freq=pd.Timedelta(hours=hours_per_step))

    def delivered(knob: float) -> float:
        frame = build_profiles(probe, index, knob=knob, check=False,
                               load_factors=load_factors)
        return float(frame["heat_kw"].corr(frame["cold_kw"]))

    low, high = 0.0, 0.99
    at_low, at_high = delivered(low), delivered(high)
    if target <= at_low:
        answer = low
    elif target >= at_high:
        answer = high
    else:
        for _ in range(max_iterations):
            middle = 0.5 * (low + high)
            value = delivered(middle)
            if abs(value - target) < tolerance:
                low = high = middle
                break
            if value < target:
                low = middle
            else:
                high = middle
        answer = 0.5 * (low + high)

    _KNOB_CACHE[key] = (answer, at_low, at_high)
    return _KNOB_CACHE[key]


def solve_correlation_knob(spec: DemandSpec, tolerance: float = 0.005,
                           max_iterations: int = 20,
                           hours_per_step: float = 1.0) -> float:
    """Internal correlation that delivers the requested finished correlation.

    The correlation the generator sets, between the carriers' latent series,
    and the correlation you observe in the finished profiles are different
    numbers. Carriers share a calendar, so the finished profiles are correlated
    even when their residuals are independent -- every carrier dips on a Sunday
    and in July. The floor this imposes is

        g(0) = CV_calendar^2 / CV_total^2

    which for the shipped process classes runs from 0.08 to 0.64. A carrier
    given a calendar of its own shares less with the others, and lowers it. No
    non-negative internal correlation delivers less than the floor; asked for
    less, the solver returns the value that comes closest, and the generator
    warns.

    Solved by bisection, generating a year at each trial value, and cached.
    It is solved at *zero lag*, so `carrier_correlation` is the peak of the
    cross-correlogram. A lag sweep then changes timing without also changing
    how tightly the carriers move together.
    """
    return _solve_knob(spec, hours_per_step, None, tolerance, max_iterations)[0]
