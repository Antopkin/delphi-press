"""Tests for MediaAnalyst (Stage 3)."""

from __future__ import annotations

import json

import pytest

from .conftest import make_llm_response, make_outlet_profile


class TestMediaValidation:
    def test_no_threads_returns_error(self, mock_router, make_context):
        from src.agents.analysts.media import MediaAnalyst

        agent = MediaAnalyst(llm_client=mock_router)
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_no_outlet_profile_returns_error(self, mock_router, make_context, sample_threads):
        from src.agents.analysts.media import MediaAnalyst

        agent = MediaAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        assert agent.validate_context(ctx) is not None

    def test_with_threads_and_profile_returns_none(
        self, mock_router, make_context, sample_threads
    ):
        from src.agents.analysts.media import MediaAnalyst

        agent = MediaAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.outlet_profile = make_outlet_profile()
        assert agent.validate_context(ctx) is None


class TestMediaExecute:
    @pytest.mark.asyncio
    async def test_returns_assessments(self, mock_router, make_context, sample_threads):
        from src.agents.analysts.media import MediaAnalyst

        agent = MediaAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.outlet_profile = make_outlet_profile()

        response_data = {
            "assessments": [
                {
                    "thread_id": t.id,
                    "newsworthiness": {
                        "timeliness": 0.8,
                        "impact": 0.7,
                        "prominence": 0.9,
                        "proximity": 0.6,
                        "conflict": 0.5,
                        "novelty": 0.3,
                    },
                    "editorial_fit": 0.8,
                    "editorial_fit_explanation": "Matches focus topics.",
                    "news_cycle_position": "developing",
                    "saturation": 0.4,
                    "coverage_probability": 0.85,
                    "predicted_prominence": "major",
                    "likely_framing": "National security angle.",
                    "competing_stories": ["Thread B"],
                    "headline_angles": ["Angle 1", "Angle 2"],
                }
                for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        result = await agent.execute(ctx)

        assert "assessments" in result
        assert len(result["assessments"]) == len(sample_threads)
        assert result["assessments"][0]["thread_id"] == sample_threads[0].id
        assert "newsworthiness" in result["assessments"][0]

    @pytest.mark.asyncio
    async def test_uses_outlet_profile_in_prompt(self, mock_router, make_context, sample_threads):
        from src.agents.analysts.media import MediaAnalyst

        agent = MediaAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.outlet_profile = make_outlet_profile()

        response_data = {
            "assessments": [
                {"thread_id": t.id, "coverage_probability": 0.5} for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        await agent.execute(ctx)

        call_args = mock_router.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        # Check that outlet name appears in prompt
        all_content = " ".join(m.content for m in messages)
        assert "TASS" in all_content
