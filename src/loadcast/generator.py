"""The generator.

Every profile is a product of four factors, then capped and rescaled:

    P_m(t) = L_m * S(t) * M_m(t - tau_m) * R_m(t - tau_m)

where

    P_m(t)   demand for carrier m at hour t, kW
    L_m      level, set so the annual energy matches the spec exactly
    S(t)     calendar factor: month x day-of-week x hour, mean one
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

The calendar is shared and never shifted. A factory's opening hours are common
to all its carriers -- heat and refrigeration do not take the weekend off at
different times -- so only the *process fluctuation* carries a lag. Because a
circular shift is a permutation, lagging a carrier leaves every one of its own
statistics (load factor, spread, persistence, annual energy) exactly unchanged.
The lag is therefore a pure cross-carrier knob.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .classes import ProcessClass, get_class
from .spec import ALL_CARRIERS, CARRIERS, COLUMN_NAMES, DemandSpec

__all__ = ["generate", "build_profiles", "solve_correlation_knob"]


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
    """Persistent, cross-correlated on/off masks from Gaussian latents.

    Thresholding a persistent latent at its own empirical quantile is a Gaussian
    copula: the binary state inherits both the persistence and the cross-carrier
    correlation of the latent, with no transition matrix to fit. Using the
    *empirical* quantile makes the realised off fraction exactly `off_fraction`.

    Giving every carrier the same mask would force their correlation to one,
    which is the artefact this package exists to avoid.
    """
    if off_fraction <= 0.0:
        return np.ones_like(latent)
    cut = np.quantile(latent, off_fraction, axis=-1, keepdims=True)
    return np.where(latent > cut, 1.0, float(off_level))


def cap_to_rated_capacity(profile: np.ndarray, target_load_factor: float,
                          iterations: int = 8) -> np.ndarray:
    """Impose a rated capacity while preserving annual energy.

    A plant cannot draw more than it has installed, so its load duration curve
    has a hard ceiling; a lognormal tail has none. Capping lowers the mean,
    which lowers the cap, so cap and rescale are alternated:

        P~ = min(P, mean(P)/eta);   P <- P~ * E / sum(P~)

    The map is a contraction and converges in a handful of passes. At the fixed
    point the load factor is `eta` and the energy is `E`, both exactly. This is
    what makes the *extreme quantiles* right: the coefficient of variation can
    be correct while the top of the load duration curve is badly wrong.
    """
    if not 0.0 < target_load_factor < 1.0:
        return profile

    out = np.array(profile, dtype=float)
    energy = float(out.sum())
    if energy <= 0:
        return out
    for _ in range(iterations):
        mean = float(out.mean())
        if mean <= 0:
            break
        out = np.minimum(out, mean / target_load_factor)
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
    deltas = np.diff(index.view("int64"))
    # Median rather than the first gap, so a daylight-saving seam or a single
    # missing step does not redefine the resolution.
    return float(np.median(deltas)) / 3.6e12


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


def _stochastic_factors(process: ProcessClass, spec: DemandSpec,
                        index: pd.DatetimeIndex, knob: float,
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calendar, masks and residuals, before any lag is applied."""
    n = len(index)
    rng = np.random.default_rng(spec.seed)
    shape = process.calendar(index)
    phi = rescale_persistence(process.target_lag1, step_hours(index))

    # Two independent sets of correlated latents: one drives the on/off state,
    # the other the variation within a run. Both carry the cross-carrier
    # correlation, so no carrier is a copy of another.
    mask_latent = correlated_ar1(n, len(ALL_CARRIERS), phi, 1.0, knob, rng)
    masks = onoff_from_latent(mask_latent, process.off_fraction,
                              process.off_level)

    # The residual supplies only the spread the calendar and mask have not.
    reference = shape * masks[0]
    cv = residual_cv_for(process.target_cv, reference)
    sigma = float(np.sqrt(np.log1p(cv**2)))
    residual_latent = correlated_ar1(n, len(ALL_CARRIERS), phi, sigma, knob, rng)
    residuals = lognormal_from_latent(residual_latent, sigma)
    return shape, masks, residuals


def build_profiles(spec: DemandSpec, index: pd.DatetimeIndex,
                   knob: float | None = None) -> pd.DataFrame:
    """Hourly demand in kW for one site, one column per carrier.

    Parameters
    ----------
    spec
        What to generate.
    index
        Hourly timestamps. A full year is usual but any length works.
    knob
        Internal residual correlation. Leave as ``None`` to solve for the one
        that delivers `spec.carrier_correlation` in the finished profiles; pass
        a number to use it directly, which is what the solver itself does.
    """
    process = get_class(spec.process_class)
    if knob is None:
        # With fewer than two carriers there is no cross-carrier correlation to
        # deliver, and solving for one would only cost time.
        knob = (solve_correlation_knob(spec, hours_per_step=step_hours(index))
                if len(spec.active_carriers) > 1 else 0.0)

    shape, masks, residuals = _stochastic_factors(process, spec, index, knob)

    hours_per_step = step_hours(index)
    # Energy divided by *elapsed hours*, not by the number of steps, so the mean
    # power is the same whether the year is rendered in 8760 steps or 35040.
    total_hours = float(len(index)) * hours_per_step
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
        # The calendar is shared and unshifted; only the process fluctuation
        # carries the lag.
        profile = (shape
                   * _shift(masks[position], lag)
                   * _shift(residuals[position], lag))
        profile = cap_to_rated_capacity(profile, process.target_load_factor)

        target_kw = energy_mwh * 1000.0 / total_hours
        mean = float(profile.mean())
        columns[COLUMN_NAMES[carrier]] = (
            profile * (target_kw / mean) if mean > 0 else np.zeros(len(index))
        )

    return pd.DataFrame(columns, index=index)


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

    Two honest caveats about sub-hourly output. The process classes were
    calibrated on hourly meters, so their spread and persistence describe hourly
    behaviour; asking for 15-minute steps renders those hourly statistics on a
    finer grid rather than adding measured sub-hourly structure. And the
    calendar resolves to hour-of-day, so every step within an hour carries the
    same calendar factor -- the sub-hourly variation is all residual.
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

_KNOB_CACHE: dict[tuple, float] = {}


def solve_correlation_knob(spec: DemandSpec, tolerance: float = 0.005,
                           max_iterations: int = 20,
                           hours_per_step: float = 1.0) -> float:
    """Residual correlation that delivers the requested finished correlation.

    The knob and the observable are different numbers. Carriers share a
    calendar, so the finished profiles are correlated even when their residuals
    are independent -- every carrier dips on a Sunday and in July. The floor
    this imposes is

        g(0) = CV_calendar^2 / CV_total^2

    which for these process classes runs from 0.08 to 0.64. Asking for a
    correlation below the floor is not achievable with a non-negative knob, and
    the solver will return the knob that gets closest rather than pretending.

    Solved by bisection on a one-year draw. The answer depends only on the
    process class, the target and the seed, so it is cached.

    The knob is solved at *zero lag*, so `carrier_correlation` is the peak of
    the cross-correlogram. That is deliberate: it lets a lag sweep change timing
    without also changing coupling strength.
    """
    key = (spec.process_class, round(float(spec.carrier_correlation), 6),
           int(spec.seed), round(float(hours_per_step), 6))
    if key in _KNOB_CACHE:
        return _KNOB_CACHE[key]

    target = float(spec.carrier_correlation)
    # Solve on a spec with no lag, so the target is the correlogram's peak, and
    # with two thermal carriers present whatever the real spec asks for.
    probe = DemandSpec(
        annual_mwh=spec.annual_mwh,
        heat_to_cold=2.0,
        elec_share=0.2,
        process_class=spec.process_class,
        carrier_correlation=target,
        seed=spec.seed,
    )
    # A year at the target resolution, so the solved knob belongs to the same
    # persistence the real call will use.
    periods = max(2000, int(round(8760.0 / max(hours_per_step, 1e-9))))
    index = pd.date_range("2025-01-01", periods=periods,
                          freq=pd.Timedelta(hours=hours_per_step))

    def delivered(knob: float) -> float:
        frame = build_profiles(probe, index, knob=knob)
        return float(frame.iloc[:, 0].corr(frame.iloc[:, 1]))

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

    _KNOB_CACHE[key] = answer
    return answer
