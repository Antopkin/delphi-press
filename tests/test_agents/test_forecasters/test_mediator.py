"""Tests for Mediator agent (Stage 5)."""

from __future__ import annotations

import json

import pytest

from .conftest import (
    make_llm_response,
    make_mediator_synthesis,
    make_persona_assessment,
    make_prediction_item,
)


class TestMediatorClassification:
    """Test algorithmic classification of predictions."""

    def _make_5_preds(self, thread_id: str, probability: float) -> list:
        """Make 5 predictions (min required by schema) with one target thread."""
        return [
            make_prediction_item(thread_id, probability=probability),
            *[make_prediction_item(f"filler_{j}", probability=0.5) for j in range(4)],
        ]

    def test_consensus_when_spread_low(self):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        assessments = [
            make_persona_assessment(
                f"persona_{i}",
                predictions=self._make_5_preds("thread_0001", probability=0.60 + i * 0.02),
            )
            for i in range(5)
        ]
        consensus, disputes, gaps = mediator._classify_events(assessments)
        consensus_ids = [c.event_thread_id for c in consensus]
        assert "thread_0001" in consensus_ids

    def test_dispute_when_spread_high(self):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        assessments = [
            make_persona_assessment(
                f"persona_{i}",
                predictions=self._make_5_preds("thread_0001", probability=0.3 + i * 0.1),
            )
            for i in range(5)
        ]
        consensus, disputes, gaps = mediator._classify_events(assessments)
        dispute_ids = [d.event_thread_id for d in disputes]
        assert "thread_0001" in dispute_ids

    def test_gap_when_few_agents(self):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        # Only 2 agents mention thread_rare, all 5 mention fillers
        base_preds = [make_prediction_item(f"filler_{j}", probability=0.5) for j in range(4)]
        assessments = [
            make_persona_assessment(
                "persona_0",
                predictions=[
                    make_prediction_item("thread_common", probability=0.5),
                    make_prediction_item("thread_rare", probability=0.3),
                    *base_preds[:3],
                ],
            ),
            make_persona_assessment(
                "persona_1",
                predictions=[
                    make_prediction_item("thread_common", probability=0.55),
                    make_prediction_item("thread_rare", probability=0.35),
                    *base_preds[:3],
                ],
            ),
            make_persona_assessment(
                "persona_2",
                predictions=self._make_5_preds("thread_common", probability=0.52),
            ),
            make_persona_assessment(
                "persona_3",
                predictions=self._make_5_preds("thread_common", probability=0.48),
            ),
            make_persona_assessment(
                "persona_4",
                predictions=self._make_5_preds("thread_common", probability=0.51),
            ),
        ]
        consensus, disputes, gaps = mediator._classify_events(assessments)
        gap_ids = [g.event_thread_id for g in gaps]
        assert "thread_rare" in gap_ids


class TestMediatorAnonymize:
    """Test anonymization of assessments."""

    def test_labels_are_expert_a_b_c(self):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        assessments = [make_persona_assessment(f"persona_{i}") for i in range(3)]
        anonymized = mediator._anonymize_assessments(assessments)
        labels = list(anonymized.keys())
        assert len(labels) == 3
        for label in labels:
            assert label.startswith("Expert ")
        # Values should be dicts (not PersonaAssessment)
        for val in anonymized.values():
            assert isinstance(val, dict)

    def test_persona_id_not_leaked(self):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        assessments = [make_persona_assessment("secret_persona")]  # uses default 5 preds
        anonymized = mediator._anonymize_assessments(assessments)
        serialized = json.dumps(anonymized, default=str)
        assert "secret_persona" not in serialized


class TestMediatorCrossImpact:
    """Test cross-impact flag detection."""

    def test_flags_dependency_on_disputed_event(self):
        from src.agents.forecasters.mediator import Mediator
        from src.schemas.agent import DisputeArea

        mediator = Mediator.__new__(Mediator)
        preds = [
            make_prediction_item("thread_A", probability=0.6, conditional_on=["thread_B"]),
            *[make_prediction_item(f"filler_{j}", probability=0.5) for j in range(4)],
        ]
        assessments = [
            make_persona_assessment("p1", predictions=preds),
        ]
        disputes = [
            DisputeArea(
                event_thread_id="thread_B",
                median_probability=0.5,
                spread=0.30,
                positions=[],
                key_question="What happens?",
            )
        ]
        flags = mediator._check_cross_impacts(assessments, disputes)
        assert len(flags) == 1
        assert flags[0].depends_on_event_id == "thread_B"


class TestMediatorValidation:
    """Test validate_context."""

    def test_no_assessments_returns_error(self, mock_router, make_context):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator(llm_client=mock_router)
        ctx = make_context()
        assert mediator.validate_context(ctx) is not None

    def test_valid_with_assessments(self, mock_router, make_context):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator(llm_client=mock_router)
        ctx = make_context()
        ctx.round1_assessments = [make_persona_assessment(f"p{i}") for i in range(4)]
        assert mediator.validate_context(ctx) is None


class TestMediatorExecute:
    """Test execute() with mock LLM."""

    @pytest.mark.asyncio
    async def test_returns_synthesis(self, mock_router, make_context):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator(llm_client=mock_router)
        ctx = make_context()
        # All 5 assessments share the same 5 threads from conftest default
        ctx.round1_assessments = [make_persona_assessment(f"p{i}") for i in range(5)]
        ctx.trajectories = []

        synthesis_data = make_mediator_synthesis().model_dump()
        mock_router.complete.return_value = make_llm_response(
            json.dumps(synthesis_data, default=str)
        )

        result = await mediator.execute(ctx)

        assert "synthesis" in result
        mock_router.complete.assert_called_once()
        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "mediator"

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(self, mock_router, make_context):
        from src.agents.forecasters.mediator import Mediator

        mediator = Mediator(llm_client=mock_router)
        ctx = make_context()
        ctx.round1_assessments = [make_persona_assessment(f"p{i}") for i in range(5)]
        ctx.trajectories = []

        synthesis_data = make_mediator_synthesis().model_dump()
        mock_router.complete.return_value = make_llm_response(
            json.dumps(synthesis_data, default=str)
        )

        await mediator.execute(ctx)
        assert mediator._cost_usd > 0
        assert mediator._tokens_in > 0
