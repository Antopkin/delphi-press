"""Tests for StyleReplicator agent (Stage 8)."""

from __future__ import annotations

import json

import pytest

from .conftest import (
    make_framing_brief,
    make_generated_headline,
    make_llm_response,
    make_outlet_profile,
    make_ranked_prediction,
)


class TestStyleReplicatorValidation:
    """Test validate_context."""

    def test_no_predictions_returns_error(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_no_framing_briefs_returns_error(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        assert agent.validate_context(ctx) is not None

    def test_no_outlet_profile_returns_error(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        assert agent.validate_context(ctx) is not None

    def test_valid_context(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()
        assert agent.validate_context(ctx) is None


class TestStyleReplicatorExecute:
    """Test execute() with mock LLM."""

    def _mock_headline_set(self, event_thread_id: str = "thread_0001") -> str:
        """Build JSON for a GeneratedHeadlineSet response."""
        headlines = [
            make_generated_headline(
                event_thread_id=event_thread_id, variant_number=i + 1
            ).model_dump()
            for i in range(3)
        ]
        return json.dumps({"headlines": headlines}, default=str)

    @pytest.mark.asyncio
    async def test_returns_generated_headlines(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        mock_router.complete.return_value = make_llm_response(self._mock_headline_set())

        result = await agent.execute(ctx)

        assert "generated_headlines" in result
        assert len(result["generated_headlines"]) == 3

    @pytest.mark.asyncio
    async def test_calls_llm_with_style_task(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        mock_router.complete.return_value = make_llm_response(self._mock_headline_set())

        await agent.execute(ctx)

        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"].startswith("style_generation")

    @pytest.mark.asyncio
    async def test_russian_outlet_uses_ru_task(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile(language="ru")

        mock_router.complete.return_value = make_llm_response(self._mock_headline_set())

        await agent.execute(ctx)

        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "style_generation_ru"

    @pytest.mark.asyncio
    async def test_english_outlet_uses_default_task(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief(outlet_name="BBC")]
        ctx.outlet_profile = make_outlet_profile(language="en", outlet_name="BBC")

        mock_router.complete.return_value = make_llm_response(self._mock_headline_set())

        await agent.execute(ctx)

        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "style_generation"

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        ctx.outlet_profile = make_outlet_profile()

        mock_router.complete.return_value = make_llm_response(self._mock_headline_set())

        await agent.execute(ctx)

        assert agent._cost_usd > 0
        assert agent._tokens_in > 0

    @pytest.mark.asyncio
    async def test_length_deviation_computed(self, mock_router, make_context):
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        ctx = make_context()
        ctx.ranked_predictions = [make_ranked_prediction()]
        ctx.framing_briefs = [make_framing_brief()]
        # Profile expects avg 60 chars
        ctx.outlet_profile = make_outlet_profile()

        # Headline with 10 chars — way too short
        short_headline = make_generated_headline(headline="Short one!").model_dump()
        response_data = json.dumps({"headlines": [short_headline]}, default=str)
        mock_router.complete.return_value = make_llm_response(response_data)

        result = await agent.execute(ctx)

        headlines = result["generated_headlines"]
        assert len(headlines) >= 1
        # length_deviation should be negative (too short)
        assert headlines[0]["length_deviation"] < 0

    @pytest.mark.asyncio
    async def test_generate_one_parse_error_returns_empty(self, mock_router, make_context):
        """_generate_one must catch PromptParseError and return [] without raising."""
        from src.agents.generators.style_replicator import StyleReplicator

        agent = StyleReplicator(llm_client=mock_router)
        prediction = make_ranked_prediction()
        brief = make_framing_brief()
        profile = make_outlet_profile()

        mock_router.complete.return_value = make_llm_response("INVALID JSON — not parseable")

        # _generate_one should return [] on parse failure, not raise
        result = await agent._generate_one(prediction, brief, profile)
        assert result == []
