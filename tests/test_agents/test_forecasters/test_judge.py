"""Tests for Judge agent (Stage 6)."""

from __future__ import annotations


class TestPlattScale:
    """Test Platt scaling (extremization)."""

    def test_pushes_above_half_higher(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        result = judge._platt_scale(0.65)
        assert result > 0.65

    def test_pushes_below_half_lower(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        result = judge._platt_scale(0.35)
        assert result < 0.35

    def test_half_stays_at_half(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        result = judge._platt_scale(0.5)
        assert abs(result - 0.5) < 0.001

    def test_symmetry(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        high = judge._platt_scale(0.65)
        low = judge._platt_scale(0.35)
        assert abs(high + low - 1.0) < 0.001

    def test_clamps_extreme_values(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        assert 0.0 < judge._platt_scale(0.01) < 1.0
        assert 0.0 < judge._platt_scale(0.99) < 1.0


class TestWeightedMedian:
    """Test weighted median computation."""

    def test_equal_weights_returns_median(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        probs = [0.3, 0.5, 0.7]
        weights = [1.0, 1.0, 1.0]
        result = judge._weighted_median(probs, weights)
        assert result == 0.5

    def test_high_weight_on_high_value(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        probs = [0.3, 0.5, 0.7]
        weights = [1.0, 1.0, 10.0]
        result = judge._weighted_median(probs, weights)
        assert result == 0.7

    def test_single_value(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        result = judge._weighted_median([0.42], [1.0])
        assert result == 0.42


class TestHeadlineScore:
    """Test headline_score computation."""

    def test_product_of_factors(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        score = judge._headline_score(
            calibrated_prob=0.8,
            newsworthiness=0.9,
            saturation=0.1,
            outlet_relevance=1.0,
        )
        expected = 0.8 * 0.9 * (1.0 - 0.1) * 1.0
        assert abs(score - expected) < 0.001

    def test_zero_newsworthiness_gives_zero(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        score = judge._headline_score(0.8, 0.0, 0.0, 1.0)
        assert score == 0.0


class TestProbToLabel:
    """Test confidence label assignment."""

    def test_very_high(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import ConfidenceLabel

        assert Judge._prob_to_label(0.90) == ConfidenceLabel.VERY_HIGH

    def test_high(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import ConfidenceLabel

        assert Judge._prob_to_label(0.75) == ConfidenceLabel.HIGH

    def test_moderate(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import ConfidenceLabel

        assert Judge._prob_to_label(0.55) == ConfidenceLabel.MODERATE

    def test_low(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import ConfidenceLabel

        assert Judge._prob_to_label(0.35) == ConfidenceLabel.LOW

    def test_speculative(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import ConfidenceLabel

        assert Judge._prob_to_label(0.15) == ConfidenceLabel.SPECULATIVE


class TestAssessAgreement:
    """Test agreement level classification."""

    def test_consensus(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import AgreementLevel

        judge = Judge.__new__(Judge)
        level, spread = judge._assess_agreement([0.60, 0.62, 0.65, 0.68, 0.70])
        assert level == AgreementLevel.CONSENSUS
        assert spread < 0.15

    def test_majority_with_dissent(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import AgreementLevel

        judge = Judge.__new__(Judge)
        level, spread = judge._assess_agreement([0.40, 0.50, 0.55, 0.58, 0.60])
        assert level == AgreementLevel.MAJORITY_WITH_DISSENT

    def test_contested(self):
        from src.agents.forecasters.judge import Judge
        from src.schemas.headline import AgreementLevel

        judge = Judge.__new__(Judge)
        level, spread = judge._assess_agreement([0.20, 0.40, 0.50, 0.70, 0.80])
        assert level == AgreementLevel.CONTESTED
        assert spread > 0.30


class TestJudgeValidation:
    """Test validate_context."""

    def test_no_round2_assessments_returns_error(self, mock_router, make_context):
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.mediator_synthesis = {"some": "data"}
        assert judge.validate_context(ctx) is not None

    def test_no_mediator_synthesis_returns_error(self, mock_router, make_context):
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.round2_assessments = [{"some": "data"}]
        assert judge.validate_context(ctx) is not None

    def test_valid_context(self, mock_router, make_context):
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.round2_assessments = [{"some": "data"}]
        ctx.mediator_synthesis = {"some": "data"}
        assert judge.validate_context(ctx) is None
