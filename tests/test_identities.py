"""The algebra the generator rests on, checked rather than asserted.

Each test here corresponds to one derivation in `docs/mathematics.md`. If the
maths in the documentation is right, these pass; if someone changes the code in
a way that breaks the maths, they fail with a pointer to which step broke.
"""

import numpy as np
import pandas as pd
import pytest

import loadcast as lc
from loadcast import fitting, generator


RNG = np.random.default_rng(20250925)
INDEX = pd.date_range("2025-01-01", periods=8760, freq="h")


# =============================================================================
# The residual has mean one, so it cannot move the annual energy
# =============================================================================


@pytest.mark.parametrize("sigma", [0.1, 0.3, 0.5, 0.9])
def test_residual_has_unit_mean(sigma):
    """E[exp(z - sigma^2/2)] = 1 for z ~ N(0, sigma^2)."""
    latent = generator.correlated_ar1(200_000, 1, phi=0.5, sigma=sigma,
                                      correlation=0.0, rng=RNG)
    residual = generator.lognormal_from_latent(latent, sigma)
    assert residual.mean() == pytest.approx(1.0, abs=0.02)


# =============================================================================
# The AR(1) is stationary from the first step: no burn-in
# =============================================================================


@pytest.mark.parametrize("phi", [0.0, 0.5, 0.9, 0.97])
def test_ar1_is_stationary_from_the_start(phi):
    """The sqrt(1 - phi^2) factor makes the variance sigma^2 immediately.

    Without it the series starts at zero variance and grows into its spread,
    which at phi = 0.97 would waste several hundred hours of a year.
    """
    sigma = 0.4
    paths = generator.correlated_ar1(4000, 400, phi=phi, sigma=sigma,
                                     correlation=0.0, rng=RNG)
    # Variance across the ensemble, at the very first step and much later.
    first = float(paths[:, 0].std())
    later = float(paths[:, -1].std())
    assert first == pytest.approx(sigma, rel=0.10)
    assert later == pytest.approx(sigma, rel=0.10)


# =============================================================================
# Spread composes multiplicatively, not additively
# =============================================================================


def test_cv_composition_identity():
    """1 + CV_total^2 = (1 + CV_calendar^2)(1 + CV_residual^2)."""
    calendar_cv, residual_cv = 0.31, 0.34
    total = fitting.combine_cv(calendar_cv, residual_cv)
    assert (1 + total**2) == pytest.approx(
        (1 + calendar_cv**2) * (1 + residual_cv**2), rel=1e-12
    )
    # and the inverse recovers the residual
    assert fitting.split_cv(total, calendar_cv) == pytest.approx(residual_cv,
                                                                rel=1e-12)


def test_cv_composition_holds_on_generated_series():
    """The identity is exact in expectation, so allow finite-sample slack."""
    process = lc.get_class("semi_continuous")
    calendar = process.calendar(INDEX)
    residual_cv = fitting.split_cv(process.target_cv,
                                   float(calendar.std() / calendar.mean()))
    sigma = fitting.sigma_from_cv(residual_cv)
    latent = generator.correlated_ar1(len(INDEX), 1, phi=0.79, sigma=sigma,
                                      correlation=0.0, rng=RNG)
    residual = generator.lognormal_from_latent(latent, sigma)[0]

    product = calendar * residual
    achieved = float(product.std() / product.mean())
    # One draw of 8760 hours carries sampling covariance between the two
    # factors, so this is close but not exact -- which is why the production
    # path caps and rescales rather than trusting the identity alone.
    assert achieved == pytest.approx(process.target_cv, rel=0.10)


# =============================================================================
# Lognormal transforms invert exactly
# =============================================================================


@pytest.mark.parametrize("cv", [0.1, 0.4, 0.8, 1.2])
def test_sigma_cv_round_trip(cv):
    assert fitting.cv_from_sigma(fitting.sigma_from_cv(cv)) == pytest.approx(
        cv, rel=1e-12)


@pytest.mark.parametrize("lag1", [0.1, 0.5, 0.79, 0.97])
def test_phi_lag1_round_trip(lag1):
    sigma = fitting.sigma_from_cv(0.4)
    phi = fitting.phi_from_lag1(lag1, sigma)
    assert fitting.lag1_from_phi(phi, sigma) == pytest.approx(lag1, rel=1e-10)


@pytest.mark.parametrize("rho", [-0.3, 0.0, 0.25, 0.7, 0.95])
def test_correlation_transform_round_trip(rho):
    sigma = fitting.sigma_from_cv(0.5)
    residual = fitting.residual_correlation(rho, sigma)
    assert fitting.latent_correlation(residual, sigma) == pytest.approx(
        rho, rel=1e-10)


def test_latent_correlation_transfers_to_lognormals():
    """corr(exp z1, exp z2) = (exp(rho*s^2) - 1)/(exp(s^2) - 1)."""
    sigma, rho = 0.35, 0.3
    paths = generator.correlated_ar1(300_000, 2, phi=0.0, sigma=sigma,
                                     correlation=rho, rng=RNG)
    residual = generator.lognormal_from_latent(paths, sigma)
    empirical = float(np.corrcoef(residual[0], residual[1])[0, 1])
    assert empirical == pytest.approx(
        fitting.residual_correlation(rho, sigma), abs=0.02)


# =============================================================================
# The correlation floor: what the shared calendar alone imposes
# =============================================================================


@pytest.mark.parametrize("process_class", lc.available_classes())
def test_correlation_floor_is_reached_with_independent_residuals(process_class):
    """g(0) = CV_calendar^2 / CV_total^2, the calendar-only coupling.

    Asking for a correlation of zero cannot go below this floor, because every
    carrier dips on a Sunday and in July whatever its residual does.
    """
    spec = lc.DemandSpec(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                         process_class=process_class, carrier_correlation=0.0)
    frame = generator.build_profiles(spec, INDEX, knob=0.0)
    achieved = float(frame["heat_kw"].corr(frame["cold_kw"]))
    predicted = lc.correlation_floor(process_class)
    # The closed form is exact for the unmasked model; the on/off mask and the
    # capacity cap shift it, so masked classes get a looser bound.
    tolerance = 0.10 if lc.get_class(process_class).mode == "lognormal" else 0.25
    assert achieved == pytest.approx(predicted, abs=tolerance)


def test_requested_correlation_is_delivered():
    for target in (0.55, 0.70, 0.88):
        frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0,
                            elec_share=0.2, process_class="semi_continuous",
                            carrier_correlation=target)
        achieved = float(frame["heat_kw"].corr(frame["cold_kw"]))
        assert achieved == pytest.approx(target, abs=0.05)


# =============================================================================
# The lag is a pure cross-carrier knob
# =============================================================================


@pytest.mark.parametrize("tau", [3, 6, 12, 24])
def test_lag_preserves_every_marginal_statistic(tau):
    """A circular shift is a permutation, so the shifted carrier's own
    statistics are identical. The lag changes timing and nothing else."""
    common = dict(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                  process_class="semi_continuous", carrier_correlation=0.75)
    unlagged = lc.generate(**common)
    lagged = lc.generate(carrier_lag_h={"cold": tau}, **common)

    before = lc.profile_statistics(unlagged["cold_kw"])
    after = lc.profile_statistics(lagged["cold_kw"])
    for key in ("mean_kw", "peak_kw", "load_factor", "cv", "annual_mwh"):
        assert after[key] == pytest.approx(before[key], rel=0.02), key


@pytest.mark.parametrize("tau", [3, 6, 12])
def test_lag_moves_the_correlogram_peak(tau):
    frame = lc.generate(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                        process_class="semi_continuous",
                        carrier_correlation=0.75,
                        carrier_lag_h={"cold": tau})
    correlogram = lc.cross_correlogram(frame["heat_kw"], frame["cold_kw"],
                                       max_lag=36)
    peak = int(correlogram.loc[correlogram["correlation"].idxmax(), "lag_h"])
    assert peak == pytest.approx(tau, abs=1)


def test_lag_raises_integrated_drift():
    """A store integrates a mismatch, so an offset costs it buffering even
    when the annual quantities balance exactly."""
    common = dict(annual_mwh=10_000, heat_to_cold=2.0, elec_share=0.2,
                  process_class="semi_continuous", carrier_correlation=0.75)
    drifts = []
    for tau in (0, 6, 12):
        frame = lc.generate(carrier_lag_h={"cold": tau}, **common)
        drifts.append(lc.integrated_drift(frame["heat_kw"], frame["cold_kw"],
                                          window_h=24))
    assert drifts[0] < drifts[1] < drifts[2]
