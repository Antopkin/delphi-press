"""Tests for orchestrator stage_callback — incremental stage result emission."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.agents.orchestrator import Orchestrator
from src.agents.registry import AgentRegistry
from src.schemas.agent import StageResult
from src.schemas.pipeline import PipelineContext
from src.schemas.prediction import PredictionRequest
from tests.test_agents.conftest import make_stub_agent_class

# ── helpers ──────────────────────────────────────────────────────────

ALL_AGENT_NAMES = [
    "news_scout",
    "event_calendar",
    "outlet_historian",
    "event_trend_analyzer",
    "geopolitical_analyst",
    "economic_analyst",
    "media_analyst",
    "delphi_realist",
    "delphi_geostrategist",
    "delphi_economist",
    "delphi_media_expert",
    "delphi_devils_advocate",
    "mediator",
    "judge",
    "framing",
    "style_replicator",
    "quality_gate",
]


def _agent_data(name: str) -> dict:
    mapping = {
        "news_scout": {"signals": [{"id": "sig1"}]},
        "event_calendar": {"scheduled_events": [{"id": "evt1"}]},
        "outlet_historian": {"outlet_profile": {"name": "TASS"}},
        "event_trend_analyzer": {"event_threads": [{"id": "t1"}]},
        "geopolitical_analyst": {"assessments": []},
        "economic_analyst": {"assessments": []},
        "media_analyst": {"assessments": []},
        "judge": {"ranked_predictions": [{"rank": 1}]},
        "framing": {"framing_briefs": [{"rank": 1}]},
        "style_replicator": {"generated_headlines": [{"rank": 1}]},
        "quality_gate": {"final_predictions": []},
        "mediator": {"synthesis": {"summary": "ok"}},
    }
    if name.startswith("delphi_"):
        return {"assessment": {"persona_id": name, "round": 1}}
    return mapping.get(name, {})


@pytest.fixture
def populated_registry(mock_router):
    registry = AgentRegistry(mock_router)
    for name in ALL_AGENT_NAMES:
        cls = make_stub_agent_class(name, data=_agent_data(name))
        registry.register_class(cls)
    return registry


@pytest.fixture
def request_obj():
    return PredictionRequest(outlet="TASS", target_date=date(2026, 4, 1))


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_calls_stage_callback_after_each_stage(populated_registry, request_obj):
    """stage_callback should be called once per stage (9 stages total)."""
    callback = AsyncMock()

    orch = Orchestrator(populated_registry)
    await orch.run_prediction(request_obj, stage_callback=callback)

    assert callback.call_count == 9
    # Each call receives (StageResult, PipelineContext)
    for call_args in callback.call_args_list:
        stage_result, context = call_args[0]
        assert isinstance(stage_result, StageResult)
        assert isinstance(context, PipelineContext)


@pytest.mark.asyncio
async def test_orchestrator_stage_callback_none_is_noop(populated_registry, request_obj):
    """When stage_callback is None, pipeline runs without errors."""
    orch = Orchestrator(populated_registry)
    response = await orch.run_prediction(request_obj, stage_callback=None)
    assert response.status == "completed"


@pytest.mark.asyncio
async def test_orchestrator_stage_callback_receives_stage_names(populated_registry, request_obj):
    """Verify callback receives correct stage names in order."""
    callback = AsyncMock()

    orch = Orchestrator(populated_registry)
    await orch.run_prediction(request_obj, stage_callback=callback)

    stage_names = [call_args[0][0].stage_name for call_args in callback.call_args_list]
    assert "collection" in stage_names
    assert "generation" in stage_names
    assert "quality_gate" in stage_names


@pytest.mark.asyncio
async def test_orchestrator_stage_callback_on_failure(mock_router, request_obj):
    """When a required stage fails, callback is still called for that stage."""
    callback = AsyncMock()

    registry = AgentRegistry(mock_router)
    for name in ALL_AGENT_NAMES:
        if name == "event_trend_analyzer":
            cls = make_stub_agent_class(name, succeed=False)
        else:
            cls = make_stub_agent_class(name, data=_agent_data(name))
        registry.register_class(cls)

    orch = Orchestrator(registry)
    response = await orch.run_prediction(request_obj, stage_callback=callback)

    assert response.status == "failed"
    # Callback should have been called for at least the stages up to and including failure
    assert callback.call_count >= 2  # collection + event_identification (failed)
    # The last callback call should be for the failed stage
    last_stage = callback.call_args_list[-1][0][0]
    assert last_stage.success is False
