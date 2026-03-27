"""Tests for GeopoliticalAnalyst (Stage 3)."""

from __future__ import annotations

import json

import pytest

from .conftest import make_llm_response


class TestGeopoliticalValidation:
    """Test validate_context."""

    def test_no_threads_returns_error(self, mock_router, make_context):
        from src.agents.analysts.geopolitical import GeopoliticalAnalyst

        agent = GeopoliticalAnalyst(llm_client=mock_router)
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_with_threads_returns_none(self, mock_router, make_context, sample_threads):
        from src.agents.analysts.geopolitical import GeopoliticalAnalyst

        agent = GeopoliticalAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        assert agent.validate_context(ctx) is None


class TestGeopoliticalExecute:
    """Test execute with mock LLM."""

    @pytest.mark.asyncio
    async def test_returns_assessments(
        self, mock_router, make_context, sample_threads, sample_trajectories
    ):
        from src.agents.analysts.geopolitical import GeopoliticalAnalyst

        agent = GeopoliticalAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.trajectories = sample_trajectories

        response_data = {
            "assessments": [
                {
                    "thread_id": t.id,
                    "strategic_actors": [
                        {
                            "name": "US",
                            "role": "initiator",
                            "interests": ["trade dominance"],
                            "likely_actions": ["tariff increase"],
                            "leverage": "economic",
                        }
                    ],
                    "power_dynamics": "US strengthening position.",
                    "alliance_shifts": ["EU closer to US"],
                    "escalation_probability": 0.4,
                    "second_order_effects": ["Supply chain disruption"],
                    "sanctions_risk": "medium",
                    "military_implications": "",
                    "headline_angles": ["Trade war escalates"],
                }
                for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        result = await agent.execute(ctx)

        assert "assessments" in result
        assert len(result["assessments"]) == len(sample_threads)
        assert result["assessments"][0]["thread_id"] == sample_threads[0].id
        mock_router.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(
        self, mock_router, make_context, sample_threads, sample_trajectories
    ):
        from src.agents.analysts.geopolitical import GeopoliticalAnalyst

        agent = GeopoliticalAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.trajectories = sample_trajectories

        response_data = {
            "assessments": [
                {"thread_id": t.id, "escalation_probability": 0.1} for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        await agent.execute(ctx)

        assert agent._cost_usd > 0
        assert agent._tokens_in > 0
