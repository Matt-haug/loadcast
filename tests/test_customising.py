"""Your own calendar, your own ratings, a shipped class adjusted, and the checks.

The shipped classes give a first result with no tuning; everything here is
what a user changes to fit a site, and what the generator says when a change
cannot be delivered as asked.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import loadcast as lc

YEAR = pd.date_range("2025-01-01", periods=8760, freq="h")
SITE = dict(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2, seed=1)


def quiet(spec):
    """Generate, failing on any TargetMissedWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", lc.TargetMissedWarning)
        return lc.generate(spec)


# =============================================================================
# Calendars
# =============================================================================


def test_calendar_factors_have_mean_one():
    calendar = lc.Calendar(month=range(1, 13), week=np.arange(1, 169))
    assert np.mean(calendar.month) == pytest.approx(1.0)
    assert np.mean(calendar.week) == pytest.approx(1.0)


def test_calendar_rejects_wrong_lengths_and_negatives():
    with pytest.raises(ValueError, match="168"):
        lc.Calendar(month=[1] * 12, week=[1] * 24)
    with pytest.raises(ValueError, match="non-negative"):
        lc.Calendar(month=[-1] + [1] * 11, week=[1] * 168)


def test_schedule_sets_running_hours_and_base_load():
    calendar = lc.Calendar.from_schedule([("Mon-Fri", 6, 22), ("Sat", 6, 14)],
                                         base_load=0.25)
    week = calendar.describe().to_numpy()
    running = week[0, 10]
    assert week[0, 3] / running == pytest.approx(0.25)     # Monday night
    assert week[5, 10] / running == pytest.approx(1.0)     # Saturday morning
    assert week[5, 16] / running == pytest.approx(0.25)    # Saturday afternoon
    assert week[6, 10] / running == pytest.approx(0.25)    # Sunday


def test_a_night_shift_runs_past_midnight():
    calendar = lc.Calendar.from_schedule([("Fri", 22, 6)], base_load=0.0)
    week = calendar.describe().to_numpy()
    assert week[4, 23] > 0 and week[5, 5] > 0      # Friday 23 h, Saturday 5 h
    assert week[5, 6] == 0 and week[4, 21] == 0


def test_a_shift_round_the_clock_is_flat():
    calendar = lc.Calendar.from_schedule([("daily", 0, 24)])
    assert calendar == lc.Calendar.flat()


def test_series_gives_back_its_calendar():
    """A noiseless series built from a calendar returns that calendar."""
    truth = lc.Calendar.from_schedule([("Mon-Fri", 6, 22)], base_load=0.3)
    truth = truth.with_months(np.linspace(0.8, 1.2, 12))
    series = pd.Series(truth.factors(YEAR) * 500.0, index=YEAR)
    measured = lc.Calendar.from_series(series)
    np.testing.assert_allclose(measured.week, truth.week, rtol=1e-9)
    np.testing.assert_allclose(measured.month, truth.month, rtol=1e-9)


def test_a_short_series_keeps_flat_months():
    week_long = YEAR[:24 * 14]
    series = pd.Series(lc.Calendar.of("semi_continuous").factors(week_long),
                       index=week_long)
    assert lc.Calendar.from_series(series).month == lc.Calendar.flat().month


def test_monthly_bills_set_the_month_factors():
    """A month with no energy gets no demand; energy per running hour is kept."""
    bills = [100.0] * 12
    bills[7] = 0.0                                   # shut in August
    calendar = lc.Calendar.from_schedule([("Mon-Fri", 6, 22)], base_load=0.1,
                                         monthly_energy=bills)
    assert calendar.month[7] == pytest.approx(0.0)
    frame = quiet(lc.DemandSpec(process_class=lc.custom_class(calendar=calendar),
                                **SITE))
    monthly = frame["heat_kw"].groupby(frame.index.month).sum()
    assert monthly[8] / monthly.sum() < 0.002


def test_class_calendar_round_trips():
    for name in lc.available_classes():
        process = lc.get_class(name)
        calendar = lc.Calendar.of(name)
        ratio = process.calendar(YEAR) / calendar.factors(YEAR)
        assert np.ptp(ratio) == pytest.approx(0.0, abs=1e-9)


# =============================================================================
# Adjusting a shipped class
# =============================================================================


def test_custom_class_with_nothing_changed_keeps_the_numbers():
    for name in lc.available_classes():
        base = lc.get_class(name)
        same = lc.custom_class(name)
        assert same.target_load_factor == pytest.approx(base.target_load_factor)
        assert same.target_cv == pytest.approx(base.target_cv, rel=1e-6)
        assert same.target_lag1 == base.target_lag1


@pytest.mark.parametrize("off_fraction", [0.1, 0.3, 0.5])
def test_more_stops_keep_every_target_reachable(off_fraction):
    """The same plant stopping more often: load factor and idle share exact."""
    process = lc.custom_class("semi_continuous", off_fraction=off_fraction)
    frame = quiet(lc.DemandSpec(process_class=process, **SITE))
    stats = lc.profile_statistics(frame["heat_kw"])
    assert stats["load_factor"] == pytest.approx(process.target_load_factor,
                                                 rel=1e-3)
    assert stats["idle_fraction"] == pytest.approx(off_fraction, abs=0.01)
    assert stats["cv"] == pytest.approx(process.target_cv, rel=0.15)


@pytest.mark.parametrize("shifts", [
    [("Mon-Fri", 6, 14)],
    [("Mon-Fri", 6, 22)],
    [("Mon-Sat", 0, 24)],
    [("Mon-Fri", 6, 22), ("Sat", 6, 14)],
])
def test_own_calendar_keeps_the_fluctuation(shifts):
    """A new calendar on a shipped class: no warning, and the targets land."""
    calendar = lc.Calendar.from_schedule(shifts, base_load=0.25)
    process = lc.custom_class("semi_continuous", calendar=calendar)
    frame = quiet(lc.DemandSpec(process_class=process, carrier_correlation=0.8,
                                **SITE))
    stats = lc.profile_statistics(frame["heat_kw"])
    assert stats["load_factor"] == pytest.approx(process.target_load_factor,
                                                 rel=1e-3)
    assert stats["cv"] == pytest.approx(process.target_cv, rel=0.1)
    assert np.allclose(lc.Calendar.of(process).week, calendar.week)


@pytest.mark.parametrize("base", sorted(lc.load_classes()))
@pytest.mark.parametrize("shifts", [[("Mon-Fri", 6, 14)], [("Mon-Fri", 6, 22)]])
def test_every_class_takes_a_schedule_quietly(base, shifts):
    """The derived load factor is reached, and the spread lands, at any seed.

    The cap clips the share of hours the base's cap clips; a base with no
    fluctuation (batch) takes its step function's own load factor, raised just
    enough to be reached whatever the seed.
    """
    process = lc.custom_class(base, calendar=lc.Calendar.from_schedule(
        shifts, base_load=0.25))
    for seed in (1, 2, 3):
        frame = quiet(lc.DemandSpec(process_class=process,
                                    carrier_correlation=0.9,
                                    **{**SITE, "seed": seed}))
        achieved = lc.profile_statistics(frame["heat_kw"])["load_factor"]
        assert achieved == pytest.approx(process.target_load_factor, rel=5e-3)


@pytest.mark.parametrize("base", ["continuous", "semi_continuous", "campaign"])
def test_a_carrier_on_its_own_calendar_is_quiet(base):
    for seed in (1, 2):
        quiet(lc.DemandSpec(process_class=base, calendars={"cold": lc.Calendar.flat()},
                            **{**SITE, "seed": seed}))


def test_a_spread_smaller_than_the_calendar_warns():
    calendar = lc.Calendar.from_schedule([("Mon-Fri", 6, 22)], base_load=0.25)
    with pytest.warns(lc.TargetMissedWarning, match="nothing is left"):
        lc.custom_class("semi_continuous", calendar=calendar, cv=0.4)
    with pytest.warns(lc.TargetMissedWarning, match="nothing is left"):
        lc.class_from_observations("mine", 0.4, 0.4, 0.8, calendar=calendar)


def test_a_class_object_needs_no_registering():
    process = lc.custom_class("continuous", name="never_registered",
                              off_fraction=0.2)
    assert "never_registered" not in lc.available_classes()
    frame = lc.generate(process_class=process, **SITE)
    assert frame["heat_kw"].sum() > 0


def test_the_knob_belongs_to_the_class_not_its_name():
    """Two classes under one name are solved separately."""
    first = lc.custom_class("semi_continuous", name="mine")
    second = lc.custom_class("semi_continuous", name="mine", off_fraction=0.4)
    knobs = [lc.solve_correlation_knob(lc.DemandSpec(
        process_class=process, carrier_correlation=0.7, **SITE))
        for process in (first, second)]
    assert knobs[0] != pytest.approx(knobs[1], abs=1e-3)


# =============================================================================
# Ratings
# =============================================================================


def test_a_tight_rating_is_the_peak_exactly():
    spec = lc.DemandSpec(rated_kw={"heat": 1300.0}, **SITE)
    frame = quiet(spec)
    mean_kw = spec.annual_mwh_by_carrier()["heat"] * 1000 / 8760
    assert frame["heat_kw"].max() == pytest.approx(1300.0, rel=1e-6)
    assert lc.profile_statistics(frame["heat_kw"])["load_factor"] == \
        pytest.approx(mean_kw / 1300.0, rel=1e-3)


def test_each_carrier_takes_its_own_rating():
    spec = lc.DemandSpec(rated_kw={"heat": 1300.0, "elec": 400.0}, **SITE)
    frame = quiet(spec)
    assert frame["heat_kw"].max() == pytest.approx(1300.0, rel=1e-6)
    assert frame["elec_kw"].max() == pytest.approx(400.0, rel=1e-6)
    # The cold carrier keeps the class's load factor.
    cold = lc.profile_statistics(frame["cold_kw"])["load_factor"]
    assert cold == pytest.approx(lc.get_class("semi_continuous")
                                 .target_load_factor, rel=1e-3)


def test_a_carrier_load_factor_sets_its_cap():
    spec = lc.DemandSpec(load_factor={"heat": 0.55}, **SITE)
    frame = quiet(spec)
    assert lc.profile_statistics(frame["heat_kw"])["load_factor"] == \
        pytest.approx(0.55, rel=1e-3)
    # The other carriers keep the class's.
    assert lc.profile_statistics(frame["cold_kw"])["load_factor"] == \
        pytest.approx(lc.get_class("semi_continuous").target_load_factor,
                      rel=1e-3)


def test_a_rating_and_a_load_factor_for_one_carrier_raise():
    """With the annual energy fixed, a rating already is a load factor."""
    with pytest.raises(ValueError, match="not both"):
        lc.DemandSpec(rated_kw={"heat": 1300.0}, load_factor={"heat": 0.5},
                      **SITE)
    # Different carriers may each take one.
    lc.DemandSpec(rated_kw={"heat": 1300.0}, load_factor={"cold": 0.5}, **SITE)
    with pytest.raises(ValueError, match="in \\(0, 1\\)"):
        lc.DemandSpec(load_factor={"heat": 1.2})


def test_a_rating_never_reached_warns():
    with pytest.warns(lc.TargetMissedWarning, match="below its rating"):
        lc.generate(rated_kw={"cold": 3000.0}, **SITE)


def test_impossible_ratings_raise():
    with pytest.raises(ValueError, match="mean demand"):
        lc.generate(rated_kw={"heat": 500.0}, **SITE)       # mean is ~761 kW
    with pytest.raises(ValueError, match="does not have"):
        lc.generate(annual_mwh=10_000, heat_to_cold=None, rated_kw={"cold": 99.0})
    with pytest.raises(ValueError, match="unknown carriers"):
        lc.DemandSpec(rated_kw={"steam": 100.0})
    with pytest.raises(ValueError, match="positive"):
        lc.DemandSpec(rated_kw={"heat": 0.0})


# =============================================================================
# A calendar for one carrier
# =============================================================================


def test_cold_on_its_own_calendar_runs_through_the_weekend():
    flat = lc.Calendar.flat()
    spec = lc.DemandSpec(calendars={"cold": flat}, **SITE)
    frame = quiet(spec)
    weekend = frame.index.dayofweek >= 5
    share = {c: frame[c][weekend].mean() / frame[c].mean()
             for c in ("heat_kw", "cold_kw")}
    assert share["cold_kw"] > 1.5 * share["heat_kw"]
    # Less calendar in common, a lower floor.
    assert lc.correlation_floor(spec) < lc.correlation_floor(
        lc.DemandSpec(**SITE)) - 0.2


def test_calendars_must_be_calendars():
    with pytest.raises(TypeError, match="Calendar"):
        lc.DemandSpec(calendars={"cold": [1.0] * 168})


# =============================================================================
# What is delivered against what is asked
# =============================================================================


@pytest.mark.parametrize("process_class", sorted(lc.load_classes()))
def test_shipped_classes_are_quiet_at_their_defaults(process_class):
    for freq in ("h", "15min"):
        with warnings.catch_warnings():
            warnings.simplefilter("error", lc.TargetMissedWarning)
            lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class=process_class, freq=freq)


def test_a_correlation_below_the_floor_warns_and_says_why():
    with pytest.warns(lc.TargetMissedWarning, match="below the floor"):
        lc.generate(carrier_correlation=0.1, **SITE)


def test_the_default_correlation_is_raised_to_the_floor_quietly():
    """batch's floor is above 0.47; the default must not warn about it."""
    quiet(lc.DemandSpec(process_class="batch", **SITE))


def test_report_lists_every_statistic():
    spec = lc.DemandSpec(rated_kw={"heat": 1300.0}, **SITE)
    report = lc.delivery_report(spec, quiet(spec))
    assert set(report.columns) == {"carrier", "statistic", "kind", "requested",
                                   "delivered", "status", "why"}
    heat = report[report["carrier"] == "heat"]
    assert set(heat["statistic"]) == {"annual_mwh", "peak_kw", "load_factor",
                                      "cv", "lag1"}
    assert (report["status"] == "ok").all()
    assert "correlation" in set(report["statistic"])
