"""Process classes: how peaky an industrial process is, and on what rhythm.

A process class bundles everything the generator needs that is *not* specific to
one site: the calendar rhythm (month, day-of-week, hour-of-day factors) and the
three statistics that describe how the load fluctuates around it (load factor,
coefficient of variation, lag-1 persistence), plus an on/off description for
processes that are genuinely intermittent rather than merely variable.

Each class is calibrated on one metered industrial site. The sites themselves
are not distributed -- what ships is the derived statistics and the calendar
factors, which are group means and carry no identifying information.

The four classes span the range the archive covers:

    continuous       runs around the clock, small excursions
    semi_continuous  weekday shift pattern with a weekend trough
    campaign         long runs separated by genuine shutdowns
    batch            strongly bimodal, most hours near zero

Choose one from the *process description* of the site you are modelling, not by
fitting to an answer you already have. If none fits, `loadcast.fitting` builds a
class from your own observed statistics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import numpy as np

__all__ = ["ProcessClass", "available_classes", "get_class", "load_classes",
           "register_class"]


@dataclass(frozen=True)
class ProcessClass:
    """One calibrated process rhythm.

    Attributes
    ----------
    name
        Identifier used in `DemandSpec.process_class`.
    month, dayofweek, hour
        Calendar factors, each normalised to mean one over a balanced calendar.
        `month` is indexed January..December, `dayofweek` Monday..Sunday, `hour`
        00..23. They carry *shape only*: the level comes from the spec.
    target_load_factor
        Mean over peak of the finished profile. Imposed exactly by the capacity
        cap, not fitted.
    target_cv
        Coefficient of variation of the finished profile, calendar included.
    target_lag1
        Lag-1 autocorrelation of the finished profile.
    mode
        ``"lognormal"`` for a process that varies continuously, ``"onoff"`` for
        one that genuinely stops. The choice is forced by the data: a lognormal
        with the right spread still puts a batch process's load factor at 0.02
        against 0.22 measured, because a lognormal tail is far longer than an
        on/off process at equal spread.
    off_fraction
        Share of hours in the off state. Zero for ``"lognormal"`` classes.
    off_level
        Load in the off state, as a fraction of the running level. Non-zero
        because real plants idle rather than stop.
    description
        The kind of process this rhythm was measured on.
    anchor_site
        Anonymised label of the metered site it was calibrated against.
    n_hours
        Length of the series it was calibrated on.
    """

    name: str
    month: tuple[float, ...]
    dayofweek: tuple[float, ...]
    hour: tuple[float, ...]
    target_load_factor: float
    target_cv: float
    target_lag1: float
    mode: str
    off_fraction: float
    off_level: float
    description: str
    anchor_site: str
    n_hours: int

    def __post_init__(self) -> None:
        if self.mode not in ("lognormal", "onoff"):
            raise ValueError(f"unknown mode {self.mode!r}")
        for field, expected in (("month", 12), ("dayofweek", 7), ("hour", 24)):
            got = len(getattr(self, field))
            if got != expected:
                raise ValueError(
                    f"{self.name}: {field} needs {expected} factors, got {got}"
                )

    def calendar(self, index) -> np.ndarray:
        """Calendar factor `S(t)` for every timestamp in `index`.

        The three periodic factors multiply. Each has mean one over a balanced
        calendar, so their product carries shape and no level -- which is what
        lets the same rhythm be reused at any plant size.
        """
        month = np.asarray(self.month, dtype=float)
        dayofweek = np.asarray(self.dayofweek, dtype=float)
        hour = np.asarray(self.hour, dtype=float)
        return (month[index.month - 1]
                * dayofweek[index.dayofweek]
                * hour[index.hour])


@lru_cache(maxsize=1)
def load_classes() -> dict[str, ProcessClass]:
    """Every calibrated process class shipped with the package."""
    source = resources.files("loadcast.data").joinpath("process_classes.json")
    raw = json.loads(source.read_text(encoding="utf-8"))

    classes: dict[str, ProcessClass] = {}
    for name, entry in raw.items():
        classes[name] = ProcessClass(
            name=name,
            month=tuple(entry["month"]),
            dayofweek=tuple(entry["dayofweek"]),
            hour=tuple(entry["hour"]),
            target_load_factor=float(entry["target_load_factor"]),
            target_cv=float(entry["target_cv"]),
            target_lag1=float(entry["target_lag1"]),
            mode=str(entry["mode"]),
            off_fraction=float(entry["off_fraction"]),
            off_level=float(entry["off_level"]),
            description=str(entry["description"]),
            anchor_site=str(entry["anchor_site"]),
            n_hours=int(entry["n_hours"]),
        )
    return classes


# Classes built at runtime from a user's own measurements. Kept apart from the
# shipped ones so `available_classes` can say which is which, and so nothing
# a user registers can silently shadow a calibrated class.
_REGISTERED: dict[str, ProcessClass] = {}


def register_class(process_class: ProcessClass, overwrite: bool = False) -> None:
    """Make a process class usable by name in a `DemandSpec`.

    Pair this with `loadcast.fitting.class_from_observations` to generate from
    statistics you measured yourself:

        own = class_from_observations("my_plant", 0.45, 0.6, 0.9)
        register_class(own)
        generate(process_class="my_plant", annual_mwh=5_000)
    """
    name = process_class.name
    if name in load_classes():
        raise ValueError(
            f"{name!r} is a calibrated class shipped with loadcast; "
            f"choose another name rather than shadowing it"
        )
    if name in _REGISTERED and not overwrite:
        raise ValueError(f"{name!r} is already registered; pass overwrite=True")
    _REGISTERED[name] = process_class


def available_classes(include_registered: bool = True) -> list[str]:
    """Names of the process classes that can be generated from."""
    names = set(load_classes())
    if include_registered:
        names |= set(_REGISTERED)
    return sorted(names)


def get_class(name: str) -> ProcessClass:
    """One process class by name, with a helpful error if it does not exist."""
    classes = load_classes()
    if name in classes:
        return classes[name]
    if name in _REGISTERED:
        return _REGISTERED[name]
    raise KeyError(
        f"unknown process class {name!r}; available: {available_classes()}. "
        f"To build one from your own measurements, see "
        f"loadcast.fitting.class_from_observations and register_class."
    )
