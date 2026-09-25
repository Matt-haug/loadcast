"""The composition algebra, and the errors that protect it."""

import pytest

import loadcast as lc
from loadcast.spec import DemandSpec


def test_composition_sums_to_one():
    for ratio in (0.5, 2.0, 7.4, 45.0):
        for elec in (0.0, 0.2, 0.6, 0.95):
            spec = DemandSpec(heat_to_cold=ratio, elec_share=elec)
            assert sum(spec.composition) == pytest.approx(1.0, abs=1e-12)


def test_composition_matches_the_ratio():
    spec = DemandSpec(heat_to_cold=3.0, elec_share=0.2)
    heat, cold, elec = spec.composition
    assert heat / cold == pytest.approx(3.0, rel=1e-12)
    assert elec == pytest.approx(0.2, abs=1e-12)
    # and the closed form: s_c = (1 - s_e)/(1 + k)
    assert cold == pytest.approx((1 - 0.2) / (1 + 3.0), rel=1e-12)


def test_no_cold_and_no_heat_are_both_representable():
    assert DemandSpec(heat_to_cold=None, elec_share=0.1).composition == (
        pytest.approx(0.9), 0.0, 0.1)
    assert DemandSpec(heat_to_cold=0.0, elec_share=0.1).composition == (
        0.0, pytest.approx(0.9), 0.1)


def test_from_composition_round_trips():
    spec = DemandSpec.from_composition((0.5, 0.25, 0.25))
    assert spec.composition == (pytest.approx(0.5), pytest.approx(0.25),
                                pytest.approx(0.25))


def test_from_composition_refuses_to_renormalise():
    """Silently rescaling would move the point the caller asked for."""
    with pytest.raises(ValueError, match="must sum to 1"):
        DemandSpec.from_composition((0.5, 0.3, 0.3))


def test_rejects_impossible_inputs():
    with pytest.raises(ValueError, match="annual_mwh"):
        DemandSpec(annual_mwh=0.0)
    with pytest.raises(ValueError, match="elec_share"):
        DemandSpec(elec_share=1.5)
    with pytest.raises(ValueError, match="heat_to_cold"):
        DemandSpec(heat_to_cold=-1.0)
    with pytest.raises(ValueError, match="carrier_correlation"):
        DemandSpec(carrier_correlation=2.0)
    with pytest.raises(ValueError, match="unknown carriers"):
        DemandSpec(carrier_lag_h={"steam": 4})


def test_unknown_process_class_names_the_alternatives():
    with pytest.raises(KeyError, match="unknown process class"):
        lc.get_class("definitely_not_a_class")


def test_annual_energy_by_carrier():
    spec = DemandSpec(annual_mwh=1000.0, heat_to_cold=3.0, elec_share=0.2)
    parts = spec.annual_mwh_by_carrier()
    assert sum(parts.values()) == pytest.approx(1000.0, rel=1e-12)
    assert parts["heat"] / parts["cold"] == pytest.approx(3.0, rel=1e-12)


def test_lags_default_to_zero():
    # heat, cold, elec, waste
    assert DemandSpec().lags == (0, 0, 0, 0)
    assert DemandSpec(carrier_lag_h={"cold": 6}).lags == (0, 6, 0, 0)
    assert DemandSpec(carrier_lag_h={"waste": 2}).lags == (0, 0, 0, 2)
