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

    def test_no_mediator_synthesis_still_valid(self, mock_router, make_context):
        """Mediator synthesis is optional (single-round presets skip R2)."""
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.round2_assessments = [{"some": "data"}]
        assert judge.validate_context(ctx) is None

    def test_valid_context(self, mock_router, make_context):
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.round2_assessments = [{"some": "data"}]
        ctx.mediator_synthesis = {"some": "data"}
        assert judge.validate_context(ctx) is None

    def test_fallback_to_round1(self, mock_router, make_context):
        """Judge accepts R1 assessments when R2 is empty."""
        from src.agents.forecasters.judge import Judge

        judge = Judge(llm_client=mock_router)
        ctx = make_context()
        ctx.round1_assessments = [{"some": "data"}]
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

    def test_very_high_volatility_still_positive(self):
        """Hyperbolic vol discount never reaches zero (unlike old linear clipping)."""
        from src.agents.forecasters.judge import Judge

        market = {"liquidity": 1_000_000, "volatility_7d": 5.0, "distribution_reliable": True}
        weight = Judge._compute_market_weight(market)
        assert weight > 0
        # vol=5 → discount = 1/(1+5) ≈ 0.167, much lower than base
        assert weight < 0.15 * 0.2

    def test_hyperbolic_vol_discount_values(self):
        """Verify specific hyperbolic discount values."""
        from src.agents.forecasters.judge import Judge

        base = {"liquidity": 1_000_000, "distribution_reliable": True}
        # vol=0 → discount=1.0
        w0 = Judge._compute_market_weight({**base, "volatility_7d": 0.0})
        # vol=1 → discount=0.5
        w1 = Judge._compute_market_weight({**base, "volatility_7d": 1.0})
        assert abs(w1 / w0 - 0.5) < 0.01

    def test_long_horizon_market_lower_weight(self):
        """Markets ending >180 days out get horizon_factor=0.5."""
        from datetime import UTC, datetime, timedelta

        from src.agents.forecasters.judge import Judge

        base = {"liquidity": 1_000_000, "volatility_7d": 0.0, "distribution_reliable": True}
        short = {**base, "end_date": (datetime.now(UTC) + timedelta(days=20)).isoformat()}
        long = {**base, "end_date": (datetime.now(UTC) + timedelta(days=200)).isoformat()}

        w_short = Judge._compute_market_weight(short)
        w_long = Judge._compute_market_weight(long)
        assert w_long < w_short
        assert abs(w_long / w_short - 0.5) < 0.01  # horizon_factor=0.5

    def test_medium_horizon_market_moderate_weight(self):
        """Markets ending 90-180 days out get horizon_factor=0.75."""
        from datetime import UTC, datetime, timedelta

        from src.agents.forecasters.judge import Judge

        base = {"liquidity": 1_000_000, "volatility_7d": 0.0, "distribution_reliable": True}
        short = {**base, "end_date": (datetime.now(UTC) + timedelta(days=20)).isoformat()}
        medium = {**base, "end_date": (datetime.now(UTC) + timedelta(days=120)).isoformat()}

        w_short = Judge._compute_market_weight(short)
        w_medium = Judge._compute_market_weight(medium)
        assert w_medium < w_short
        assert abs(w_medium / w_short - 0.75) < 0.01

    def test_no_end_date_horizon_factor_one(self):
        """Missing end_date → horizon_factor stays 1.0."""
        from src.agents.forecasters.judge import Judge

        market = {"liquidity": 1_000_000, "volatility_7d": 0.0, "distribution_reliable": True}
        weight = Judge._compute_market_weight(market)
        assert weight == 0.15  # no discount


# ── Temporal aggregation helpers ────────────────────────────────────


class TestAggregateDate:
    """Test predicted_date aggregation from persona predictions."""

    def test_median_date_from_multiple_personas(self):
        from datetime import date
        from unittest.mock import MagicMock

        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        preds = {}
        for i, d in enumerate([date(2026, 4, 1), date(2026, 4, 3), date(2026, 4, 5)]):
            p = MagicMock()
            p.predicted_date = d
            p.uncertainty_days = 1.0
            preds[f"persona_{i}"] = p

        result_date, result_unc = judge._aggregate_date(preds, date(2026, 4, 2))
        assert result_date == date(2026, 4, 3)  # median
        assert result_unc == 1.0

    def test_fallback_to_target_date_when_no_dates(self):
        from datetime import date
        from unittest.mock import MagicMock

        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        preds = {"p1": MagicMock(predicted_date=None, uncertainty_days=1.0)}

        result_date, result_unc = judge._aggregate_date(preds, date(2026, 4, 1))
        assert result_date == date(2026, 4, 1)
        assert result_unc == 1.0

    def test_mean_uncertainty(self):
        from datetime import date
        from unittest.mock import MagicMock

        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        preds = {}
        for i, unc in enumerate([0.5, 1.5, 3.0]):
            p = MagicMock()
            p.predicted_date = date(2026, 4, 1)
            p.uncertainty_days = unc
            preds[f"p_{i}"] = p

        _, result_unc = judge._aggregate_date(preds, date(2026, 4, 1))
        assert abs(result_unc - (0.5 + 1.5 + 3.0) / 3) < 0.01


class TestAggregateCausalDeps:
    """Test causal dependencies union."""

    def test_union_of_deps(self):
        from unittest.mock import MagicMock

        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        p1 = MagicMock(causal_dependencies=["t1", "t2"])
        p2 = MagicMock(causal_dependencies=["t2", "t3"])
        deps = judge._aggregate_causal_deps({"a": p1, "b": p2})
        assert deps == ["t1", "t2", "t3"]

    def test_empty_when_no_deps(self):
        from unittest.mock import MagicMock

        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        p1 = MagicMock(causal_dependencies=[])
        assert judge._aggregate_causal_deps({"a": p1}) == []


# ── Aggregate timeline (Step 6a) ───────────────────────────────────


class TestAggregateTimeline:
    """Test _aggregate_timeline returns PredictedTimeline."""

    def _make_judge(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        return judge

    def test_returns_predicted_timeline(self, make_context):
        from datetime import date, timedelta

        from src.schemas.timeline import PredictedTimeline

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=2)

        from tests.test_agents.test_forecasters.conftest import make_persona_assessment

        assessments = [
            make_persona_assessment("realist", predictions=None),
            make_persona_assessment("economist", predictions=None),
            make_persona_assessment("geostrateg", predictions=None),
        ]
        timeline = judge._aggregate_timeline(assessments, ctx)
        assert isinstance(timeline, PredictedTimeline)
        assert len(timeline.entries) > 0
        assert timeline.target_date == ctx.target_date

    def test_temporal_order_assigned(self, make_context):
        from datetime import date, timedelta

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=3)

        from tests.test_agents.test_forecasters.conftest import make_persona_assessment

        assessments = [make_persona_assessment("realist")]
        timeline = judge._aggregate_timeline(assessments, ctx)
        for entry in timeline.entries:
            assert entry.temporal_order >= 1

    def test_horizon_band_computed(self, make_context):
        from datetime import date, timedelta

        from src.schemas.timeline import HorizonBand

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=1)

        from tests.test_agents.test_forecasters.conftest import make_persona_assessment

        assessments = [make_persona_assessment("realist")]
        timeline = judge._aggregate_timeline(assessments, ctx)
        assert timeline.horizon_band == HorizonBand.IMMEDIATE


# ── Select headlines (Step 6b) ─────────────────────────────────────


class TestSelectHeadlines:
    """Test _select_headlines maps timeline → RankedPrediction."""

    def _make_judge(self):
        from src.agents.forecasters.judge import Judge

        judge = Judge.__new__(Judge)
        judge.a = 1.5
        judge.b = 0.0
        judge.llm = None
        return judge

    def test_returns_ranked_predictions(self, make_context):
        from datetime import date, timedelta

        from src.schemas.headline import RankedPrediction

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=2)

        from tests.test_agents.test_forecasters.conftest import make_persona_assessment

        assessments = [
            make_persona_assessment("realist"),
            make_persona_assessment("economist"),
        ]
        timeline = judge._aggregate_timeline(assessments, ctx)
        ranked = judge._select_headlines(timeline, assessments, ctx)
        assert len(ranked) > 0
        assert all(isinstance(rp, RankedPrediction) for rp in ranked)

    def test_preserves_ranked_prediction_contract(self, make_context):
        """All required fields of RankedPrediction must be present."""
        from datetime import date, timedelta

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=2)

        from tests.test_agents.test_forecasters.conftest import make_persona_assessment

        assessments = [make_persona_assessment("realist")]
        timeline = judge._aggregate_timeline(assessments, ctx)
        ranked = judge._select_headlines(timeline, assessments, ctx)

        rp = ranked[0]
        assert hasattr(rp, "event_thread_id")
        assert hasattr(rp, "prediction")
        assert hasattr(rp, "calibrated_probability")
        assert hasattr(rp, "raw_probability")
        assert hasattr(rp, "headline_score")
        assert hasattr(rp, "newsworthiness")
        assert hasattr(rp, "confidence_label")
        assert hasattr(rp, "agreement_level")
        assert hasattr(rp, "spread")
        assert hasattr(rp, "reasoning")
        assert hasattr(rp, "evidence_chain")
        assert hasattr(rp, "dissenting_views")
        assert hasattr(rp, "is_wild_card")
        assert rp.rank >= 1

    def test_top_n_selection(self, make_context):
        from datetime import date, timedelta

        judge = self._make_judge()
        ctx = make_context()
        ctx.target_date = date.today() + timedelta(days=2)
        ctx.pipeline_config = {"max_headlines": 3}

        from tests.test_agents.test_forecasters.conftest import (
            make_persona_assessment,
            make_prediction_item,
        )

        # Create assessments with many threads
        preds = [
            make_prediction_item(f"thread_{i:04d}", probability=0.5 + i * 0.03) for i in range(10)
        ]
        assessments = [make_persona_assessment("realist", predictions=preds[:5])]
        # Add more threads via second persona
        preds2 = [
            make_prediction_item(f"thread_{i:04d}", probability=0.6 + i * 0.02)
            for i in range(5, 10)
        ]
        assessments.append(make_persona_assessment("economist", predictions=preds2))

        timeline = judge._aggregate_timeline(assessments, ctx)
        ranked = judge._select_headlines(timeline, assessments, ctx)
        # Should be at most 3 (top_n) + wild cards
        non_wild = [r for r in ranked if not r.is_wild_card]
        assert len(non_wild) <= 3
