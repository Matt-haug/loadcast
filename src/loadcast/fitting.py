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

from dataclasses import replace

import numpy as np

from .classes import ProcessClass, get_class, load_classes

__all__ = [
    "sigma_from_cv", "cv_from_sigma",
    "phi_from_lag1", "lag1_from_phi",
    "residual_correlation", "latent_correlation",
    "combine_cv", "split_cv",
    "correlation_floor", "correlation_transfer",
    "class_from_observations", "bias_report",
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
    """Correlation of the finished profiles, from the generator's knob.

    With ``P_m = L_m * S * R_m`` sharing one calendar ``S``, writing
    ``q = rho_R * CV_R^2``:

                       CV_S^2 + q + CV_S^2 * q
        corr(P_h, P_c) = -----------------------
                                CV_total^2

    Verified against simulation to three decimals across the range of the knob.
    It is exact for the unmasked model; an on/off mask and the capacity cap both
    shift it, which is why the production path solves for the knob numerically
    and uses this for explanation, diagnosis and a starting guess.
    """
    if sigma is None:
        sigma = sigma_from_cv(residual_cv)
    rho_r = residual_correlation(latent_corr, sigma)
    q = residual_cv**2 * rho_r
    total_squared = (1 + calendar_cv**2) * (1 + residual_cv**2) - 1
    if total_squared <= 0:
        return 0.0
    return float((calendar_cv**2 + q + calendar_cv**2 * q) / total_squared)


def correlation_floor(process_class: str | ProcessClass,
                      index=None) -> float:
    """Lowest cross-carrier correlation reachable with independent residuals.

        g(0) = CV_calendar^2 / CV_total^2

    Read it as a statement about industry rather than as plumbing: the floor is
    the share of a profile's total variance that the shared calendar
    contributes, so a high floor means the carriers move together mainly
    because the factory is open or shut, not because the processes are linked.

    Asking the generator for a correlation below this floor cannot be satisfied
    by any non-negative knob.
    """
    import pandas as pd

    process = (process_class if isinstance(process_class, ProcessClass)
               else get_class(process_class))
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
    persistence are *not* imposed -- they emerge from parameters chosen to
    produce them -- so they land close but not on target, and this reports how
    close. The offset is systematic rather than random: persistence typically
    comes out a few hundredths above target, because the capacity cap trims the
    peaks that would otherwise break up a run.

    Reported rather than tuned away. A third free parameter fitted to close it
    would be over-fitting, not calibration.
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
                            description: str = "") -> ProcessClass:
    """A process class fitted to statistics you measured yourself.

    Supply the four numbers a meter gives you and get a class the generator can
    use. The calendar rhythm is borrowed from one of the shipped classes, since
    a month/day/hour shape needs a full year of measurement to estimate and is
    usually the part a user does *not* have; pass `calendar_from` to choose
    which rhythm is closest to your site's shift pattern.

    .. warning::

       **Feed it measurements, never generated output.** The generator delivers
       persistence slightly above target (see `bias_report`). That offset is
       harmless once, but it compounds if you measure a generated profile and
       feed the result back in. Doing so repeatedly from `semi_continuous`
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
    load_factor
        Mean demand over peak demand, in (0, 1).
    cv
        Coefficient of variation of the hourly series.
    lag1
        Lag-1 autocorrelation of the hourly series.
    off_fraction
        Share of hours effectively off. Leave at zero unless the process is
        genuinely bimodal: a spread alone cannot make a profile *off* rather
        than merely low, and a mask fitted to a process that does not stop will
        overstate its idle time.
    """
    if not 0.0 < load_factor < 1.0:
        raise ValueError(f"load_factor must be in (0, 1), got {load_factor}")
    if cv <= 0:
        raise ValueError(f"cv must be positive, got {cv}")
    if not -1.0 < lag1 < 1.0:
        raise ValueError(f"lag1 must be in (-1, 1), got {lag1}")

    template = get_class(calendar_from)
    return replace(
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
