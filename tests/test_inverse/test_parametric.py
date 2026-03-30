"""Tests for src/inverse/parametric.py — Exp/Weibull parametric estimation."""

from __future__ import annotations

import math

import pytest

from src.inverse.parametric import fit_exponential, fit_weibull


# ---------------------------------------------------------------------------
# Exponential fit
# ---------------------------------------------------------------------------


class TestFitExponential:
    def test_perfect_data_recovers_lambda(self) -> None:
        """With perfect data from known λ, MLE should recover it."""
        true_lambda = 0.05  # event rate: 5% per day
        horizons = [30.0, 60.0, 90.0, 120.0, 180.0, 365.0]
        positions = [1 - math.exp(-true_lambda * h) for h in horizons]

        result = fit_exponential(positions, horizons, user_id="perfect")
        assert result is not None
        assert abs(result.lambda_val - true_lambda) < 0.001
        assert result.n_observations == 6

    def test_noisy_data_reasonable_estimate(self) -> None:
        """With noise, estimate should be in the right ballpark."""
        true_lambda = 0.02
        horizons = [30.0, 60.0, 90.0, 120.0, 180.0, 250.0, 365.0]
        # Add noise ±0.05 to true positions
        noise = [0.02, -0.03, 0.04, -0.01, 0.03, -0.02, 0.01]
        positions = [
            max(0.01, min(0.99, 1 - math.exp(-true_lambda * h) + n))
            for h, n in zip(horizons, noise)
        ]

        result = fit_exponential(positions, horizons, user_id="noisy")
        assert result is not None
        # Within 100% of true value (generous for noisy data)
        assert 0.005 < result.lambda_val < 0.06

    def test_insufficient_data_returns_none(self) -> None:
        """Fewer than MIN_OBS_EXPONENTIAL observations → None."""
        result = fit_exponential([0.5, 0.6], [30.0, 60.0])
        assert result is None

    def test_mismatched_lengths_returns_none(self) -> None:
        result = fit_exponential([0.5, 0.6, 0.7], [30.0, 60.0])
        assert result is None

    def test_zero_horizon_skipped(self) -> None:
        """Markets with horizon=0 should be skipped."""
        positions = [0.3, 0.5, 0.6, 0.7, 0.8]
        horizons = [0.0, 30.0, 60.0, 90.0, 120.0]
        # Only 4 valid observations (first skipped) — still < 5 but let's use 6
        positions = [0.1, 0.3, 0.5, 0.6, 0.7, 0.8]
        horizons = [0.0, 30.0, 60.0, 90.0, 120.0, 180.0]

        result = fit_exponential(positions, horizons, user_id="zero_h")
        assert result is not None
        assert result.n_observations == 5  # one skipped

    def test_ci_bounds(self) -> None:
        """CI lower < lambda < CI upper."""
        true_lambda = 0.03
        horizons = [30.0, 60.0, 90.0, 120.0, 180.0, 365.0]
        positions = [1 - math.exp(-true_lambda * h) for h in horizons]

        result = fit_exponential(positions, horizons)
        assert result is not None
        assert result.ci_lower < result.lambda_val < result.ci_upper

    def test_bayesian_shrinkage(self) -> None:
        """With prior, small-n estimates are pulled toward prior."""
        # 5 observations — small n triggers shrinkage
        positions = [0.9, 0.85, 0.8, 0.75, 0.7]
        horizons = [30.0, 30.0, 30.0, 30.0, 30.0]

        result_mle = fit_exponential(positions, horizons, user_id="mle")
        result_bayes = fit_exponential(
            positions,
            horizons,
            user_id="bayes",
            prior_lambda=0.001,
            prior_strength=10,
        )

        assert result_mle is not None and result_bayes is not None
        # Bayesian should be pulled toward prior (lower)
        assert result_bayes.lambda_val < result_mle.lambda_val

    def test_extreme_positions_clamped(self) -> None:
        """Positions at 0 or 1 should be safely clamped."""
        positions = [0.0, 1.0, 0.5, 0.6, 0.7]
        horizons = [30.0, 30.0, 60.0, 90.0, 120.0]
        result = fit_exponential(positions, horizons)
        assert result is not None
        assert result.lambda_val > 0


# ---------------------------------------------------------------------------
# Weibull fit
# ---------------------------------------------------------------------------


class TestFitWeibull:
    def test_weibull_reduces_to_exp_at_k1(self) -> None:
        """With data from Exp(λ), Weibull should find k ≈ 1."""
        true_lambda = 0.03
        horizons = list(range(10, 400, 15))  # 26 points
        positions = [1 - math.exp(-true_lambda * h) for h in horizons]

        result = fit_weibull(
            positions,
            [float(h) for h in horizons],
            user_id="exp_data",
            initial_lambda=true_lambda,
        )
        assert result is not None
        assert abs(result.shape_k - 1.0) < 0.3  # k should be near 1

    def test_insufficient_data_returns_none(self) -> None:
        """Fewer than MIN_OBS_WEIBULL → None."""
        positions = [0.5] * 10
        horizons = [30.0] * 10
        result = fit_weibull(positions, horizons)
        assert result is None

    def test_aic_bic_computed(self) -> None:
        """AIC and BIC should be finite numbers."""
        true_lambda = 0.005
        horizons = list(range(10, 400, 15))
        positions = [1 - math.exp(-true_lambda * h) for h in horizons]

        result = fit_weibull(
            positions,
            [float(h) for h in horizons],
            initial_lambda=0.005,
        )
        assert result is not None
        assert math.isfinite(result.aic)
        assert math.isfinite(result.bic)

    def test_accelerating_hazard_k_greater_1(self) -> None:
        """With accelerating event probability, k should be > 1."""
        # Weibull CDF with k=2: P = 1 - exp(-(λH)^2)
        true_lambda = 0.01
        true_k = 2.0
        horizons = list(range(10, 400, 15))
        positions = [1 - math.exp(-((true_lambda * h) ** true_k)) for h in horizons]

        result = fit_weibull(
            positions,
            [float(h) for h in horizons],
            initial_lambda=true_lambda,
        )
        assert result is not None
        assert result.shape_k > 1.2  # Should find k > 1


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestParametricSchemas:
    def test_exponential_fit_frozen(self) -> None:
        from src.inverse.schemas import ExponentialFit

        fit = ExponentialFit(
            user_id="u1",
            lambda_val=0.05,
            n_observations=10,
            log_likelihood=-5.0,
            ci_lower=0.03,
            ci_upper=0.07,
        )
        with pytest.raises(Exception):
            fit.user_id = "changed"  # type: ignore[misc]

    def test_parametric_result_model_selection(self) -> None:
        from src.inverse.schemas import ExponentialFit, ParametricResult

        exp = ExponentialFit(
            user_id="u1",
            lambda_val=0.05,
            n_observations=10,
            log_likelihood=-5.0,
            ci_lower=0.03,
            ci_upper=0.07,
        )
        result = ParametricResult(
            user_id="u1",
            preferred_model="exponential",
            exp_fit=exp,
            weibull_fit=None,
            delta_aic=0.0,
        )
        assert result.preferred_model == "exponential"
        assert result.weibull_fit is None
