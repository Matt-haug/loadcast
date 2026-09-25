"""Diagnostics: what a generated profile actually turned out to be.

Four views, and between them they cover what anyone sizing equipment needs:

    profile_statistics   the four scalars the generator was asked for
    duration_curve       the load duration curve, sorted descending
    cross_correlogram    how the carriers line up, lag by lag
    integrated_drift     how far apart they drift over a storage window

The last two are the ones other generators cannot show you, because they have no
controllable cross-carrier structure to display.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["profile_statistics", "duration_curve", "cross_correlogram",
           "integrated_drift", "summary_table"]


def profile_statistics(series: pd.Series | np.ndarray) -> dict[str, float]:
    """Load factor, spread, persistence and idle fraction of one profile."""
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
        "annual_mwh": float(values.sum()) / 1000.0,
    }


def duration_curve(series: pd.Series | np.ndarray,
                   normalise: bool = True) -> np.ndarray:
    """Load duration curve: demand sorted from highest hour to lowest.

    Often the only thing an industrial site can actually supply about itself,
    and it encodes load factor, peak and idle fraction at once -- which is why
    it is the right thing to tune against.
    """
    values = np.sort(np.asarray(series, dtype=float))[::-1]
    if normalise and values.size and values.max() > 0:
        values = values / values.max()
    return values


def cross_correlogram(first: pd.Series | np.ndarray,
                      second: pd.Series | np.ndarray,
                      max_lag: int = 48) -> pd.DataFrame:
    """Correlation between two carriers as a function of lag, in hours.

    ``corr(first(t), second(t + lag))``, so a positive peak lag means `second`
    trails `first`.

    Read the *position* of the peak, not only its height. A lag and a weak
    coupling look identical at lag zero: as carriers are offset, the
    contemporaneous correlation decays towards the floor the shared calendar
    imposes, which is exactly where a small correlation would also put it. Only
    the correlogram separates the two.
    """
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.size != b.size:
        raise ValueError("series must be the same length")

    rows = []
    for lag in range(-int(max_lag), int(max_lag) + 1):
        if lag >= 0:
            x, y = a[:a.size - lag or None], b[lag:]
        else:
            x, y = a[-lag:], b[:b.size + lag or None]
        if x.size < 2 or x.std() == 0 or y.std() == 0:
            rows.append({"lag_h": lag, "correlation": np.nan})
            continue
        rows.append({"lag_h": lag,
                     "correlation": float(np.corrcoef(x, y)[0, 1])})
    return pd.DataFrame(rows)


def integrated_drift(first: pd.Series | np.ndarray,
                     second: pd.Series | np.ndarray,
                     window_h: int = 24) -> float:
    """Mean absolute drift between two carriers over a storage window.

    Each carrier is normalised to its own mean, so this measures *timing*
    mismatch and not a difference in size:

        D(t) = sum over the window of [ a(s)/mean(a) - b(s)/mean(b) ]

    A store does not sample a mismatch, it integrates one, so the quantity that
    sizes a buffer is the running integral rather than the instantaneous gap.
    Correlation is a single point of that picture -- the value at lag zero --
    and is blind to how long an excursion lasts. Two carrier pairs with
    identical correlation can differ severalfold here.
    """
    a = pd.Series(np.asarray(first, dtype=float))
    b = pd.Series(np.asarray(second, dtype=float))
    if a.mean() <= 0 or b.mean() <= 0:
        return float("nan")
    mismatch = a / a.mean() - b / b.mean()
    return float(mismatch.rolling(int(window_h)).sum().abs().mean())


def summary_table(frame: pd.DataFrame) -> pd.DataFrame:
    """`profile_statistics` for every carrier in a generated frame."""
    return pd.DataFrame(
        {column: profile_statistics(frame[column]) for column in frame.columns}
    ).T.round(4)
