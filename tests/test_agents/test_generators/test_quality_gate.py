"""Tests for QualityGate agent (Stage 9)."""

from __future__ import annotations

import json

import pytest

from src.schemas.headline import CheckResult

from .conftest import (
    make_framing_brief,
    make_generated_headline,
    make_llm_response,
    make_outlet_profile,
    make_quality_score,
    make_ranked_prediction,
)


class TestGateDecision:
    """Test _make_decision() logic."""

    def test_pass_when_both_scores_ok(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(factual_score=4, style_score=4)
        assert gate._make_decision(score) == GateDecision.PASS

    def test_reject_when_factual_low(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(factual_score=2, style_score=5)
        assert gate._make_decision(score) == GateDecision.REJECT

    def test_revise_when_style_low(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(factual_score=4, style_score=2)
        assert gate._make_decision(score) == GateDecision.REVISE

    def test_merge_when_internal_duplicate(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(
            factual_score=4, style_score=4, is_internal_duplicate=True, duplicate_of_id="other"
        )
        assert gate._make_decision(score) == GateDecision.MERGE

    def test_deprioritize_when_external_duplicate(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(factual_score=4, style_score=4, is_external_duplicate=True)
        assert gate._make_decision(score) == GateDecision.DEPRIORITIZE

    def test_factual_reject_takes_priority_over_duplicate(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate
        from src.schemas.headline import GateDecision

        gate = QualityGate(llm_client=mock_router)
        score = make_quality_score(factual_score=1, style_score=5, is_internal_duplicate=True)
        assert gate._make_decision(score) == GateDecision.REJECT


class TestDedup:
    """Test _check_internal_duplicates() with SequenceMatcher."""

    def test_identical_headlines_flagged(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        h1 = make_generated_headline(headline="ЦБ повысит ставку до 23%")
        h2 = make_generated_headline(headline="ЦБ повысит ставку до 23%")
        scores = [
            make_quality_score(headline_id=h1.id, factual_score=4, style_score=4),
            make_quality_score(headline_id=h2.id, factual_score=3, style_score=3),
        ]

        pairs = list(zip([h1, h2], scores))
        gate._check_internal_duplicates(pairs)

        # One of them should be marked as duplicate
        assert scores[0].is_internal_duplicate or scores[1].is_internal_duplicate

    def test_different_headlines_not_flagged(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        h1 = make_generated_headline(headline="ЦБ повысит ставку до 23%")
        h2 = make_generated_headline(headline="Путин подписал указ о бюджете")
        scores = [
            make_quality_score(headline_id=h1.id),
            make_quality_score(headline_id=h2.id),
        ]

        pairs = list(zip([h1, h2], scores))
        gate._check_internal_duplicates(pairs)

        assert not scores[0].is_internal_duplicate
        assert not scores[1].is_internal_duplicate

    def test_external_duplicates_flagged(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        h1 = make_generated_headline(headline="ЦБ повысит ставку до 23%")
        score = make_quality_score(headline_id=h1.id)

        pairs = [(h1, score)]
        existing = ["ЦБ повысит ставку до 23%"]
        gate._check_external_duplicates(pairs, existing)

        assert score.is_external_duplicate


class TestQualityGateValidation:
    """Test validate_context."""

    def test_no_headlines_returns_error(self, mock_router, make_context):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        assert gate.validate_context(ctx) is not None

    def test_valid_context(self, mock_router, make_context):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        ctx.generated_headlines = [make_generated_headline()]
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()
        assert gate.validate_context(ctx) is None


class TestQualityGateExecute:
    """Test execute() with mock LLM."""

    @pytest.mark.asyncio
    async def test_returns_final_predictions(self, mock_router, make_context):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        ctx.generated_headlines = [make_generated_headline()]
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        # Mock: factual check returns score 4, style check returns score 4
        check_ok = json.dumps({"score": 4, "feedback": "Looks good."})
        mock_router.complete.return_value = make_llm_response(check_ok)

        result = await gate.execute(ctx)

        assert "final_predictions" in result
        assert len(result["final_predictions"]) >= 1

    @pytest.mark.asyncio
    async def test_rejected_headline_excluded(self, mock_router, make_context):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        ctx.generated_headlines = [make_generated_headline()]
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        # Mock: factual check returns score 1 → REJECT
        check_fail = json.dumps({"score": 1, "feedback": "Factually incorrect."})
        mock_router.complete.return_value = make_llm_response(check_fail)

        result = await gate.execute(ctx)

        assert result["final_predictions"] == []

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(self, mock_router, make_context):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        ctx.generated_headlines = [make_generated_headline()]
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        check_ok = json.dumps({"score": 4, "feedback": "Good."})
        mock_router.complete.return_value = make_llm_response(check_ok)

        await gate.execute(ctx)

        assert gate._cost_usd > 0
        assert gate._tokens_in > 0


class TestQualityGateParseErrors:
    """Test that _check_factual/_check_style catch PromptParseError internally."""

    @pytest.mark.asyncio
    async def test_check_factual_parse_error_returns_neutral(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        headline = make_generated_headline()
        prediction = make_ranked_prediction()

        mock_router.complete.return_value = make_llm_response("INVALID JSON")

        # _check_factual must return neutral CheckResult, not raise
        result = await gate._check_factual(headline, prediction)
        assert result.score == 3
        assert "parse" in result.feedback.lower() or "could not" in result.feedback.lower()

    @pytest.mark.asyncio
    async def test_check_style_parse_error_returns_neutral(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        headline = make_generated_headline()
        profile = make_outlet_profile()

        mock_router.complete.return_value = make_llm_response("INVALID JSON")

        # _check_style must return neutral CheckResult, not raise
        result = await gate._check_style(headline, profile)
        assert result.score == 3
        assert "parse" in result.feedback.lower() or "could not" in result.feedback.lower()

    @pytest.mark.asyncio
    async def test_full_preset_parse_error_does_not_reject(self, mock_router, make_context):
        """With min_score=4, fallback score must equal min_score so headline isn't rejected."""
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        ctx = make_context()
        ctx.generated_headlines = [make_generated_headline()]
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()
        ctx.pipeline_config["quality_gate_min_score"] = 4

        # ALL LLM calls return invalid JSON → fallback scores
        mock_router.complete.return_value = make_llm_response("INVALID JSON")

        result = await gate.execute(ctx)

        # With preset-aware fallback, headline should PASS (not be rejected)
        assert len(result["final_predictions"]) >= 1


class TestBuildFinalPredictions:
    """Test _build_final_predictions helper."""

    def test_groups_variants_by_event(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        headlines = [
            make_generated_headline(event_thread_id="t1", variant_number=1, headline="Variant A"),
            make_generated_headline(event_thread_id="t1", variant_number=2, headline="Variant B"),
            make_generated_headline(
                event_thread_id="t2", variant_number=1, headline="Other event"
            ),
        ]
        pred_index = {
            "t1": make_ranked_prediction(event_thread_id="t1", rank=1),
            "t2": make_ranked_prediction(event_thread_id="t2", rank=2),
        }
        framing_index = {
            "t1": make_framing_brief(event_thread_id="t1"),
            "t2": make_framing_brief(event_thread_id="t2"),
        }

        finals = gate._build_final_predictions(headlines, pred_index, framing_index)

        assert len(finals) == 2
        # First event has 1 alternative
        t1_pred = next(f for f in finals if f["event_thread_id"] == "t1")
        assert t1_pred["headline"] == "Variant A"
        assert len(t1_pred["alternative_headlines"]) == 1
        assert t1_pred["alternative_headlines"][0] == "Variant B"

    def test_sorted_by_rank(self, mock_router):
        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        headlines = [
            make_generated_headline(event_thread_id="t2", variant_number=1),
            make_generated_headline(event_thread_id="t1", variant_number=1),
        ]
        pred_index = {
            "t1": make_ranked_prediction(event_thread_id="t1", rank=1),
            "t2": make_ranked_prediction(event_thread_id="t2", rank=2),
        }
        framing_index = {
            "t1": make_framing_brief(event_thread_id="t1"),
            "t2": make_framing_brief(event_thread_id="t2"),
        }

        finals = gate._build_final_predictions(headlines, pred_index, framing_index)

        assert finals[0]["rank"] == 1
        assert finals[1]["rank"] == 2


class TestQualityGateConcurrency:
    """Test concurrent execution of scoring checks."""

    @pytest.mark.asyncio
    async def test_score_one_runs_factual_and_style_concurrently(self, mock_router):
        """Factual and style checks within _score_one should run in parallel."""
        import asyncio
        import time
        from unittest.mock import AsyncMock, patch

        from src.agents.generators.quality_gate import QualityGate

        gate = QualityGate(llm_client=mock_router)
        headline = make_generated_headline()
        prediction = make_ranked_prediction()
        profile = make_outlet_profile()

        async def slow_factual(*args, **kwargs):
            await asyncio.sleep(0.1)
            return CheckResult(score=4, feedback="ok")

        async def slow_style(*args, **kwargs):
            await asyncio.sleep(0.1)
            return CheckResult(score=4, feedback="ok")

        with (
            patch.object(gate, "_check_factual", side_effect=slow_factual),
            patch.object(gate, "_check_style", side_effect=slow_style),
        ):
            start = time.monotonic()
            score = await gate._score_one(headline, prediction, profile)
            elapsed = time.monotonic() - start

        # If parallel: ~0.1s. If sequential: ~0.2s.
        assert elapsed < 0.15, f"Expected concurrent execution, but took {elapsed:.3f}s"
        assert score.factual_score == 4
        assert score.style_score == 4
