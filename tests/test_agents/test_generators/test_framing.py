"""Tests for FramingAnalyzer agent (Stage 7)."""

from __future__ import annotations

import json

import pytest

from .conftest import (
    make_framing_brief,
    make_llm_response,
    make_outlet_profile,
    make_ranked_prediction,
)


class TestFramingValidation:
    """Test validate_context."""

    def test_no_predictions_returns_error(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_no_outlet_profile_returns_error(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        assert agent.validate_context(ctx) is not None

    def test_valid_with_predictions_and_profile(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.outlet_profile = make_outlet_profile()
        assert agent.validate_context(ctx) is None


class TestFramingExecute:
    """Test execute() with mock LLM."""

    @pytest.mark.asyncio
    async def test_returns_framing_briefs(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.outlet_profile = make_outlet_profile()

        brief_data = make_framing_brief().model_dump()
        mock_router.complete.return_value = make_llm_response(json.dumps(brief_data, default=str))

        result = await agent.execute(ctx)

        assert "framing_briefs" in result
        assert len(result["framing_briefs"]) == 1

    @pytest.mark.asyncio
    async def test_calls_llm_with_framing_task(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.outlet_profile = make_outlet_profile()

        brief_data = make_framing_brief().model_dump()
        mock_router.complete.return_value = make_llm_response(json.dumps(brief_data, default=str))

        await agent.execute(ctx)

        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "framing"

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.outlet_profile = make_outlet_profile()

        brief_data = make_framing_brief().model_dump()
        mock_router.complete.return_value = make_llm_response(json.dumps(brief_data, default=str))

        await agent.execute(ctx)

        assert agent._cost_usd > 0
        assert agent._tokens_in > 0

    @pytest.mark.asyncio
    async def test_multiple_predictions(self, mock_router, make_context):
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [
            make_ranked_prediction(event_thread_id=f"thread_{i:04d}", rank=i + 1) for i in range(3)
        ]
        ctx.outlet_profile = make_outlet_profile()

        # Each call returns a brief for the corresponding prediction
        mock_router.complete.side_effect = [
            make_llm_response(
                json.dumps(
                    make_framing_brief(event_thread_id=f"thread_{i:04d}").model_dump(), default=str
                )
            )
            for i in range(3)
        ]

        result = await agent.execute(ctx)

        assert len(result["framing_briefs"]) == 3
        assert mock_router.complete.call_count == 3

    @pytest.mark.asyncio
    async def test_brief_always_has_prediction_event_thread_id(self, mock_router, make_context):
        """LLM may return wrong event_thread_id — framing must override with prediction's ID."""
        from src.agents.generators.framing import FramingAnalyzer

        agent = FramingAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction(event_thread_id="thread_correct_42")]
        ctx.outlet_profile = make_outlet_profile()

        # LLM returns brief with WRONG event_thread_id
        wrong_brief = make_framing_brief(event_thread_id="thread_WRONG_llm_hallucinated")
        mock_router.complete.return_value = make_llm_response(
            json.dumps(wrong_brief.model_dump(), default=str)
        )

        result = await agent.execute(ctx)

        assert len(result["framing_briefs"]) == 1
        assert result["framing_briefs"][0]["event_thread_id"] == "thread_correct_42"
