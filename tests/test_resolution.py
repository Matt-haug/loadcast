"""Sub-hourly output, and what must not change when the grid gets finer.

Resolution is a rendering choice, not a change of site. Energy, mean power, load
factor and the *wall-clock* persistence all have to survive it; only the number
of rows changes.
"""

import numpy as np
import pandas as pd
import pytest

import loadcast as lc
from loadcast.generator import rescale_persistence, step_hours

FREQS = [("h", 1), ("30min", 2), ("15min", 4)]


def steps_per_hour(frame) -> int:
    return int(round(1.0 / step_hours(frame.index)))


@pytest.mark.parametrize("freq,expected", FREQS)
def test_step_length_is_inferred(freq, expected):
    frame = lc.generate(annual_mwh=1_000, heat_to_cold=2.0, elec_share=0.2,
                        freq=freq)
    assert steps_per_hour(frame) == expected
    assert len(frame) == 8760 * expected


@pytest.mark.parametrize("freq,mult", FREQS)
def test_energy_is_the_same_at_every_resolution(freq, mult):
    """Energy is power times elapsed hours, not power times step count."""
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        freq=freq)
    hours = len(frame) / mult
    total_mwh = frame.sum(axis=1).mean() * hours / 1000.0
    assert total_mwh == pytest.approx(10_000.0, rel=1e-9)


@pytest.mark.parametrize("freq,_", FREQS)
def test_load_factor_survives_resolution(freq, _):
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="semi_continuous", freq=freq)
    achieved = lc.profile_statistics(frame["heat_kw"])["load_factor"]
    assert achieved == pytest.approx(0.401, abs=0.02)


@pytest.mark.parametrize("freq,mult", FREQS)
def test_persistence_is_the_same_in_wall_clock_time(freq, mult):
    """An excursion must last the same number of hours at any resolution.

    An AR(1) decays as phi^k over k steps, so a finer grid needs a higher
    per-step coefficient. Raising the measured per-step value back to the power
    of the steps-per-hour recovers one comparable number.
    """
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="semi_continuous", freq=freq)
    per_step = lc.profile_statistics(frame["heat_kw"])["lag1"]
    hourly_equivalent = per_step ** mult
    assert hourly_equivalent == pytest.approx(0.86, abs=0.04)


def test_rescale_persistence_is_the_power_law():
    assert rescale_persistence(0.8, 1.0) == pytest.approx(0.8)
    assert rescale_persistence(0.8, 0.25) == pytest.approx(0.8 ** 0.25)
    # and it round-trips back over an hour
    quarter = rescale_persistence(0.79, 0.25)
    assert quarter ** 4 == pytest.approx(0.79, rel=1e-9)


@pytest.mark.parametrize("freq,mult", FREQS)
def test_lag_is_given_in_hours_at_every_resolution(freq, mult):
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="semi_continuous",
                        carrier_correlation=0.75, carrier_lag_h={"cold": 6},
                        freq=freq)
    correlogram = lc.cross_correlogram(frame["heat_kw"], frame["cold_kw"],
                                       max_lag=12 * mult)
    peak_steps = int(correlogram.loc[correlogram["correlation"].idxmax(),
                                     "lag_h"])
    assert peak_steps / mult == pytest.approx(6.0, abs=0.5)


def test_step_hours_ignores_a_single_odd_gap():
    """The median gap defines the resolution, so one seam cannot redefine it."""
    index = pd.DatetimeIndex(
        list(pd.date_range("2025-01-01", periods=50, freq="h"))
        + [pd.Timestamp("2025-01-03 12:00")]
    )
    assert step_hours(index) == pytest.approx(1.0)


# =============================================================================
# Any subset of carriers
# =============================================================================


SUBSETS = [
    ({"heat": 1.0}, ("heat",)),
    ({"cold": 1.0}, ("cold",)),
    ({"elec": 1.0}, ("elec",)),
    ({"heat": 0.8, "elec": 0.2}, ("heat", "elec")),
    ({"cold": 0.6, "elec": 0.4}, ("cold", "elec")),
    ({"heat": 0.7, "cold": 0.3}, ("heat", "cold")),
    ({"heat": 0.5, "cold": 0.25, "elec": 0.25}, ("heat", "cold", "elec")),
]


@pytest.mark.parametrize("shares,active", SUBSETS)
def test_any_subset_of_carriers(shares, active):
    spec = lc.DemandSpec.from_shares(shares, annual_mwh=10_000)
    assert spec.active_carriers == active

    frame = lc.generate(spec)
    # The schema does not depend on the spec: every column always exists.
    assert list(frame.columns) == ["heat_kw", "cold_kw", "elec_kw", "waste_kw"]

    energy = frame.sum() / 1000.0
    # Waste heat is not bought, so it is not part of the demand budget.
    assert energy[["heat_kw", "cold_kw", "elec_kw"]].sum() == pytest.approx(
        10_000.0, rel=1e-9)
    assert energy["waste_kw"] == 0.0
    for carrier, column in (("heat", "heat_kw"), ("cold", "cold_kw"),
                            ("elec", "elec_kw")):
        expected = 10_000.0 * shares.get(carrier, 0.0)
        assert energy[column] == pytest.approx(expected, rel=1e-9)


def test_from_shares_rejects_bad_input():
    with pytest.raises(ValueError, match="must sum to 1"):
        lc.DemandSpec.from_shares({"heat": 0.5, "elec": 0.2})
    with pytest.raises(ValueError, match="unknown carriers"):
        lc.DemandSpec.from_shares({"steam": 1.0})
    with pytest.raises(ValueError, match="at least one carrier"):
        lc.DemandSpec.from_shares({})


def test_single_carrier_skips_the_correlation_solve():
    """With one carrier there is nothing to correlate, so nothing is solved."""
    spec = lc.DemandSpec.from_shares({"heat": 1.0}, annual_mwh=1_000)
    frame = lc.generate(spec)
    assert frame["heat_kw"].sum() > 0
    assert frame["cold_kw"].sum() == 0.0
    assert frame["elec_kw"].sum() == 0.0


# =============================================================================
# Waste heat: a by-product, not a demand
# =============================================================================


def test_waste_is_sized_off_heat_and_not_from_the_demand_budget():
    spec = lc.DemandSpec(annual_mwh=10_000, heat_to_cold=4.0, elec_share=0.2,
                         waste_to_heat=0.8)
    frame = lc.generate(spec)
    energy = frame.sum() / 1000.0

    # The site still consumes exactly what it was asked to consume.
    assert energy[["heat_kw", "cold_kw", "elec_kw"]].sum() == pytest.approx(
        10_000.0, rel=1e-9)
    # And rejects 0.8 kWh per kWh of process heat on top.
    assert energy["waste_kw"] / energy["heat_kw"] == pytest.approx(0.8,
                                                                  rel=1e-9)
    assert spec.waste_mwh == pytest.approx(energy["waste_kw"], rel=1e-9)


def test_waste_is_not_a_deterministic_multiple_of_heat():
    """It carries its own residual, so its correlation is a knob, not 1.000.

    Deriving waste heat as a fixed fraction of the heat demand would reintroduce
    exactly the perfect-coupling artefact this package exists to avoid.
    """
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=4.0, elec_share=0.2,
                        carrier_correlation=0.75, waste_to_heat=0.8)
    achieved = float(frame["heat_kw"].corr(frame["waste_kw"]))
    assert 0.2 < achieved < 0.99


def test_waste_takes_its_own_lag():
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=4.0, elec_share=0.2,
                        carrier_correlation=0.75, waste_to_heat=0.8,
                        carrier_lag_h={"waste": 3})
    correlogram = lc.cross_correlogram(frame["heat_kw"], frame["waste_kw"],
                                       max_lag=12)
    peak = int(correlogram.loc[correlogram["correlation"].idxmax(), "lag_h"])
    assert peak == pytest.approx(3, abs=1)


def test_no_waste_by_default():
    assert lc.generate(annual_mwh=1_000)["waste_kw"].sum() == 0.0
    with pytest.raises(ValueError, match="waste_to_heat"):
        lc.DemandSpec(waste_to_heat=-0.5)
