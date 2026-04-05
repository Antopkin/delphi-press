"""Tests for Murphy decomposition, calibration slope, and ECE — Phase 3 Step 2."""

from __future__ import annotations

import pytest

from src.eval.metrics import (
    BrierDecomposition,
    brier_decomposition,
    calibration_slope,
    expected_calibration_error,
)

# ---------------------------------------------------------------------------
# Murphy decomposition
# ---------------------------------------------------------------------------


class TestBrierDecomposition:
    def test_perfect_predictions(self) -> None:
        """Perfect predictions: REL=0, BS=0."""
        probs = [1.0, 0.0, 1.0, 0.0]
        outcomes = [1.0, 0.0, 1.0, 0.0]
        result = brier_decomposition(probs, outcomes)
        assert isinstance(result, BrierDecomposition)
        assert result.reliability == pytest.approx(0.0, abs=1e-6)

    def test_worst_predictions(self) -> None:
        """Completely wrong predictions: high REL."""
        probs = [0.0, 1.0, 0.0, 1.0]
        outcomes = [1.0, 0.0, 1.0, 0.0]
        result = brier_decomposition(probs, outcomes)
        assert result.reliability > 0.5

    def test_bs_equals_rel_minus_res_plus_unc(self) -> None:
        """Verify: BS = REL - RES + UNC (Murphy identity)."""
        probs = [0.8, 0.3, 0.9, 0.1, 0.6, 0.7, 0.2, 0.4, 0.5, 0.85]
        outcomes = [1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0]
        result = brier_decomposition(probs, outcomes, n_bins=5)
        bs_computed = result.reliability - result.resolution + result.uncertainty
        # Should approximately equal actual Brier Score
        actual_bs = sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)
        assert bs_computed == pytest.approx(actual_bs, abs=0.05)

    def test_degenerate_few_bins(self) -> None:
        """With very few distinct probabilities, should still return valid result."""
        probs = [0.5, 0.5, 0.5, 0.5]
        outcomes = [1.0, 0.0, 1.0, 0.0]
        result = brier_decomposition(probs, outcomes, n_bins=10)
        assert result.uncertainty == pytest.approx(0.25, abs=1e-6)

    def test_empty_raises(self) -> None:
        """Empty inputs should raise ValueError."""
        with pytest.raises(ValueError):
            brier_decomposition([], [])

    def test_result_is_frozen_dataclass(self) -> None:
        """Result should be a frozen dataclass."""
        result = brier_decomposition([0.5, 0.5], [1.0, 0.0])
        with pytest.raises(AttributeError):
            result.reliability = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Calibration slope
# ---------------------------------------------------------------------------


class TestCalibrationSlope:
    def test_perfect_calibration(self) -> None:
        """Perfectly calibrated predictions → slope ≈ 1.0."""
        # Groups: 20% outcome rate at p=0.2, 80% at p=0.8
        probs = [0.2] * 50 + [0.8] * 50
        outcomes = [1.0] * 10 + [0.0] * 40 + [1.0] * 40 + [0.0] * 10
        slope = calibration_slope(probs, outcomes)
        assert slope == pytest.approx(1.0, abs=0.15)

    def test_overconfident(self) -> None:
        """Overconfident predictions (extreme probs, moderate outcomes) → slope < 1.0."""
        probs = [0.05] * 50 + [0.95] * 50
        outcomes = [0.0] * 35 + [1.0] * 15 + [1.0] * 35 + [0.0] * 15
        slope = calibration_slope(probs, outcomes)
        assert slope < 1.0

    def test_empty_raises(self) -> None:
        """Empty inputs should raise ValueError."""
        with pytest.raises(ValueError):
            calibration_slope([], [])


# ---------------------------------------------------------------------------
# Expected Calibration Error
# ---------------------------------------------------------------------------


class TestExpectedCalibrationError:
    def test_perfect_calibration(self) -> None:
        """Well-calibrated predictions → low ECE."""
        # Generate calibrated data: p=0.3 with 30% outcome, p=0.7 with 70%
        import random

        random.seed(42)
        probs = []
        outcomes = []
        for _ in range(200):
            p = random.choice([0.3, 0.7])
            probs.append(p)
            outcomes.append(1.0 if random.random() < p else 0.0)
        ece = expected_calibration_error(probs, outcomes, n_bins=5)
        assert ece < 0.15  # Not exactly 0 due to finite sample, but low

    def test_worst_calibration(self) -> None:
        """Completely miscalibrated predictions → high ECE."""
        probs = [0.1] * 50 + [0.9] * 50
        outcomes = [1.0] * 50 + [0.0] * 50
        ece = expected_calibration_error(probs, outcomes)
        assert ece > 0.5

    def test_output_in_valid_range(self) -> None:
        """ECE should be in [0, 1]."""
        probs = [0.3, 0.7, 0.5, 0.2, 0.8]
        outcomes = [0.0, 1.0, 1.0, 0.0, 1.0]
        ece = expected_calibration_error(probs, outcomes)
        assert 0.0 <= ece <= 1.0

    def test_empty_raises(self) -> None:
        """Empty inputs should raise ValueError."""
        with pytest.raises(ValueError):
            expected_calibration_error([], [])
