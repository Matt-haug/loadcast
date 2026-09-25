"""What the generator promises exactly, rather than approximately.

Annual energy, composition and load factor are *imposed* -- by the two
rescalings and the capacity cap fixed point -- not fitted. If any of these
drifts, a study built on the output is solving a different problem from the one
it plotted, so they are checked to tight tolerances.
"""

import numpy as np
import pytest

import loadcast as lc


@pytest.mark.parametrize("process_class", lc.available_classes())
def test_annual_energy_is_exact(process_class):
    total = 12_345.0
    frame = lc.generate(annual_mwh=total, heat_to_cold=3.0, elec_share=0.25,
                        process_class=process_class)
    assert frame.sum().sum() / 1000.0 == pytest.approx(total, rel=1e-9)


@pytest.mark.parametrize("heat_to_cold", [0.5, 1.0, 2.0, 7.4, 45.0])
def test_heat_to_cold_ratio_is_exact(heat_to_cold):
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=heat_to_cold,
                        elec_share=0.2)
    ratio = frame["heat_kw"].sum() / frame["cold_kw"].sum()
    assert ratio == pytest.approx(heat_to_cold, rel=1e-9)


@pytest.mark.parametrize("elec_share", [0.0, 0.05, 0.2, 0.5, 0.95])
def test_electricity_share_is_exact(elec_share):
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0,
                        elec_share=elec_share)
    share = frame["elec_kw"].sum() / frame.sum().sum()
    assert share == pytest.approx(elec_share, abs=1e-9)


@pytest.mark.parametrize("process_class", lc.available_classes())
def test_load_factor_hits_the_target(process_class):
    """The capacity cap is a fixed point, so the load factor is imposed."""
    target = lc.get_class(process_class).target_load_factor
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class=process_class)
    for column in frame.columns:
        if frame[column].sum() <= 0:
            continue    # a carrier this site does not have
        achieved = lc.profile_statistics(frame[column])["load_factor"]
        assert achieved == pytest.approx(target, abs=0.02)


def test_profiles_are_strictly_positive():
    """The published generator this replaces emits negative power; exp() cannot."""
    for process_class in lc.available_classes():
        frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0,
                            elec_share=0.2, process_class=process_class)
        assert (frame.to_numpy() >= 0).all()


def test_same_seed_same_profiles():
    kwargs = dict(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2)
    first = lc.generate(seed=7, **kwargs)
    again = lc.generate(seed=7, **kwargs)
    different = lc.generate(seed=8, **kwargs)
    np.testing.assert_allclose(first.to_numpy(), again.to_numpy())
    assert not np.allclose(first.to_numpy(), different.to_numpy())


def test_no_cold_demand_is_representable():
    """`heat_to_cold=None` means a site with no cooling at all."""
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=None, elec_share=0.3)
    assert frame["cold_kw"].sum() == pytest.approx(0.0, abs=1e-9)
    assert frame["heat_kw"].sum() / 1000.0 == pytest.approx(7_000.0, rel=1e-9)
