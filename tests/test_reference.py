"""Indicative published values, and the caveats that travel with them."""

import pytest

import loadcast as lc
from loadcast import reference


def test_every_source_is_peer_reviewed_and_carries_a_caveat():
    table = reference.sources()
    assert len(table) == 4
    assert table["peer_reviewed"].all()
    for name in table.index:
        assert reference.citation(name).strip()
        assert table.loc[name, "caveat"].strip()


def test_industry_composition_sums_to_one():
    composition = reference.industry_composition()
    total = composition["heat"] + composition["cold"] + composition["elec"]
    assert total == pytest.approx(1.0, abs=0.001)
    assert composition["heat"] / composition["cold"] == pytest.approx(
        composition["heat_to_cold"], rel=0.02)


def test_it_can_drive_a_spec():
    """The whole point: a published anchor becomes a runnable starting spec."""
    composition = reference.industry_composition()
    spec = lc.DemandSpec(annual_mwh=10_000,
                         heat_to_cold=composition["heat_to_cold"],
                         elec_share=composition["elec"],
                         waste_to_heat=reference.waste_to_heat("Paper"))
    frame = lc.generate(spec)
    energy = frame.sum() / 1000.0
    assert energy[["heat_kw", "cold_kw", "elec_kw"]].sum() == pytest.approx(
        10_000.0, rel=1e-9)
    assert energy["waste_kw"] > 0


def test_subsector_ranges_are_ranges_not_points():
    """Rehfeldt's two datasets disagree; the module must not average them."""
    low, high = reference.heat_to_cold_range("Food, beverages and tobacco")
    assert low == pytest.approx(4.6, abs=0.3)
    assert high == pytest.approx(7.5, abs=0.3)
    low, high = reference.heat_to_cold_range("Chemicals")
    assert high > 2 * low      # the disagreement is larger than a rounding


def test_subsectors_without_cooling_are_reported_as_such():
    """No cooling in a dataset means an unbounded ratio, not a big one."""
    assert reference.heat_to_cold_range("Non-metallic minerals") == (None, None)
    # One dataset with cooling, one without: bounded below only.
    low, high = reference.heat_to_cold_range("Paper")
    assert low == pytest.approx(22.8, abs=1.0)
    assert high is None


def test_ratio_follows_from_the_cooling_share():
    """heat:cold is the non-cooling share over the cooling share, nothing else."""
    bands = reference.temperature_bands("rehfeldt")
    for subsector in reference.subsectors():
        cooling = bands.loc[subsector, "cooling"]
        low, high = reference.heat_to_cold_range(subsector)
        present = sorted((100 - c) / c for c in cooling if c > 0)
        if present:
            assert low == pytest.approx(present[0], abs=0.05)


def test_band_shares_sum_to_one_hundred():
    for source in ("naegler", "rehfeldt"):
        table = reference.temperature_bands(source)
        # Bands run from the coldest to the hottest.
        assert table.columns[0] in ("space_heat_hot_water", "cooling")
        assert "above" in table.columns[-1]
        assert (table >= 0).all().all()
        assert table.sum(axis=1).to_numpy() == pytest.approx(100.0, abs=0.15)


def test_naegler_transport_reaches_the_500_1000_band():
    """Fig. 3 gives transport a 500-1000 C band of ~5 %; an earlier digitising
    put it in 100-500 C instead."""
    row = reference.temperature_bands("naegler").loc["Transport"]
    assert row["process_500_1000c"] == pytest.approx(5.6, abs=1.0)
    assert row["process_100_500c"] == pytest.approx(11.9, abs=1.0)


def test_unknown_names_are_rejected():
    with pytest.raises(KeyError, match="unknown subsector"):
        reference.heat_to_cold_range("Widgets")
    with pytest.raises(KeyError, match="unknown sector"):
        reference.waste_to_heat("Widgets")
    with pytest.raises(KeyError, match="unknown source"):
        reference.citation("hearsay")
    with pytest.raises(KeyError, match="unknown source"):
        reference.temperature_bands("hearsay")


def test_temperatures_are_ordered_and_plausible():
    table = reference.sector_temperatures()
    for sector in table.index:
        row = table.loc[sector]
        assert row["process_p25_c"] <= row["process_median_c"] <= row["process_p75_c"]
        # Waste heat is rejected below the process it came from.
        assert row["waste_median_c"] < row["process_median_c"]
