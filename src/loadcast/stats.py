"""Diagnostics: what a generated profile actually turned out to be.

Four views, which between them cover what sizing equipment needs:

    profile_statistics   the four statistics the generator was asked for
    duration_curve       the load duration curve, sorted from the highest hour
    cross_correlogram    how the carriers line up, offset by offset
    integrated_drift     how far apart they drift over a storage window

The last two describe how the carriers relate, which the generator lets you
set.

Offsets, windows and energies are in hours at any step length. Each function
reads the length of a step from the series' `DatetimeIndex`, as the generator
writes it; for a bare array, pass `hours_per_step` (one hour if omitted).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .generator import step_hours

__all__ = ["profile_statistics", "duration_curve", "cross_correlogram",
           "integrated_drift", "summary_table"]


def _hours_per_step(series, hours_per_step: float | None) -> float:
    """Length of one step in hours: given, read off the index, or one hour."""
    if hours_per_step is not None:
        if hours_per_step <= 0:
            raise ValueError(
                f"hours_per_step must be positive, got {hours_per_step}")
        return float(hours_per_step)
    index = getattr(series, "index", None)
    if isinstance(index, pd.DatetimeIndex) and len(index) > 1:
        return step_hours(index)
    return 1.0


def profile_statistics(series: pd.Series | np.ndarray,
                       hours_per_step: float | None = None) -> dict[str, float]:
    """Load factor, spread, persistence and idle fraction of one profile.

    `lag1` is the correlation of the series with itself one *step* later, as
    the generator's persistence is defined per step; on a series of 15-minute
    steps, raise it to the power 4 for the value one hour later. `annual_mwh`
    is power times elapsed hours, so it is right at any step length.
    """
    hours = _hours_per_step(series, hours_per_step)
    values = np.asarray(series, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or values.max() <= 0:
        return {"mean_kw": 0.0, "peak_kw": 0.0, "load_factor": 0.0,
                "cv": 0.0, "lag1": 0.0, "idle_fraction": 0.0,
                "annual_mwh": 0.0}

    mean = float(values.mean())
    peak = float(values.max())
    centred = values - mean
    denominator = float((centred**2).sum())
    lag1 = (float((centred[:-1] * centred[1:]).sum() / denominator)
            if denominator > 0 else 0.0)
    return {
        "mean_kw": mean,
        "peak_kw": peak,
        "load_factor": mean / peak,
        "cv": float(values.std() / mean),
        "lag1": lag1,
        # "Idle" is judged against the peak, not the mean, so the number means
        # the same thing for a flat process and a spiky one.
        "idle_fraction": float((values < 0.05 * peak).mean()),
        "annual_mwh": float(values.sum()) * hours / 1000.0,
    }


def duration_curve(series: pd.Series | np.ndarray,
                   normalise: bool = True) -> np.ndarray:
    """Load duration curve: demand sorted from the highest hour to the lowest.

    It is often the only thing an industrial site can supply about itself, and
    it shows the load factor, the peak and the idle fraction at once, which
    makes it the right thing to compare against.
    """
    values = np.sort(np.asarray(series, dtype=float))[::-1]
    if normalise and values.size and values.max() > 0:
        values = values / values.max()
    return values


def cross_correlogram(first: pd.Series | np.ndarray,
                      second: pd.Series | np.ndarray,
                      max_lag: float = 48,
                      hours_per_step: float | None = None) -> pd.DataFrame:
    """Correlation between two carriers at each offset, in hours.

    ``corr(first(t), second(t + lag))`` for every whole step from `-max_lag` to
    `max_lag` hours, so a peak at a positive lag means `second` trails `first`.
    The `lag_h` column is in hours at any step length: a 15-minute series gives
    a row every 0.25 h.

    Read the *position* of the peak, not only its height. At zero offset, a lag
    and a weak coupling look the same: as carriers are offset, their
    correlation at zero offset falls towards the floor the shared calendar
    imposes, which is exactly where a small correlation would also put it. Only
    the correlogram separates the two.
    """
    hours = _hours_per_step(first, hours_per_step)
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.size != b.size:
        raise ValueError("series must be the same length")

    max_steps = int(round(float(max_lag) / hours))
    # Whole hours stay integers, so an hourly correlogram reads as before.
    whole = float(hours).is_integer()
    rows = []
    for lag in range(-max_steps, max_steps + 1):
        offset = lag * int(hours) if whole else lag * hours
        if lag >= 0:
            x, y = a[:a.size - lag or None], b[lag:]
        else:
            x, y = a[-lag:], b[:b.size + lag or None]
        if x.size < 2 or x.std() == 0 or y.std() == 0:
            rows.append({"lag_h": offset, "correlation": np.nan})
            continue
        rows.append({"lag_h": offset,
                     "correlation": float(np.corrcoef(x, y)[0, 1])})
    return pd.DataFrame(rows)


def integrated_drift(first: pd.Series | np.ndarray,
                     second: pd.Series | np.ndarray,
                     window_h: float = 24,
                     hours_per_step: float | None = None) -> float:
    """Mean absolute drift between two carriers over a storage window.

    Each carrier is divided by its own mean, so this measures a mismatch in
    *timing*, not in size:

        D(t) = sum over the window of [ a(s)/mean(a) - b(s)/mean(b) ] * h

    where ``h`` is the length of a step in hours, and the result is the mean of
    ``|D(t)|``, in hours of mean demand. A store does not see a mismatch hour
    by hour, it accumulates it, so what sizes a store is the mismatch summed
    over its window rather than the gap in one hour. The correlation is a
    single point of that picture, the value at zero offset, and is blind to how
    long an excursion lasts. Two carrier pairs with the same correlation can
    differ severalfold here.

    `window_h` is in hours at any step length; it is rounded to whole steps.
    """
    hours = _hours_per_step(first, hours_per_step)
    a = pd.Series(np.asarray(first, dtype=float))
    b = pd.Series(np.asarray(second, dtype=float))
    if a.mean() <= 0 or b.mean() <= 0:
        return float("nan")
    window = max(1, int(round(float(window_h) / hours)))
    mismatch = (a / a.mean() - b / b.mean()) * hours
    return float(mismatch.rolling(window).sum().abs().mean())


def summary_table(frame: pd.DataFrame) -> pd.DataFrame:
    """`profile_statistics` for every carrier in a generated frame.

    The step length is read from the frame's index, so `annual_mwh` is right at
    any resolution.
    """
    hours = _hours_per_step(frame, None)
    return pd.DataFrame(
        {column: profile_statistics(frame[column], hours_per_step=hours)
         for column in frame.columns}
    ).T.round(4)
