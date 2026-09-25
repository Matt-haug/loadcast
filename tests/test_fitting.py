"""Generating from statistics you measured yourself.

This is the path that separates a demand generator from a random signal
generator: you give it observables, not parameters.
"""

import pytest

import loadcast as lc
from loadcast import fitting


def test_class_from_observations_reproduces_its_inputs():
    """Give it a load factor and a spread; get them back out of the profile."""
    own = fitting.class_from_observations(
        "test_plant", load_factor=0.45, cv=0.60, lag1=0.90,
        calendar_from="semi_continuous",
    )
    lc.register_class(own, overwrite=True)

    frame = lc.generate(annual_mwh=5_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="test_plant")
    statistics = lc.profile_statistics(frame["heat_kw"])
    assert statistics["load_factor"] == pytest.approx(0.45, abs=0.02)
    assert statistics["cv"] == pytest.approx(0.60, abs=0.12)


def test_registering_cannot_shadow_a_calibrated_class():
    clash = fitting.class_from_observations("batch", 0.4, 0.5, 0.9)
    with pytest.raises(ValueError, match="shipped with loadcast"):
        lc.register_class(clash)


def test_class_from_observations_validates():
    with pytest.raises(ValueError, match="load_factor"):
        fitting.class_from_observations("x", load_factor=1.5, cv=0.5, lag1=0.9)
    with pytest.raises(ValueError, match="cv"):
        fitting.class_from_observations("x", load_factor=0.5, cv=-1, lag1=0.9)
    with pytest.raises(ValueError, match="lag1"):
        fitting.class_from_observations("x", load_factor=0.5, cv=0.5, lag1=1.5)


def test_off_fraction_switches_the_mode():
    """A spread alone makes a profile low; only a mask makes it off."""
    smooth = fitting.class_from_observations("s", 0.5, 0.6, 0.9)
    bimodal = fitting.class_from_observations("b", 0.5, 0.6, 0.9,
                                              off_fraction=0.35)
    assert smooth.mode == "lognormal"
    assert bimodal.mode == "onoff"

    lc.register_class(bimodal, overwrite=True)
    frame = lc.generate(annual_mwh=5_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="b")
    assert lc.profile_statistics(frame["heat_kw"])["idle_fraction"] > 0.15


@pytest.mark.parametrize("process_class", lc.available_classes(False))
def test_correlation_floor_is_between_zero_and_one(process_class):
    floor = lc.correlation_floor(process_class)
    assert 0.0 <= floor <= 1.0


def test_correlation_transfer_is_monotone_and_starts_at_the_floor():
    calendar_cv, residual_cv = 0.31, 0.34
    values = [fitting.correlation_transfer(rho, calendar_cv, residual_cv)
              for rho in (0.0, 0.2, 0.5, 0.8, 0.99)]
    assert values == sorted(values)
    expected_floor = calendar_cv**2 / (
        (1 + calendar_cv**2) * (1 + residual_cv**2) - 1)
    assert values[0] == pytest.approx(expected_floor, rel=1e-9)
    assert values[-1] == pytest.approx(1.0, abs=0.05)


# =============================================================================
# The bias, pinned
# =============================================================================


def test_imposed_statistics_are_exact_and_emergent_ones_are_not():
    """Load factor is imposed; spread and persistence are only aimed at.

    Pinned so the gap cannot widen unnoticed. The sign of the persistence bias
    differs by class: a capacity cap trims peaks and lengthens runs, while an
    on/off mask chops them up, so unmasked classes come out stickier than target
    and masked ones looser.
    """
    report = fitting.bias_report(seeds=2)
    for name, row in report.iterrows():
        assert row["load_factor_mean"] == pytest.approx(
            row["load_factor_target"], abs=0.005), name
        assert abs(row["cv_bias"]) < 0.35, name
        assert abs(row["lag1_bias"]) < 0.25, name


def test_recursive_refitting_degenerates():
    """Refitting on generated output compounds the bias -- so never do it.

    This is the classic degeneration of a model retrained on its own output.
    The package never takes this path; the test exists to document that the
    hazard is real and to fail if someone wires it into the library by accident.
    """
    base = lc.get_class("semi_continuous")
    lf, cv, lag1 = (base.target_load_factor, base.target_cv, base.target_lag1)
    first = None
    for iteration in range(5):
        own = fitting.class_from_observations(
            f"_recur{iteration}", load_factor=min(max(lf, 0.02), 0.98),
            cv=cv, lag1=min(lag1, 0.99), calendar_from="semi_continuous")
        lc.register_class(own, overwrite=True)
        frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0,
                            elec_share=0.2, process_class=f"_recur{iteration}",
                            seed=200 + iteration)
        statistics = lc.profile_statistics(frame["heat_kw"])
        lf, cv, lag1 = (statistics["load_factor"], statistics["cv"],
                        statistics["lag1"])
        if first is None:
            first = lag1

    # Persistence ratchets up and away from where it started.
    assert lag1 > first + 0.05
    assert lag1 > base.target_lag1 + 0.10
