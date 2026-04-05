"""Tests for src.eval.correlation — news-market correlation analysis."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.eval.correlation import (
    collect_news_in_window,
    compute_granger_causality,
    compute_spearman_correlation,
    detect_sharp_movements,
)

# ===========================================================================
# detect_sharp_movements
# ===========================================================================


class TestDetectSharpMovements:
    def test_above_threshold(self) -> None:
        """Movements with |delta_p| >= threshold are detected."""
        prices = [
            {"t": 1000, "p": 0.50},
            {"t": 2000, "p": 0.50},
            {"t": 3000, "p": 0.65},  # +0.15 from previous
            {"t": 4000, "p": 0.64},
        ]
        result = detect_sharp_movements(prices, threshold=0.10)
        assert len(result) == 1
        assert result[0]["delta_p"] == pytest.approx(0.15)
        assert result[0]["timestamp"] == 3000
        assert result[0]["price_before"] == pytest.approx(0.50)
        assert result[0]["price_after"] == pytest.approx(0.65)

    def test_below_threshold(self) -> None:
        """Small price changes are filtered out."""
        prices = [
            {"t": 1000, "p": 0.50},
            {"t": 2000, "p": 0.52},
            {"t": 3000, "p": 0.51},
        ]
        result = detect_sharp_movements(prices, threshold=0.10)
        assert result == []

    def test_dedup_interval(self) -> None:
        """Movements within min_interval_hours are deduplicated."""
        prices = [
            {"t": 1000, "p": 0.50},
            {"t": 2000, "p": 0.65},  # +0.15 (detected)
            {"t": 3000, "p": 0.50},  # -0.15 (within 1h of previous → skip)
            {"t": 20000, "p": 0.35},  # -0.15 from 0.50 (far enough → detected)
        ]
        result = detect_sharp_movements(prices, threshold=0.10, min_interval_hours=4)
        assert len(result) == 2

    def test_empty_prices(self) -> None:
        assert detect_sharp_movements([]) == []

    def test_single_price(self) -> None:
        assert detect_sharp_movements([{"t": 1000, "p": 0.50}]) == []

    def test_negative_delta(self) -> None:
        """Price drops are also detected."""
        prices = [
            {"t": 1000, "p": 0.80},
            {"t": 2000, "p": 0.60},  # -0.20
        ]
        result = detect_sharp_movements(prices, threshold=0.10)
        assert len(result) == 1
        assert result[0]["delta_p"] == pytest.approx(-0.20)


# ===========================================================================
# collect_news_in_window
# ===========================================================================


class TestCollectNewsInWindow:
    def test_finds_matching(self) -> None:
        """Signals in [-24h, 0] before movement are collected."""
        movement_ts = 100_000
        signals = [
            {"published_at": 95_000, "relevance_score": 0.8, "categories": ["politics"]},
            {"published_at": 99_000, "relevance_score": 0.6, "categories": ["economy"]},
        ]
        result = collect_news_in_window(signals, movement_ts, window_hours=24)
        assert result["count"] == 2
        assert result["mean_relevance"] == pytest.approx(0.7)

    def test_excludes_after(self) -> None:
        """Signals after movement timestamp are excluded."""
        movement_ts = 100_000
        signals = [
            {"published_at": 101_000, "relevance_score": 0.9, "categories": []},
        ]
        result = collect_news_in_window(signals, movement_ts, window_hours=24)
        assert result["count"] == 0

    def test_excludes_before_window(self) -> None:
        """Signals before the lookback window are excluded."""
        movement_ts = 100_000
        # 24h = 86400s, so anything before 100000 - 86400 = 13600 is excluded
        signals = [
            {"published_at": 10_000, "relevance_score": 0.5, "categories": []},
        ]
        result = collect_news_in_window(signals, movement_ts, window_hours=24)
        assert result["count"] == 0

    def test_category_overlap(self) -> None:
        """Category overlap score computed when market_categories provided."""
        movement_ts = 100_000
        signals = [
            {"published_at": 99_000, "relevance_score": 0.5, "categories": ["politics", "war"]},
        ]
        result = collect_news_in_window(
            signals,
            movement_ts,
            window_hours=24,
            market_categories=["politics", "geopolitics"],
        )
        assert result["count"] == 1
        # Jaccard: {"politics"} & {"politics","geopolitics"} / union = 1/3
        assert result["category_overlap_score"] > 0

    def test_empty_signals(self) -> None:
        result = collect_news_in_window([], 100_000, window_hours=24)
        assert result["count"] == 0
        assert result["mean_relevance"] == 0.0


# ===========================================================================
# compute_spearman_correlation
# ===========================================================================


class TestSpearmanCorrelation:
    def test_sufficient_data(self) -> None:
        """>= 5 points returns valid rho and p-value."""
        # Perfect rank correlation: larger delta_p → more news
        movements = [(0.05, 1), (0.10, 2), (0.15, 3), (0.20, 4), (0.25, 5)]
        rho, pval = compute_spearman_correlation(movements)
        assert rho is not None
        assert pval is not None
        assert rho == pytest.approx(1.0, abs=0.01)

    def test_insufficient_data(self) -> None:
        """< 5 points returns (None, None)."""
        movements = [(0.10, 2), (0.15, 3)]
        rho, pval = compute_spearman_correlation(movements)
        assert rho is None
        assert pval is None

    def test_constant_input_returns_none(self) -> None:
        """All news_counts identical → NaN handled, returns None."""
        movements = [(0.10, 3), (0.20, 3), (0.15, 3), (0.25, 3), (0.05, 3)]
        rho, pval = compute_spearman_correlation(movements)
        assert rho is None
        assert pval is None


# ===========================================================================
# compute_granger_causality
# ===========================================================================


class TestGrangerCausality:
    def test_without_statsmodels(self) -> None:
        """Returns (None, None, None) when statsmodels is not available."""
        with patch.dict("sys.modules", {"statsmodels": None, "statsmodels.tsa.stattools": None}):
            f, p, lag = compute_granger_causality([1, 2, 3, 4, 5], [0.1, 0.2, 0.1, 0.3, 0.1])
        assert f is None
        assert p is None
        assert lag is None

    def test_insufficient_data(self) -> None:
        """Too few observations returns None."""
        f, p, lag = compute_granger_causality([1, 2], [0.1, 0.2], max_lag=1)
        assert f is None
