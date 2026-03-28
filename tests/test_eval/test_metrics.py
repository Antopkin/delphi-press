"""Tests for src.eval.metrics.

Covers Brier Score (with bootstrap CI), Log Score, and Composite Score.
"""

from __future__ import annotations

import pytest

from src.eval.metrics import BrierResult, brier_score, composite_score, log_score


class TestBrierScore:
    """Brier Score computation and bootstrap CI."""

    def test_brier_score_perfect(self) -> None:
        """Perfect predictions yield BS ~ 0.0."""
        result = brier_score([1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0])
        assert isinstance(result, BrierResult)
        assert result.score == pytest.approx(0.0, abs=1e-9)
        assert result.n_predictions == 4

    def test_brier_score_random(self) -> None:
        """Always predicting 0.5 on balanced outcomes gives BS = 0.25."""
        probs = [0.5] * 10
        outcomes = [1.0] * 5 + [0.0] * 5
        result = brier_score(probs, outcomes)
        assert result.score == pytest.approx(0.25, abs=1e-9)

    def test_brier_skill_score(self) -> None:
        """BSS = 1 - BS / 0.25 for known values."""
        # Perfect: BS=0 => BSS=1
        perfect = brier_score([1.0, 0.0], [1.0, 0.0])
        assert perfect.skill_score == pytest.approx(1.0, abs=1e-9)

        # Random: BS=0.25 => BSS=0
        random = brier_score([0.5, 0.5, 0.5, 0.5], [1.0, 0.0, 1.0, 0.0])
        assert random.skill_score == pytest.approx(0.0, abs=1e-9)

    def test_bootstrap_ci(self) -> None:
        """CI bounds exist and ci_lower <= score <= ci_upper for a reasonable case."""
        probs = [0.7, 0.3, 0.8, 0.2, 0.6, 0.4, 0.9, 0.1, 0.5, 0.5]
        outcomes = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
        result = brier_score(probs, outcomes, n_bootstrap=2000)
        assert result.ci_lower <= result.score
        assert result.score <= result.ci_upper
        assert result.ci_lower >= 0.0
        assert result.ci_upper <= 1.0

    def test_brier_score_mismatched_lengths(self) -> None:
        """Mismatched list lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            brier_score([0.5, 0.5], [1.0])

    def test_brier_score_empty(self) -> None:
        """Empty lists should raise ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            brier_score([], [])


class TestLogScore:
    """Log Score computation."""

    def test_log_score_overconfident(self) -> None:
        """Very confident wrong prediction gives high (bad) log score."""
        # p=0.99 predicted event, but outcome=0 (didn't happen)
        score = log_score([0.99], [0.0])
        assert score > 2.0  # -log(0.01) ~ 4.6

    def test_log_score_perfect(self) -> None:
        """Near-perfect predictions give low log score."""
        score = log_score([0.99, 0.01], [1.0, 0.0])
        assert score < 0.05

    def test_log_score_mismatched_lengths(self) -> None:
        """Mismatched list lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            log_score([0.5], [1.0, 0.0])

    def test_log_score_empty(self) -> None:
        """Empty lists should raise ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            log_score([], [])


class TestCompositeScore:
    """Composite score weight verification."""

    def test_composite_score_all_ones(self) -> None:
        """All perfect scores should yield 1.0 (weights sum to 1)."""
        assert composite_score(1.0, 1.0, 1.0) == pytest.approx(1.0, abs=1e-9)

    def test_composite_score_topic_only(self) -> None:
        """Topic match only contributes 0.40."""
        assert composite_score(1.0, 0.0, 0.0) == pytest.approx(0.40, abs=1e-9)

    def test_composite_score_semantic_only(self) -> None:
        """Semantic similarity only contributes 0.35."""
        assert composite_score(0.0, 1.0, 0.0) == pytest.approx(0.35, abs=1e-9)

    def test_composite_score_style_only(self) -> None:
        """Style match only contributes 0.25."""
        assert composite_score(0.0, 0.0, 1.0) == pytest.approx(0.25, abs=1e-9)

    def test_composite_score_all_zeros(self) -> None:
        """All zeros yield 0.0."""
        assert composite_score(0.0, 0.0, 0.0) == pytest.approx(0.0, abs=1e-9)
