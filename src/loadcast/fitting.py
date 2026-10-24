"""Turning what you can observe into what the generator needs.

This is what separates a demand generator from a random signal generator. A
signal generator asks for `sigma` and `phi`. Here you supply what a meter, a
bill or a datasheet actually tells you --

    load factor    mean demand over peak demand
    spread         coefficient of variation of the hourly series
    persistence    lag-1 autocorrelation, how long an excursion lasts
    idle fraction  share of hours the process is effectively off

-- and the generator parameters follow in closed form, with no optimiser and no
convergence criterion.

The inversions
--------------
For a residual ``R = exp(z)`` with ``z`` a stationary Gaussian AR(1) of variance
``sigma^2`` and lag-1 coefficient ``phi``:

    CV[R]      = sqrt(exp(sigma^2) - 1)
    rho_R(1)   = (exp(phi*sigma^2) - 1) / (exp(sigma^2) - 1)

Both invert exactly:

    sigma^2 = ln(1 + CV^2)
    phi     = ln(1 + rho_R(1)*(exp(sigma^2) - 1)) / sigma^2

More generally a latent correlation ``rho_z`` becomes a residual correlation

    rho_R = (exp(rho_z * sigma^2) - 1) / (exp(sigma^2) - 1)

of which the lag-1 case above is simply ``rho_z = phi``. The same expression
gives the whole cross-correlogram once a lag is in play.
"""

from __future__ import annotations

import warnings
from dataclasses import replace

import numpy as np

from .calendars import Calendar
from .checks import TargetMissedWarning
from .classes import ProcessClass, get_class, load_classes
from .spec import DemandSpec

__all__ = [
    "sigma_from_cv", "cv_from_sigma",
    "phi_from_lag1", "lag1_from_phi",
    "residual_correlation", "latent_correlation",
    "combine_cv", "split_cv",
    "correlation_floor", "correlation_transfer",
    "class_from_observations", "custom_class", "bias_report",
]


# =============================================================================
# Spread and persistence
# =============================================================================


def sigma_from_cv(cv: float) -> float:
    """Log-space spread of a lognormal with coefficient of variation `cv`."""
    if cv < 0:
        raise ValueError(f"cv cannot be negative, got {cv}")
    return float(np.sqrt(np.log1p(cv**2)))


def cv_from_sigma(sigma: float) -> float:
    """Coefficient of variation of ``exp(z)`` for ``z ~ N(0, sigma^2)``."""
    return float(np.sqrt(np.expm1(sigma**2)))


def phi_from_lag1(lag1: float, sigma: float) -> float:
    """Latent AR(1) coefficient giving an observed lag-1 autocorrelation.

    The exponential transform compresses correlations, so the latent needs a
    *higher* coefficient than the one you measure on the series itself.
    """
    variance = float(sigma) ** 2
    if variance <= 0:
        return 0.0
    return float(np.log1p(lag1 * np.expm1(variance)) / variance)


def lag1_from_phi(phi: float, sigma: float) -> float:
    """Observed lag-1 autocorrelation of a lognormal AR(1)."""
    variance = float(sigma) ** 2
    if variance <= 0:
        return 0.0
    return float(np.expm1(phi * variance) / np.expm1(variance))


def residual_correlation(latent_corr: float, sigma: float) -> float:
    """Correlation of two lognormals from the correlation of their latents."""
    variance = float(sigma) ** 2
    if variance <= 0:
        return float(latent_corr)
    return float(np.expm1(latent_corr * variance) / np.expm1(variance))


def latent_correlation(residual_corr: float, sigma: float) -> float:
    """Inverse of `residual_correlation`."""
    variance = float(sigma) ** 2
    if variance <= 0:
        return float(residual_corr)
    inner = 1.0 + residual_corr * np.expm1(variance)
    if inner <= 0:
        return -1.0
    return float(np.log(inner) / variance)


# =============================================================================
# How the calendar and the residual share the spread
# =============================================================================


def combine_cv(calendar_cv: float, residual_cv: float) -> float:
    """Total spread from calendar and residual spreads.

        1 + CV_total^2 = (1 + CV_calendar^2)(1 + CV_residual^2)
    """
    return float(np.sqrt((1 + calendar_cv**2) * (1 + residual_cv**2) - 1))


def split_cv(total_cv: float, calendar_cv: float) -> float:
    """Residual spread needed to reach `total_cv` given the calendar's own."""
    ratio = (1 + total_cv**2) / (1 + calendar_cv**2)
    return float(np.sqrt(max(ratio - 1.0, 0.0)))


# =============================================================================
# Cross-carrier correlation
# =============================================================================


def correlation_transfer(latent_corr: float, calendar_cv: float,
                         residual_cv: float, sigma: float | None = None
                         ) -> float:
    """Correlation of the finished profiles, from the internal correlation.

    `latent_corr` is the correlation between the carriers' latent series, which
    the generator sets.

    With ``P_m = L_m * S * R_m`` sharing one calendar ``S``, writing
    ``q = rho_R * CV_R^2``:

                       CV_S^2 + q + CV_S^2 * q
        corr(P_h, P_c) = -----------------------
                                CV_total^2

    It matches simulation to three decimals across the range of `latent_corr`.
    It is exact without the on/off state and the capacity cap; both shift it,
    so the generator solves for the internal correlation numerically and uses
    this formula to explain and diagnose.
    """
    if sigma is None:
        sigma = sigma_from_cv(residual_cv)
    rho_r = residual_correlation(latent_corr, sigma)
    q = residual_cv**2 * rho_r
    total_squared = (1 + calendar_cv**2) * (1 + residual_cv**2) - 1
    if total_squared <= 0:
        return 0.0
    return float((calendar_cv**2 + q + calendar_cv**2 * q) / total_squared)


def correlation_floor(process_class: str | ProcessClass | DemandSpec,
                      index=None) -> float:
    """Lowest cross-carrier correlation reachable with independent residuals.

        g(0) = CV_calendar^2 / CV_total^2

    The floor is the share of a profile's total variance that the shared
    calendar contributes. It is a statement about industry: a high floor means
    the carriers move together mainly because the factory is open or shut, not
    because the processes are linked.

    No non-negative internal correlation delivers a correlation below this
    floor. Pass a class (or its name) for the formula above, which assumes
    every carrier follows the class's calendar. Pass a `DemandSpec` for the
    floor of that site, measured on a generated year: a carrier with a calendar
    of its own, or a cap of its own, shifts it.
    """
    import pandas as pd

    if isinstance(process_class, DemandSpec):
        from .generator import _solve_knob
        return float(_solve_knob(process_class)[1])
    process = get_class(process_class)
    if index is None:
        index = pd.date_range("2025-01-01", periods=8760, freq="h")

    calendar = process.calendar(index)
    calendar_cv = float(np.std(calendar) / np.mean(calendar))
    residual_cv = split_cv(process.target_cv, calendar_cv)
    total_squared = (1 + calendar_cv**2) * (1 + residual_cv**2) - 1
    return float(calendar_cv**2 / total_squared) if total_squared > 0 else 0.0


# =============================================================================
# Building a class from your own measurements
# =============================================================================


def bias_report(process_class: str | None = None, seeds: int = 4,
                ) -> "pd.DataFrame":
    """Target statistics against what the generator actually delivers.

    Load factor and annual energy are imposed and come out exact. Spread and
    persistence are *not* imposed -- they follow from parameters chosen to
    produce them -- so they land near their targets rather than on them, and
    this reports how near, averaged over `seeds` draws. The offset is
    systematic rather than random, and its sign depends on the class. Without
    an on/off state, persistence comes out above target, because the capacity
    cap trims the peaks that would otherwise break up a run; with one, it
    comes out below, because the on/off state chops runs into pieces.

    The gap is reported rather than tuned away: a further parameter fitted to
    close it would be over-fitting, not calibration.
    """
    import pandas as pd

    from .generator import generate

    from .stats import profile_statistics

    names = [process_class] if process_class else sorted(load_classes())
    rows = []
    for name in names:
        process = get_class(name)
        achieved = {"load_factor": [], "cv": [], "lag1": []}
        for seed in range(1, seeds + 1):
            frame = generate(annual_mwh=10_000, heat_to_cold=2.0,
                             elec_share=0.2, process_class=name, seed=seed)
            statistics = profile_statistics(frame["heat_kw"])
            for key in achieved:
                achieved[key].append(statistics[key])
        rows.append({
            "class": name,
            "load_factor_target": process.target_load_factor,
            "load_factor_mean": float(np.mean(achieved["load_factor"])),
            "cv_target": process.target_cv,
            "cv_mean": float(np.mean(achieved["cv"])),
            "lag1_target": process.target_lag1,
            "lag1_mean": float(np.mean(achieved["lag1"])),
        })
    table = pd.DataFrame(rows).set_index("class")
    table["cv_bias"] = table["cv_mean"] - table["cv_target"]
    table["lag1_bias"] = table["lag1_mean"] - table["lag1_target"]
    return table.round(4)


def class_from_observations(name: str, load_factor: float, cv: float,
                            lag1: float, calendar_from: str = "continuous",
                            off_fraction: float = 0.0, off_level: float = 0.02,
                            description: str = "",
                            calendar: Calendar | None = None) -> ProcessClass:
    """A process class fitted to statistics you measured yourself.

    Supply the numbers a meter gives you and get a class the generator can
    use. The calendar is your own if you pass one -- from your schedule, your
    meter or your monthly bills, see `loadcast.Calendar` -- and is otherwise
    borrowed from the shipped class named by `calendar_from`. To change only
    some of a shipped class's numbers, use `custom_class` instead.

    .. warning::

       **Feed it measurements, never generated output.** The generator misses
       its persistence target by a systematic amount (see `bias_report`). That
       offset does no harm once, but it compounds if you measure a generated
       profile and feed the result back in. Doing so repeatedly from `semi_continuous`
       drives the lag-1 autocorrelation 0.79 -> 0.86 -> 0.91 -> 0.94 -> ... up to
       a fixed point near 0.97, while the spread bleeds down from 0.48 to 0.42:
       the profile grows smoother and stickier each round until it has lost the
       high-frequency variability it was supposed to have.

       This is the classic degeneration of any model retrained on its own
       output, and the package never does it -- the shipped classes hold
       constants measured once, and no code path writes generated statistics
       back into a class. It is only reachable if a caller builds that loop
       deliberately.

    Parameters
    ----------
    name
        Name to register the class under, and to pass as `process_class`.
    load_factor
        Mean demand over peak demand, in (0, 1).
    cv
        Coefficient of variation of the hourly series: standard deviation over
        mean.
    lag1
        Lag-1 autocorrelation of the hourly series: its correlation with itself
        one hour later.
    calendar_from
        Shipped class whose calendar (month, weekday and hour factors) to
        borrow when `calendar` is not given.
    off_fraction
        Share of hours the process is off. Leave at zero unless the process
        runs or stops: spread alone cannot make a profile *off* rather than
        merely low, and an on/off state fitted to a process that does not stop
        overstates its idle time.
    off_level
        Load while off, as a fraction of the running level.
    description
        Free text kept with the class.
    calendar
        Your own `loadcast.Calendar`. Measured statistics and a calendar must
        come from the same site: the spread includes the calendar's, and must
        be larger than it.
    """
    if not 0.0 < load_factor < 1.0:
        raise ValueError(f"load_factor must be in (0, 1), got {load_factor}")
    if cv <= 0:
        raise ValueError(f"cv must be positive, got {cv}")
    if not -1.0 < lag1 < 1.0:
        raise ValueError(f"lag1 must be in (-1, 1), got {lag1}")

    template = get_class(calendar_from)
    built = replace(
        template,
        name=name,
        target_load_factor=float(load_factor),
        target_cv=float(cv),
        target_lag1=float(lag1),
        mode="onoff" if off_fraction > 0 else "lognormal",
        off_fraction=float(off_fraction),
        off_level=float(off_level),
        description=description or f"fitted from observations, "
                                   f"calendar of {calendar_from}",
        anchor_site="user",
    )
    if calendar is not None:
        built = _with_calendar(built, calendar)
        if not description:
            built = replace(built, description="fitted from observations, "
                                               "own calendar")
    _warn_if_no_room(built)
    return built


# =============================================================================
# Adjusting a shipped class
# =============================================================================


def _mask_term(off_fraction: float, off_level: float) -> tuple[float, float]:
    """Mean of the on/off factor M, and 1 + CV[M]^2.

    M is 1 with probability 1 - a and l with probability a, so
    E[M] = 1 - a + a*l and E[M^2] = 1 - a + a*l^2.
    """
    mean = 1.0 - off_fraction + off_fraction * off_level
    second = 1.0 - off_fraction + off_fraction * off_level**2
    return mean, second / mean**2


def _calendar_terms(calendar: Calendar) -> tuple[float, float]:
    """1 + CV[S]^2 of a calendar over an hourly year, and its peak over its mean."""
    import pandas as pd

    index = pd.date_range("2025-01-01", periods=8760, freq="h")
    values = calendar.factors(index)
    return (1.0 + (values.std() / values.mean())**2,
            float(values.max() / values.mean()))


def _with_calendar(process: ProcessClass, calendar: Calendar) -> ProcessClass:
    """The class with its calendar replaced, weekday and hour kept as summaries."""
    week = np.asarray(calendar.week).reshape(7, 24)
    return replace(process, month=calendar.month, week=calendar.week,
                   dayofweek=tuple(week.mean(axis=1)),
                   hour=tuple(week.mean(axis=0)))


def _warn_if_no_room(process: ProcessClass) -> None:
    """Warn when the calendar and on/off state already exceed the class's spread."""
    calendar_term, _ = _calendar_terms(Calendar.of(process))
    _, mask_term = _mask_term(process.off_fraction, process.off_level)
    fixed = float(np.sqrt(calendar_term * mask_term - 1.0))
    if process.target_cv <= fixed:
        warnings.warn(
            f"class {process.name!r}: its calendar and on/off state alone "
            f"spread the profile by {fixed:.2f}, as much as or more than its "
            f"spread of {process.target_cv:.2f}, so nothing is left for the "
            f"fluctuation: the profile will be its calendar. Give it a spread "
            f"above {fixed:.2f}.",
            TargetMissedWarning, stacklevel=3)


def custom_class(base: str | ProcessClass = "semi_continuous", *,
                 name: str | None = None,
                 calendar: Calendar | None = None,
                 load_factor: float | None = None,
                 cv: float | None = None,
                 lag1: float | None = None,
                 off_fraction: float | None = None,
                 off_level: float | None = None,
                 description: str | None = None) -> ProcessClass:
    """A shipped class with any of its numbers changed.

    Start from the class closest to your site, which is calibrated on a
    metered plant, and change what you know to be different. Everything you
    leave out is carried over so that the plant behaves as the base class does
    *while it runs*:

    spread
        The base's fluctuation within its running hours is kept, and the new
        calendar's and on/off state's spread added to it, since one plus the
        squared spread multiplies across independent factors:
        ``1 + cv^2 = (1 + cv_calendar^2)(1 + cv_onoff^2)(1 + cv_fluctuation^2)``.
    load factor
        The cap clips as many hours as the base's does: a shipped class holds
        1-2 % of its hours at the peak, and the new class holds the same share
        on its own calendar and on/off state (see
        `loadcast.generator.matched_load_factor`).
    persistence
        Unchanged.

    So ``custom_class("semi_continuous", off_fraction=0.3)`` is the same plant
    stopping 30 % of the time, and ``custom_class("semi_continuous",
    calendar=two_shifts)`` the same plant on your shifts. Give a number
    explicitly to override what is derived.

    The result needs no registering: pass it as `process_class`. Register it
    with `register_class` only to call it by name.

    Parameters
    ----------
    base
        Name of a shipped class, or a `ProcessClass`.
    name
        Name for the new class; by default the base's with ``"+custom"``.
    calendar
        A `loadcast.Calendar`: from a schedule, a meter or monthly bills.
    load_factor, cv, lag1
        Load factor, spread (coefficient of variation, calendar included) and
        hourly lag-1 autocorrelation of the finished profile.
    off_fraction, off_level
        Share of hours the process is stopped, and its load while stopped
        relative to running. A base that never stops gets an idle level of
        0.02 unless you give one.
    description
        Free text kept with the class.
    """
    origin = get_class(base)
    given = [label for label, value in (
        ("calendar", calendar), ("load_factor", load_factor), ("cv", cv),
        ("lag1", lag1), ("off_fraction", off_fraction),
        ("off_level", off_level)) if value is not None]
    off = origin.off_fraction if off_fraction is None else float(off_fraction)
    if off_level is None:
        level = origin.off_level if origin.off_fraction > 0 else 0.02
    else:
        level = float(off_level)
    if not 0.0 <= off < 1.0:
        raise ValueError(f"off_fraction must be in [0, 1), got {off}")
    if not 0.0 <= level < 1.0:
        raise ValueError(f"off_level must be in [0, 1), got {level}")

    old_calendar = Calendar.of(origin)
    new_calendar = old_calendar if calendar is None else calendar
    old_term, _ = _calendar_terms(old_calendar)
    new_term, _ = _calendar_terms(new_calendar)
    _, old_mask = _mask_term(origin.off_fraction, origin.off_level)
    _, new_mask = _mask_term(off, level)

    reshaped = calendar is not None or (off, level) != (
        origin.off_fraction, origin.off_level if origin.off_fraction > 0 else 0.02)
    if cv is None and not reshaped:
        cv = origin.target_cv
    elif cv is None:
        # A base whose calendar and stops already exceed its spread (batch)
        # has no fluctuation beyond them, and keeps none on the new calendar.
        fluctuation = max((1 + origin.target_cv**2) / (old_term * old_mask), 1.0)
        cv = float(np.sqrt(max(new_term * new_mask * fluctuation - 1.0, 1e-6)))
    if lag1 is None:
        lag1 = origin.target_lag1
    if load_factor is not None and not 0.0 < load_factor < 1.0:
        raise ValueError(f"load_factor must be in (0, 1), got {load_factor}")
    if cv <= 0:
        raise ValueError(f"cv must be positive, got {cv}")
    if not -1.0 < lag1 < 1.0:
        raise ValueError(f"lag1 must be in (-1, 1), got {lag1}")

    built = replace(
        origin,
        name=name or f"{origin.name}+custom",
        target_load_factor=(origin.target_load_factor if load_factor is None
                            else float(load_factor)),
        target_cv=float(cv),
        target_lag1=float(lag1),
        mode="onoff" if off > 0 else "lognormal",
        off_fraction=off,
        off_level=level if off > 0 else 0.0,
        description=description or (f"{origin.name}, with "
                                    f"{', '.join(given) or 'nothing'} changed"),
        anchor_site="user",
    )
    if calendar is not None:
        built = _with_calendar(built, calendar)
    if load_factor is None and (reshaped or cv != origin.target_cv
                                or lag1 != origin.target_lag1):
        # Anything that reshapes the uncapped profile moves the cap that clips
        # the base's share of hours: derive the load factor that keeps it.
        from .generator import matched_load_factor
        built = replace(built, target_load_factor=matched_load_factor(origin,
                                                                      built))
    if "cv" in given:
        # A derived spread inherits the base's room for fluctuation, whatever
        # it is; only a spread you set can contradict the calendar.
        _warn_if_no_room(built)
    return built
