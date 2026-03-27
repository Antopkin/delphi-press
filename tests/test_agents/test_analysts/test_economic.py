"""Tests for EconomicAnalyst (Stage 3)."""

from __future__ import annotations

import json

import pytest

from .conftest import make_llm_response


class TestEconomicValidation:
    def test_no_threads_returns_error(self, mock_router, make_context):
        from src.agents.analysts.economic import EconomicAnalyst

        agent = EconomicAnalyst(llm_client=mock_router)
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_with_threads_returns_none(self, mock_router, make_context, sample_threads):
        from src.agents.analysts.economic import EconomicAnalyst

        agent = EconomicAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        assert agent.validate_context(ctx) is None


class TestEconomicExecute:
    @pytest.mark.asyncio
    async def test_returns_assessments(
        self, mock_router, make_context, sample_threads, sample_trajectories
    ):
        from src.agents.analysts.economic import EconomicAnalyst

        agent = EconomicAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.trajectories = sample_trajectories

        response_data = {
            "assessments": [
                {
                    "thread_id": t.id,
                    "affected_indicators": [
                        {
                            "name": "S&P 500",
                            "direction": "down",
                            "magnitude": "medium",
                            "confidence": 0.7,
                            "timeframe": "days",
                        }
                    ],
                    "market_impact": "negative",
                    "affected_sectors": ["technology"],
                    "headline_angles": ["Markets tumble"],
                }
                for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        result = await agent.execute(ctx)

        assert "assessments" in result
        assert len(result["assessments"]) == len(sample_threads)
        assert result["assessments"][0]["thread_id"] == sample_threads[0].id

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(
        self, mock_router, make_context, sample_threads, sample_trajectories
    ):
        from src.agents.analysts.economic import EconomicAnalyst

        agent = EconomicAnalyst(llm_client=mock_router)
        ctx = make_context()
        ctx.event_threads = sample_threads
        ctx.trajectories = sample_trajectories

        response_data = {
            "assessments": [
                {"thread_id": t.id, "market_impact": "neutral"} for t in sample_threads
            ]
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(response_data))

        await agent.execute(ctx)
        assert agent._cost_usd > 0
