"""The calendar: when a site runs, as factors of mean one.

A calendar is the deterministic part of a profile: the factor S(t) that every
hour of demand is multiplied by, before the fluctuation. It holds

    month   12 factors, January to December
    week    168 factors, Monday 00:00 to Sunday 23:00

and S(t) is the month factor times the hour-of-week factor. Both sets are
normalised to mean one, so a calendar carries shape and no level: the level
comes from the annual energy.

A full week of 168 factors, rather than a weekday factor times an hour factor,
lets each day keep its own hours: a Saturday morning shift, or a night shift on
weekdays only. The shipped classes were calibrated as weekday times hour, and
`Calendar.of` writes them out as a week.

Four ways to build one, from what a user is likely to have:

    Calendar.of("semi_continuous")          a shipped class's calendar
    Calendar.from_schedule([...])           the shifts the site runs
    Calendar.from_series(meter)             a metered series, a week or longer
    calendar.with_monthly_energy([...])     twelve monthly bills

What a calendar cannot do: the month scales the whole week, so the daily
pattern cannot change with the season.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = ["Calendar"]

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _normalised(values, length: int, what: str) -> tuple[float, ...]:
    array = np.asarray(values, dtype=float).ravel()
    if array.size != length:
        raise ValueError(f"{what} needs {length} factors, got {array.size}")
    if not np.all(np.isfinite(array)) or np.any(array < 0):
        raise ValueError(f"{what} factors must be finite and non-negative")
    mean = float(array.mean())
    if mean <= 0:
        raise ValueError(f"{what} factors cannot all be zero")
    return tuple(float(v) for v in array / mean)


def _parse_days(days: str) -> list[int]:
    """'Mon-Fri', 'Sat', 'Mon,Wed,Fri', 'daily' -> weekday numbers, Monday 0."""
    text = days.strip().lower()
    if text in ("daily", "all", "mon-sun"):
        return list(range(7))
    chosen: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            first, last = (_DAYS.index(p.strip()[:3]) for p in part.split("-"))
            span = range(first, last + 1) if first <= last else \
                list(range(first, 7)) + list(range(0, last + 1))
            chosen.extend(span)
        else:
            chosen.append(_DAYS.index(part[:3]))
    return sorted(set(chosen))


@dataclass(frozen=True)
class Calendar:
    """Month and hour-of-week factors, each normalised to mean one.

    Both sets are rescaled to mean one on construction, so any positive numbers
    in the right proportions will do.

    Parameters
    ----------
    month
        Twelve factors, January to December.
    week
        168 factors, Monday 00:00 to Sunday 23:00.
    """

    month: tuple[float, ...]
    week: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "month", _normalised(self.month, 12, "month"))
        object.__setattr__(self, "week", _normalised(self.week, 168, "week"))

    # ------------------------------------------------------------------ use

    def factors(self, index: pd.DatetimeIndex) -> np.ndarray:
        """The calendar factor S(t) for every timestamp of `index`."""
        month = np.asarray(self.month)[index.month - 1]
        week = np.asarray(self.week)[index.dayofweek * 24 + index.hour]
        return month * week

    def spread(self, year: int = 2025) -> float:
        """Coefficient of variation of S(t) over an hourly year.

        The part of a profile's spread the calendar alone accounts for.
        """
        index = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01",
                              freq="h")[:-1]
        values = self.factors(index)
        return float(values.std() / values.mean())

    # ------------------------------------------------------------ builders

    @classmethod
    def flat(cls) -> "Calendar":
        """The same factor at every hour of the year: a site that never varies."""
        return cls(month=(1.0,) * 12, week=(1.0,) * 168)

    @classmethod
    def of(cls, process_class) -> "Calendar":
        """The calendar of a process class, shipped or your own.

        Takes a class name or a `ProcessClass`.
        """
        from .classes import ProcessClass, get_class

        process = (process_class if isinstance(process_class, ProcessClass)
                   else get_class(process_class))
        if process.week is not None:
            return cls(month=process.month, week=process.week)
        week = np.outer(process.dayofweek, process.hour).ravel()
        return cls(month=process.month, week=week)

    @classmethod
    def from_schedule(cls, shifts, base_load: float = 0.0,
                      monthly_energy=None, months=None,
                      year: int = 2025) -> "Calendar":
        """A calendar from the hours a site runs.

        Parameters
        ----------
        shifts
            One entry per block of running hours, as ``(days, start_h,
            end_h)`` or ``(days, start_h, end_h, level)``. `days` is a string
            such as ``"Mon-Fri"``, ``"Sat"``, ``"Mon,Wed"`` or ``"daily"``;
            hours run from `start_h` up to `end_h`, and a block that ends before
            it starts runs past midnight into the next day. `level` is the
            demand in that block relative to a full shift, 1 by default.
        base_load
            Demand outside every block, relative to a full shift: what the site
            draws when it is not producing (space heating, standby, cold rooms
            kept cold). Read it off a meter at night or at the weekend.
        monthly_energy
            Optional twelve monthly energies, as on the bills, to set the month
            factors; see `with_monthly_energy`.
        months
            Optional twelve month factors given directly, such as a shipped
            class's: ``Calendar.of("semi_continuous").month``. A schedule says
            nothing about seasons, so without either the months are flat.
        year
            Year whose weekdays the monthly energies are counted on.

        Examples
        --------
        Two shifts on weekdays, a morning shift on Saturday, a quarter of the
        load the rest of the time, and the seasons of the shipped
        semi-continuous class::

            Calendar.from_schedule([("Mon-Fri", 6, 22), ("Sat", 6, 14)],
                                   base_load=0.25,
                                   months=Calendar.of("semi_continuous").month)
        """
        if monthly_energy is not None and months is not None:
            raise ValueError("give monthly_energy or months, not both")
        if not 0.0 <= base_load <= 1.0:
            raise ValueError(f"base_load must be in [0, 1], got {base_load}")
        week = np.full(168, float(base_load))
        for entry in shifts:
            if len(entry) not in (3, 4):
                raise ValueError(
                    f"each shift is (days, start_h, end_h[, level]); got {entry}")
            days, start, end = entry[0], int(entry[1]), int(entry[2])
            level = float(entry[3]) if len(entry) == 4 else 1.0
            if not (0 <= start <= 24 and 0 <= end <= 24) or start == end:
                raise ValueError(f"shift hours must be in 0-24 and differ: {entry}")
            length = end - start if end > start else end + 24 - start
            for day in _parse_days(days):
                for offset in range(length):
                    slot = (day * 24 + start + offset) % 168
                    week[slot] = max(week[slot], level)
        built = cls(month=(1.0,) * 12 if months is None else months, week=week)
        if monthly_energy is not None:
            built = built.with_monthly_energy(monthly_energy, year=year)
        return built

    @classmethod
    def from_series(cls, series: pd.Series) -> "Calendar":
        """The calendar of a metered series.

        Month and hour-of-week factors are estimated together, in turn: each
        month's factor is its energy over the energy its hours would hold at
        the current week factors, and each of the 168 week factors is the mean
        of the series at that hour, divided by its month's factor. A few rounds
        converge, and a season does not leak into the week, nor a month's count
        of working days into its factor. The month factors need all twelve
        months, and are left flat when the series is shorter; add them from
        monthly bills with `with_monthly_energy`.

        Sub-hourly series are averaged to hours first. It needs at least one
        full week.
        """
        if not isinstance(series.index, pd.DatetimeIndex):
            raise TypeError("series needs a DatetimeIndex")
        hourly = series.astype(float).resample("h").mean().dropna()
        if hourly.empty or hourly.mean() <= 0:
            raise ValueError("series must have positive values")
        values = hourly.to_numpy()
        slot = np.asarray(hourly.index.dayofweek * 24 + hourly.index.hour)
        period = np.asarray(hourly.index.year * 12 + hourly.index.month - 1)
        if len(np.unique(slot)) < 168:
            raise ValueError(
                f"series covers {len(np.unique(slot))} of the 168 hours of the "
                f"week; it needs at least one full week")

        periods, position = np.unique(period, return_inverse=True)
        week = np.bincount(slot, values, 168) / np.bincount(slot, None, 168)
        for _ in range(50):
            held = np.bincount(position, week[slot], len(periods))
            month = np.bincount(position, values, len(periods)) / held
            previous = week
            week = (np.bincount(slot, values / month[position], 168)
                    / np.bincount(slot, None, 168))
            if np.allclose(week, previous, rtol=1e-12, atol=0.0):
                break

        calendar_month = np.asarray(periods % 12)
        if len(np.unique(calendar_month)) == 12:
            # Average the factor of each calendar month over the years covered.
            factors = (np.bincount(calendar_month, month, 12)
                       / np.bincount(calendar_month, None, 12))
        else:
            factors = np.ones(12)
        return cls(month=factors, week=week)

    # ----------------------------------------------------------- adjusting

    def with_monthly_energy(self, energies, year: int = 2025) -> "Calendar":
        """Set the month factors from twelve monthly energies, such as bills.

        A month's energy depends on its activity and on how many running hours
        it holds: a month with five Mondays holds more. Each month factor is
        therefore its energy divided by the sum of the week factors over that
        month's hours, counted on `year`. A month the site was shut has an
        energy near zero, and gets a factor near zero.
        """
        energies = np.asarray(energies, dtype=float).ravel()
        if energies.size != 12:
            raise ValueError(f"need 12 monthly energies, got {energies.size}")
        index = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01",
                              freq="h")[:-1]
        weekly = np.asarray(self.week)[index.dayofweek * 24 + index.hour]
        held = pd.Series(weekly, index=index).groupby(index.month).sum()
        factors = energies / held.sort_index().to_numpy()
        return Calendar(month=factors, week=self.week)

    def with_months(self, factors) -> "Calendar":
        """The same week, with twelve month factors given directly."""
        return Calendar(month=factors, week=self.week)

    def describe(self) -> pd.DataFrame:
        """The week as a 7 x 24 table, days down and hours across."""
        table = pd.DataFrame(np.asarray(self.week).reshape(7, 24),
                             index=[d.capitalize() for d in _DAYS])
        table.columns.name = "hour"
        return table.round(3)
