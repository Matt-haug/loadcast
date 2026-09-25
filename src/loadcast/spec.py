"""What to generate: one site's carriers, proportions, rhythm and timing.

The parameterisation is deliberately the one an engineer can answer from a site
visit or an energy bill, rather than the one the mathematics wants:

    annual_mwh      how much energy the site uses in a year
    heat_to_cold    how much more heat than cold it wants
    elec_share      what fraction of the total is electricity
    process_class   how the process runs: continuously, in shifts, in batches
    carrier_lag_h   how far the carriers are offset from one another
    carrier_correlation   how tightly they move together when not offset

The three shares are not independent -- they are a composition summing to one --
so asking for two numbers and deriving the third is both easier to answer and
impossible to make inconsistent.

Why a ratio and a share rather than three shares
------------------------------------------------
Given the heat:cold ratio ``k`` and the electricity share ``s_e``, the
composition follows from ``s_h + s_c + s_e = 1`` and ``s_h = k * s_c``:

    s_c = (1 - s_e) / (1 + k)
    s_h = k * s_c

so the shares are exact by construction and can never fail to sum to one. A
composition that silently renormalises somewhere in the middle is the easiest
way to get a study wrong, because the point you solved is then not the point you
plotted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

__all__ = ["CARRIERS", "ALL_CARRIERS", "DemandSpec"]

# The carriers a site *consumes*. These are a composition: they sum to one.
CARRIERS = ("heat", "cold", "elec")

# Waste heat is not one of them. It is a by-product the site rejects, not
# energy it buys, so it takes no share of the annual total and is sized
# relative to the heat demand instead.
ALL_CARRIERS = CARRIERS + ("waste",)

# Column names of the generated frame.
COLUMN_NAMES = {
    "heat": "heat_kw",
    "cold": "cold_kw",
    "elec": "elec_kw",
    "waste": "waste_kw",
}


def _shares_from_ratio(heat_to_cold: float | None,
                       elec_share: float) -> tuple[float, float, float]:
    """Composition `(s_h, s_c, s_e)` from a ratio and an electricity share."""
    if not 0.0 <= elec_share <= 1.0:
        raise ValueError(f"elec_share must be in [0, 1], got {elec_share}")
    thermal = 1.0 - elec_share

    if heat_to_cold is None or math.isinf(heat_to_cold):
        # No cooling demand at all: every thermal unit is heat.
        return (thermal, 0.0, elec_share)
    if heat_to_cold < 0.0:
        raise ValueError(f"heat_to_cold cannot be negative, got {heat_to_cold}")
    if heat_to_cold == 0.0:
        # No heat demand at all.
        return (0.0, thermal, elec_share)

    cold = thermal / (1.0 + heat_to_cold)
    return (heat_to_cold * cold, cold, elec_share)


@dataclass(frozen=True)
class DemandSpec:
    """One site to generate.

    Parameters
    ----------
    annual_mwh
        Total annual energy across all three carriers, MWh. The generated
        profiles reproduce this exactly.
    heat_to_cold
        Ratio of annual heat demand to annual cold demand. Use ``None`` (the
        default) for a site with no cooling demand, or ``0`` for one with no
        heat demand.
    elec_share
        Electricity as a fraction of the annual total.
    process_class
        Name of a calibrated rhythm; see `loadcast.available_classes()`.
    carrier_correlation
        Correlation wanted between the *finished* carrier profiles at their
        peak alignment. This is an observable, not the generator's internal
        knob -- the knob that delivers it is solved for. See
        `loadcast.fitting.solve_correlation_knob`.
    carrier_lag_h
        Hours by which each carrier's process fluctuation trails the others,
        as ``{"cold": 6}`` for cold demand following heat by six hours.
        Carriers not named have zero lag. The shared calendar is *not* shifted:
        a factory's opening hours are common to all its carriers, so only the
        process fluctuation is offset.

        This is an exogenous design parameter, not a fitted one. No public
        archive meters heat and refrigeration at one industrial site, so no
        heat-to-cold lag can be estimated from data; sweeping it is the
        honest treatment.
    seed
        Random seed. The same seed and spec always give the same profiles.
    label
        Optional name carried through for plotting and bookkeeping.

    Notes
    -----
    A lag and a weak correlation are indistinguishable from the contemporaneous
    correlation alone: as the lag grows, the measured lag-0 correlation decays
    towards the floor the shared calendar imposes, exactly where a small
    `carrier_correlation` would also put it. When sweeping the lag, hold
    `carrier_correlation` fixed -- it is defined at peak alignment, so the sweep
    then changes timing only and not coupling strength.
    """

    annual_mwh: float = 10_000.0
    heat_to_cold: float | None = None
    elec_share: float = 0.2
    process_class: str = "semi_continuous"
    carrier_correlation: float = 0.47
    carrier_lag_h: dict[str, int] = field(default_factory=dict)
    waste_to_heat: float | None = None
    seed: int = 42
    label: str = ""

    def __post_init__(self) -> None:
        if self.annual_mwh <= 0:
            raise ValueError(f"annual_mwh must be positive, got {self.annual_mwh}")
        if not -1.0 <= self.carrier_correlation <= 1.0:
            raise ValueError(
                f"carrier_correlation must be in [-1, 1], "
                f"got {self.carrier_correlation}"
            )
        unknown = set(self.carrier_lag_h) - set(ALL_CARRIERS)
        if unknown:
            raise ValueError(
                f"carrier_lag_h has unknown carriers {sorted(unknown)}; "
                f"expected any of {list(ALL_CARRIERS)}"
            )
        if self.waste_to_heat is not None and self.waste_to_heat < 0:
            raise ValueError(
                f"waste_to_heat cannot be negative, got {self.waste_to_heat}")
        # Validates elec_share and heat_to_cold, and fails now rather than deep
        # inside the generator.
        _shares_from_ratio(self.heat_to_cold, self.elec_share)

    @property
    def composition(self) -> tuple[float, float, float]:
        """Annual shares `(heat, cold, electricity)`, summing to one exactly."""
        return _shares_from_ratio(self.heat_to_cold, self.elec_share)

    @property
    def lags(self) -> tuple[int, ...]:
        """Lag in hours for each carrier, in `ALL_CARRIERS` order."""
        return tuple(int(self.carrier_lag_h.get(name, 0))
                     for name in ALL_CARRIERS)

    @property
    def waste_mwh(self) -> float:
        """Annual waste heat rejected, MWh.

        Sized off the heat demand rather than given a share of the annual total,
        because waste heat is not bought. A site consuming 10 GWh of process
        heat and rejecting 8 GWh of it has ``waste_to_heat = 0.8`` and still an
        ``annual_mwh`` of 10 000 for what it consumes.
        """
        if not self.waste_to_heat:
            return 0.0
        return self.annual_mwh * self.composition[0] * float(self.waste_to_heat)

    def annual_mwh_by_carrier(self) -> dict[str, float]:
        """Annual energy per carrier, MWh."""
        return {name: self.annual_mwh * share
                for name, share in zip(CARRIERS, self.composition)}

    @property
    def active_carriers(self) -> tuple[str, ...]:
        """Carriers with a non-zero share.

        A site that buys only electricity, or only heat and electricity, is a
        perfectly ordinary site. The generated frame always has all three
        columns so the schema is stable, but the ones not asked for are zero and
        the coincidence knobs do not apply to them.
        """
        return tuple(name for name, share in zip(CARRIERS, self.composition)
                     if share > 0.0)

    @classmethod
    def from_composition(cls, composition, **kwargs) -> "DemandSpec":
        """Build a spec from explicit shares `(heat, cold, electricity)`.

        For callers who already work in composition space, such as a simplex
        design over the three carriers. The shares must sum to one; they are not
        renormalised, because silently moving the point is worse than failing.
        """
        heat, cold, elec = (float(v) for v in composition)
        total = heat + cold + elec
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"composition must sum to 1, got {total:.9f}. Renormalising "
                f"silently would move the point you asked for."
            )
        if min(heat, cold, elec) < -1e-12:
            raise ValueError("composition shares cannot be negative")
        ratio = None if cold <= 0.0 else heat / cold
        return cls(heat_to_cold=ratio, elec_share=elec, **kwargs)

    @classmethod
    def from_shares(cls, shares: dict[str, float], **kwargs) -> "DemandSpec":
        """Build a spec from whichever carriers a site actually has.

            DemandSpec.from_shares({"heat": 1.0})                  # heat only
            DemandSpec.from_shares({"cold": 0.7, "elec": 0.3})     # no heat
            DemandSpec.from_shares({"heat": 0.5, "cold": 0.25, "elec": 0.25})

        Carriers left out are zero. The shares given must sum to one -- a single
        carrier is written as ``{"heat": 1.0}`` rather than ``{"heat": 1}``
        meaning "all of it", so that a typo cannot silently rescale the site.
        """
        unknown = set(shares) - set(CARRIERS)
        if unknown:
            raise ValueError(
                f"unknown carriers {sorted(unknown)}; expected any of "
                f"{list(CARRIERS)}"
            )
        if not shares:
            raise ValueError("at least one carrier must have a share")
        values = {name: float(shares.get(name, 0.0)) for name in CARRIERS}
        total = sum(values.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"shares must sum to 1, got {total:.9f}. Renormalising silently "
                f"would move the point you asked for."
            )
        return cls.from_composition(
            (values["heat"], values["cold"], values["elec"]), **kwargs)
