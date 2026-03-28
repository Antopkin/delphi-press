"""Tests for src/data_sources/market_metrics.py — distribution metrics."""

from __future__ import annotations

import pytest

from src.data_sources.market_metrics import (
    MarketMetrics,
    compute_confidence_interval,
    compute_lw_probability,
    compute_market_metrics,
    compute_spread_metrics,
    compute_trend,
    compute_volatility,
)


# ---------------------------------------------------------------------------
# compute_volatility
# ---------------------------------------------------------------------------


class TestComputeVolatility:
    def test_constant_prices_zero_volatility(self) -> None:
        prices = [0.5] * 10
        assert compute_volatility(prices) == 0.0

    def test_alternating_prices_positive_volatility(self) -> None:
        prices = [0.4, 0.6, 0.4, 0.6, 0.4, 0.6, 0.4, 0.6]
        assert compute_volatility(prices) > 0

    def test_empty_prices_zero(self) -> None:
        assert compute_volatility([]) == 0.0

    def test_single_price_zero(self) -> None:
        assert compute_volatility([0.5]) == 0.0

    def test_two_prices_returns_absolute_logit_return(self) -> None:
        vol = compute_volatility([0.4, 0.6])
        assert vol > 0

    def test_window_limits_data(self) -> None:
        prices = [0.5] * 20 + [0.4, 0.6, 0.4, 0.6, 0.4, 0.6, 0.4]
        vol_full = compute_volatility(prices, window=7)
        vol_all = compute_volatility(prices, window=100)
        # Window=7 uses only the volatile tail
        assert vol_full > vol_all

    def test_higher_swings_higher_volatility(self) -> None:
        small_swing = [0.45, 0.55, 0.45, 0.55, 0.45, 0.55, 0.45, 0.55]
        large_swing = [0.2, 0.8, 0.2, 0.8, 0.2, 0.8, 0.2, 0.8]
        assert compute_volatility(large_swing) > compute_volatility(small_swing)


# ---------------------------------------------------------------------------
# compute_trend
# ---------------------------------------------------------------------------


class TestComputeTrend:
    def test_monotone_increasing_positive_trend(self) -> None:
        prices = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]
        assert compute_trend(prices) > 0

    def test_monotone_decreasing_negative_trend(self) -> None:
        prices = [0.7, 0.65, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.3]
        assert compute_trend(prices) < 0

    def test_constant_prices_zero_trend(self) -> None:
        prices = [0.5] * 10
        assert compute_trend(prices) == pytest.approx(0.0, abs=1e-10)

    def test_empty_prices_zero(self) -> None:
        assert compute_trend([]) == 0.0

    def test_single_price_zero(self) -> None:
        assert compute_trend([0.5]) == 0.0

    def test_two_prices_nonzero(self) -> None:
        trend = compute_trend([0.4, 0.6])
        assert trend > 0  # upward


# ---------------------------------------------------------------------------
# compute_spread_metrics
# ---------------------------------------------------------------------------


class TestComputeSpreadMetrics:
    def test_tight_spread_low_uncertainty(self) -> None:
        spread, uncertainty = compute_spread_metrics(0.49, 0.51)
        assert spread < 0.05
        assert uncertainty < 0.5

    def test_wide_spread_high_uncertainty(self) -> None:
        spread, uncertainty = compute_spread_metrics(0.30, 0.70)
        assert spread > 0.05
        assert uncertainty > 0.5

    def test_bid_equals_ask_zero(self) -> None:
        spread, uncertainty = compute_spread_metrics(0.50, 0.50)
        assert spread == 0.0
        assert uncertainty == 0.0

    def test_bid_greater_than_ask_zero(self) -> None:
        spread, uncertainty = compute_spread_metrics(0.60, 0.40)
        assert spread == 0.0
        assert uncertainty == 0.0

    def test_zero_bid_ask_zero(self) -> None:
        spread, uncertainty = compute_spread_metrics(0.0, 0.0)
        assert spread == 0.0
        assert uncertainty == 0.0

    def test_knee_point_half_uncertainty(self) -> None:
        """At normalized spread = 0.05, uncertainty should be ~0.5."""
        # bid=0.4875, ask=0.5125 → mid=0.5, spread=0.025, s_norm=0.05
        spread, uncertainty = compute_spread_metrics(0.4875, 0.5125)
        assert spread == pytest.approx(0.05, abs=0.001)
        assert uncertainty == pytest.approx(0.5, abs=0.05)


# ---------------------------------------------------------------------------
# compute_lw_probability
# ---------------------------------------------------------------------------


class TestComputeLwProbability:
    def test_high_volume_close_to_raw(self) -> None:
        lw = compute_lw_probability(0.7, 1_000_000)
        assert abs(lw - 0.7) < 0.05

    def test_low_volume_shrinks_toward_half(self) -> None:
        lw = compute_lw_probability(0.7, 100)
        assert lw < 0.7
        assert lw > 0.5

    def test_zero_volume_returns_half(self) -> None:
        assert compute_lw_probability(0.8, 0) == 0.5

    def test_negative_volume_returns_half(self) -> None:
        assert compute_lw_probability(0.8, -100) == 0.5

    def test_very_high_volume_capped(self) -> None:
        """Volume >> ref_volume: weight capped at 1.0, so lw_prob = raw prob."""
        lw = compute_lw_probability(0.7, 100_000_000)
        assert lw == pytest.approx(0.7, abs=0.001)

    def test_symmetric_around_half(self) -> None:
        lw_high = compute_lw_probability(0.8, 10_000)
        lw_low = compute_lw_probability(0.2, 10_000)
        assert lw_high + lw_low == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# compute_confidence_interval
# ---------------------------------------------------------------------------


class TestComputeConfidenceInterval:
    def test_enough_observations(self) -> None:
        prices = [0.3 + 0.02 * i for i in range(20)]
        ci_low, ci_high = compute_confidence_interval(prices)
        assert ci_low is not None
        assert ci_high is not None
        assert ci_low < ci_high

    def test_too_few_observations(self) -> None:
        prices = [0.5] * 5
        ci_low, ci_high = compute_confidence_interval(prices)
        assert ci_low is None
        assert ci_high is None

    def test_exactly_min_obs(self) -> None:
        prices = [0.3 + 0.02 * i for i in range(14)]
        ci_low, ci_high = compute_confidence_interval(prices, min_obs=14)
        assert ci_low is not None
        assert ci_high is not None

    def test_below_min_obs(self) -> None:
        prices = [0.5] * 13
        ci_low, ci_high = compute_confidence_interval(prices, min_obs=14)
        assert ci_low is None
        assert ci_high is None

    def test_constant_prices_equal_ci(self) -> None:
        prices = [0.5] * 20
        ci_low, ci_high = compute_confidence_interval(prices)
        assert ci_low == 0.5
        assert ci_high == 0.5

    def test_empty_prices(self) -> None:
        ci_low, ci_high = compute_confidence_interval([])
        assert ci_low is None
        assert ci_high is None


# ---------------------------------------------------------------------------
# compute_market_metrics (orchestrator)
# ---------------------------------------------------------------------------


class TestComputeMarketMetrics:
    def test_returns_frozen_model(self) -> None:
        prices = [0.5 + 0.01 * i for i in range(20)]
        m = compute_market_metrics(prices, volume=100_000, bid=0.49, ask=0.51, probability=0.7)
        assert isinstance(m, MarketMetrics)
        with pytest.raises(Exception):
            m.volatility_7d = 999  # type: ignore[misc]

    def test_empty_prices(self) -> None:
        m = compute_market_metrics([], volume=0, bid=0, ask=0, probability=0.5)
        assert m.volatility_7d == 0.0
        assert m.trend_7d == 0.0
        assert m.ci_low is None
        assert m.ci_high is None
        assert m.distribution_reliable is False
        assert m.lw_probability == 0.5

    def test_reliable_when_enough_data(self) -> None:
        prices = [0.5] * 20
        m = compute_market_metrics(prices, volume=500_000, bid=0.49, ask=0.51, probability=0.5)
        assert m.distribution_reliable is True
        assert m.ci_low is not None

    def test_unreliable_when_few_data(self) -> None:
        prices = [0.5] * 5
        m = compute_market_metrics(prices, volume=500_000, bid=0.49, ask=0.51, probability=0.5)
        assert m.distribution_reliable is False

    def test_all_fields_populated(self) -> None:
        prices = [
            0.4,
            0.42,
            0.45,
            0.47,
            0.5,
            0.52,
            0.55,
            0.57,
            0.6,
            0.62,
            0.65,
            0.67,
            0.7,
            0.72,
            0.75,
        ]
        m = compute_market_metrics(prices, volume=200_000, bid=0.48, ask=0.52, probability=0.75)
        assert m.volatility_7d >= 0
        assert m.trend_7d > 0  # upward trend
        assert m.spread > 0
        assert m.uncertainty > 0
        assert 0.5 < m.lw_probability <= 0.75
        assert m.ci_low is not None
        assert m.ci_high is not None
        assert m.distribution_reliable is True

    def test_zero_bid_ask_safe(self) -> None:
        """bid=0, ask=0 should not crash."""
        prices = [0.5] * 20
        m = compute_market_metrics(prices, volume=100_000, bid=0, ask=0, probability=0.5)
        assert m.spread == 0.0
        assert m.uncertainty == 0.0
