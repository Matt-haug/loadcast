"""What was asked, what was delivered, and why the two differ.

Some statistics are *imposed* and come out exact: the annual energy, the
composition and, while the cap is reached, the load factor. Others are *aimed
at*: the spread and the persistence follow from parameters chosen to produce
them, and the cap and the on/off state act afterwards, so they land near their
targets. A miss is reported when an exact statistic is not met, or when an
aimed one lands further off than the generator's usual error:

    spread (cv)     more than 25 % from its aim
    persistence     more than 0.2 from its aim, in hourly terms
    correlation     more than 0.03 from the request

The shipped classes, at their defaults, stay within these bands; their usual
gaps are listed by `loadcast.bias_report`.

Every miss names its cause. `generate` issues a `TargetMissedWarning` for each;
in a sweep, silence them and read `delivery_report` instead:

    import warnings
    warnings.simplefilter("ignore", loadcast.TargetMissedWarning)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .classes import get_class
from .generator import (_carrier_shapes, _solve_knob, carrier_load_factors,
                        step_hours)
from .spec import ALL_CARRIERS, COLUMN_NAMES, DemandSpec
from .stats import profile_statistics

__all__ = ["TargetMissedWarning", "delivery_report"]

CV_TOLERANCE = 0.25           # relative
LAG1_TOLERANCE = 0.20         # absolute, hourly
CORRELATION_TOLERANCE = 0.03  # absolute
LOAD_FACTOR_TOLERANCE = 0.005  # relative
AT_CAP_SHARE = 0.05           # share of steps at the peak above which the cap shapes the profile


class TargetMissedWarning(UserWarning):
    """A statistic came out other than asked. The message says why."""


def _mask_term(off_fraction: float, off_level: float) -> tuple[float, float]:
    """Mean of the on/off factor, and one plus its squared spread."""
    mean = 1.0 - off_fraction + off_fraction * off_level
    second = 1.0 - off_fraction + off_fraction * off_level**2
    return mean, second / mean**2


def _spread(values: np.ndarray) -> float:
    return float(np.std(values) / np.mean(values))


def _hourly_persistence(values: np.ndarray, hours_per_step: float,
                        lag1_per_step: float) -> float:
    """Correlation of a series with itself one hour later.

    Measured directly at the offset of one hour on a sub-hourly series: raising
    the per-step value to a power assumes an AR(1), which a profile with an
    on/off state is not.
    """
    if hours_per_step >= 1.0:
        return (lag1_per_step ** (1.0 / hours_per_step) if lag1_per_step > 0
                else lag1_per_step)
    steps = int(round(1.0 / hours_per_step))
    return float(np.corrcoef(values[:-steps], values[steps:])[0, 1])


def delivery_report(spec: DemandSpec, profiles: pd.DataFrame) -> pd.DataFrame:
    """Each requested statistic against what the profiles deliver, and why.

    One row per carrier and statistic, with the columns

        kind        exact, ceiling, aimed at, or default
        requested   what the spec and its class ask for
        delivered   what the profiles have
        status      ok, missed, or not checked
        why         the cause of a miss, and what to change

    The spread and persistence asked of a carrier are the class's, or, for a
    carrier with a calendar of its own, the class's fluctuation on that
    calendar.
    """
    process = get_class(spec.process_class)
    index = profiles.index
    hours_per_step = step_hours(index)
    total_hours = float(len(index)) * hours_per_step
    load_factors = carrier_load_factors(spec, total_hours)
    class_shape, shapes = _carrier_shapes(process, spec, index)

    mask_mean, mask_term = _mask_term(process.off_fraction, process.off_level)
    class_spread = np.sqrt((1 + _spread(class_shape)**2) * mask_term - 1)
    # The residual's share of the spread: 1 + CV^2 multiplies across factors.
    residual = float(np.sqrt(max((1 + process.target_cv**2)
                                 / (1 + class_spread**2) - 1, 0.0)))
    collapsed = residual < 1e-3

    energies = dict(spec.annual_mwh_by_carrier(), waste=spec.waste_mwh)
    rows: list[dict] = []

    def add(carrier, statistic, kind, requested, delivered, ok, why="",
            note=""):
        # `why` explains a miss; `note` is shown whether or not the row is met.
        rows.append({"carrier": carrier, "statistic": statistic, "kind": kind,
                     "requested": requested, "delivered": delivered,
                     "status": "ok" if ok else "missed",
                     "why": note if ok else why})

    for position, carrier in enumerate(ALL_CARRIERS):
        if energies[carrier] <= 0.0:
            continue
        series = profiles[COLUMN_NAMES[carrier]]
        stats = profile_statistics(series)
        peak = stats["peak_kw"]
        at_cap = float((series.to_numpy() >= peak * (1 - 1e-6)).mean())

        add(carrier, "annual_mwh", "exact", energies[carrier],
            stats["annual_mwh"],
            abs(stats["annual_mwh"] / energies[carrier] - 1) < 1e-6,
            "the energy rescaling failed; please report this as a bug")

        rating = spec.rated_kw.get(carrier)
        eta = load_factors[carrier]
        reached = abs(stats["load_factor"] / eta - 1) <= LOAD_FACTOR_TOLERANCE
        if rating is not None:
            add(carrier, "peak_kw", "ceiling", rating, peak,
                peak <= rating * (1 + 1e-6),
                "the cap failed; please report this as a bug")
            why = (f"its highest step is {peak:.0f} kW, below its rating of "
                   f"{rating:.0f} kW: the cap is never reached, so the profile's "
                   f"own peaks set the load factor. A rating well above the "
                   f"peak demand, such as an oversized nameplate, leaves the "
                   f"cap unused: give the measured peak demand instead, or use "
                   f"a class with a wider spread.")
        else:
            why = (f"its own peak stays below the cap that would hold a load "
                   f"factor of {eta:.3f}: the calendar and on/off state make "
                   f"the profile flatter than that. Ask for a load factor of "
                   f"at least {stats['load_factor']:.2f} "
                   f"(load_factor={{'{carrier}': ...}}), or build the class "
                   f"with loadcast.custom_class, which derives one that fits.")
        add(carrier, "load_factor", "exact", eta, stats["load_factor"],
            reached, why)

        # The spread aimed at: the class's fluctuation on this carrier's
        # calendar and on/off state. A class with no room for fluctuation aims,
        # in effect, at its calendar's and stops' own spread.
        own_spread = np.sqrt((1 + _spread(shapes[position])**2) * mask_term - 1)
        aimed_cv = float(np.sqrt((1 + own_spread**2) * (1 + residual**2) - 1))
        if at_cap > AT_CAP_SHARE:
            why_cv = (f"the cap holds {at_cap:.0%} of the steps at the peak, "
                      f"which flattens the top and trims the spread: the rating "
                      f"or load factor is tight for this class.")
        else:
            why_cv = ("the cap and the on/off state act after the spread is "
                      "set; this class lands this far from its aim (see "
                      "loadcast.bias_report).")
        note_cv = ""
        if collapsed:
            alike = ("carriers on the same calendar move in lockstep"
                     if process.off_fraction == 0 else
                     "carriers on the same calendar differ only through their "
                     "on/off states")
            note_cv = (f"the class's spread of {process.target_cv:.2f} is no "
                       f"more than its calendar and on/off state alone make "
                       f"({class_spread:.2f}), so it has no fluctuation beyond "
                       f"them, {alike}, and it aims at their spread instead. "
                       f"To add fluctuation, give the class a spread above "
                       f"{class_spread:.2f}.")
            why_cv = note_cv + " Beyond that, " + why_cv
        add(carrier, "cv", "aimed at", aimed_cv, stats["cv"],
            abs(stats["cv"] / aimed_cv - 1) <= CV_TOLERANCE, why_cv, note_cv)

        hourly = _hourly_persistence(series.to_numpy(), hours_per_step,
                                     stats["lag1"])
        if process.off_fraction > 0 and hourly < process.target_lag1:
            why_lag = ("the on/off state chops runs into pieces, which lowers "
                       "the persistence.")
        elif at_cap > AT_CAP_SHARE and hourly > process.target_lag1:
            why_lag = ("the cap trims the peaks that would break up a run, "
                       "which raises the persistence.")
        else:
            why_lag = ("the cap and the on/off state act after the persistence "
                       "is set (see loadcast.bias_report).")
        add(carrier, "lag1", "aimed at", process.target_lag1, hourly,
            abs(hourly - process.target_lag1) <= LAG1_TOLERANCE, why_lag)

    if energies["heat"] > 0 and energies["cold"] > 0:
        knob, floor, ceiling = _solve_knob(spec, hours_per_step, load_factors)
        offset = spec.carrier_lag_h.get("cold", 0) - spec.carrier_lag_h.get("heat", 0)
        delivered = float(profiles["heat_kw"].corr(profiles["cold_kw"]))
        if offset != 0:
            rows.append({
                "carrier": "heat-cold", "statistic": "correlation",
                "kind": "aimed at", "requested": spec.correlation_target,
                "delivered": np.nan, "status": "not checked",
                "why": ("with a lag the fluctuation is offset but the calendar "
                        "is not, so no single offset shows the requested "
                        "correlation: it is the one the same spec gives "
                        "without the lag.")})
        elif spec.carrier_correlation is None:
            requested = min(max(spec.correlation_target, floor), ceiling)
            add("heat-cold", "correlation", "default", requested, delivered,
                abs(delivered - requested) <= CORRELATION_TOLERANCE,
                "the solver did not converge; please report this as a bug")
        else:
            target = spec.correlation_target
            if target < floor - CORRELATION_TOLERANCE:
                why = (f"{target:.2f} is below the floor of {floor:.2f}: the "
                       f"carriers share a calendar, so they move together "
                       f"even when their fluctuations are independent. Ask for "
                       f"at least {floor:.2f}, or give one carrier a calendar "
                       f"of its own (DemandSpec.calendars) if it truly runs on "
                       f"different hours.")
            elif target > ceiling + CORRELATION_TOLERANCE:
                why = (f"{target:.2f} is above the highest correlation "
                       f"reachable, {ceiling:.2f}: the carriers' calendars or "
                       f"caps differ, so even identical fluctuations cannot "
                       f"line them up further.")
            else:
                why = "the solver did not converge; please report this as a bug"
            add("heat-cold", "correlation", "aimed at", target, delivered,
                abs(delivered - target) <= CORRELATION_TOLERANCE, why)

    return pd.DataFrame(rows, columns=["carrier", "statistic", "kind",
                                       "requested", "delivered", "status",
                                       "why"])


def warn_misses(spec: DemandSpec, profiles: pd.DataFrame) -> pd.DataFrame:
    """Issue a `TargetMissedWarning` for each miss in `delivery_report`."""
    report = delivery_report(spec, profiles)
    for row in report[report["status"] == "missed"].itertuples():
        warnings.warn(
            f"{row.carrier} {row.statistic}: asked {row.requested:.3f}, "
            f"delivered {row.delivered:.3f}, because {row.why}",
            TargetMissedWarning, stacklevel=4)
    return report
