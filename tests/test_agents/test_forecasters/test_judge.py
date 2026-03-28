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


# ── Market persona helpers (Phase 4) ────────────────────────────────


class TestBuildMarketIndex:
    """Test market index construction from foresight signals."""

    def test_filters_non_polymarket(self):
        from src.agents.forecasters.judge import Judge

        signals = [
            {"source": "gdelt", "title": "News", "probability": 0.5, "volume_usd": 50000},
            {"source": "polymarket", "title": "Will X?", "probability": 0.6, "volume_usd": 50000},
        ]
        index = Judge._build_market_index(signals)
        assert len(index) == 1
        assert "will x?" in index

    def test_filters_none_probability(self):
        from src.agents.forecasters.judge import Judge

        signals = [
            {"source": "polymarket", "title": "No prob", "probability": None, "volume_usd": 50000},
        ]
        assert Judge._build_market_index(signals) == {}

    def test_filters_low_liquidity(self):
        from src.agents.forecasters.judge import Judge

        signals = [
            {"source": "polymarket", "title": "Tiny", "probability": 0.5, "volume_usd": 500},
        ]
        assert Judge._build_market_index(signals) == {}

    def test_uses_liquidity_field_over_volume(self):
        from src.agents.forecasters.judge import Judge

        signals = [
            {
                "source": "polymarket",
                "title": "Has liq",
                "probability": 0.5,
                "liquidity": 50000,
                "volume_usd": 500,
            },
        ]
        index = Judge._build_market_index(signals)
        assert len(index) == 1

    def test_empty_signals(self):
        from src.agents.forecasters.judge import Judge

        assert Judge._build_market_index([]) == {}


class TestMatchMarketToThread:
    """Test market-to-event matching."""

    def _make_pred(self, prediction: str = "Something will happen", prob: float = 0.5):
        """Create a mock prediction with needed attributes."""
        from unittest.mock import MagicMock

        pred = MagicMock()
        pred.prediction = prediction
        pred.probability = prob
        return pred

    def test_tier1_high_similarity(self):
        from src.agents.forecasters.judge import Judge

        index = {
            "will bitcoin exceed 100k": {"title": "Will Bitcoin exceed 100k", "probability": 0.6},
        }
        preds = {"realist": self._make_pred("Bitcoin will exceed 100k by year end")}
        result = Judge._match_market_to_thread("bitcoin_price", preds, index)
        assert result is not None
        assert result["probability"] == 0.6

    def test_no_match_low_similarity(self):
        from src.agents.forecasters.judge import Judge

        index = {
            "will mars colony be established": {"title": "Mars colony", "probability": 0.1},
        }
        preds = {"realist": self._make_pred("Central bank will raise rates")}
        result = Judge._match_market_to_thread("interest_rates", preds, index)
        assert result is None

    def test_empty_index_returns_none(self):
        from src.agents.forecasters.judge import Judge

        preds = {"realist": self._make_pred("Something")}
        assert Judge._match_market_to_thread("event", preds, {}) is None


class TestComputeMarketWeight:
    """Test dynamic market weight computation."""

    def test_high_liquidity_high_weight(self):
        from src.agents.forecasters.judge import Judge

        market = {"liquidity": 1_000_000, "volatility_7d": 0.0, "distribution_reliable": True}
        weight = Judge._compute_market_weight(market)
        # base * 1.0 (full liquidity) * 1.0 (no vol) * 1.0 (reliable)
        assert weight == 0.15

    def test_low_liquidity_lower_weight(self):
        from src.agents.forecasters.judge import Judge

        market = {"liquidity": 100, "volatility_7d": 0.0, "distribution_reliable": True}
        weight = Judge._compute_market_weight(market)
        assert weight < 0.15

    def test_high_volatility_discounts(self):
        from src.agents.forecasters.judge import Judge

        base_market = {"liquidity": 500_000, "volatility_7d": 0.0, "distribution_reliable": True}
        vol_market = {"liquidity": 500_000, "volatility_7d": 0.8, "distribution_reliable": True}
        assert Judge._compute_market_weight(vol_market) < Judge._compute_market_weight(base_market)

    def test_unreliable_zero_weight(self):
        from src.agents.forecasters.judge import Judge

        market = {"liquidity": 1_000_000, "volatility_7d": 0.0, "distribution_reliable": False}
        assert Judge._compute_market_weight(market) == 0.0

    def test_missing_fields_defaults(self):
        from src.agents.forecasters.judge import Judge

        # No explicit fields — should use defaults safely
        market = {"volume_usd": 50_000}
        weight = Judge._compute_market_weight(market)
        assert weight > 0  # distribution_reliable defaults to True
