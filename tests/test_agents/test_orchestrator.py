"""Tests for src.agents.orchestrator — StageDefinition, Orchestrator."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.agents.orchestrator import Orchestrator, StageDefinition
from src.agents.registry import AgentRegistry
from src.schemas.prediction import PredictionRequest, PredictionResponse
from src.schemas.progress import ProgressStage
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

DELPHI_AGENT_NAMES = [
    "delphi_realist",
    "delphi_geostrategist",
    "delphi_economist",
    "delphi_media_expert",
    "delphi_devils_advocate",
]


def _agent_data(name: str) -> dict:
    """Return appropriate stub data for a given agent name."""
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
    """Registry with stub agents for all 17 pipeline agent names."""
    registry = AgentRegistry(mock_router)
    for name in ALL_AGENT_NAMES:
        cls = make_stub_agent_class(name, data=_agent_data(name))
        registry.register_class(cls)
    return registry


@pytest.fixture
def request_obj():
    return PredictionRequest(outlet="TASS", target_date=date(2026, 4, 1))


# ── StageDefinition ─────────────────────────────────────────────────


def test_stage_definition_defaults():
    sd = StageDefinition(name=ProgressStage.COLLECTION, agent_names=["a"])
    assert sd.parallel is False
    assert sd.required is True
    assert sd.timeout_seconds == 600
    assert sd.min_successful is None


def test_stage_definition_custom_values():
    sd = StageDefinition(
        name=ProgressStage.DELPHI_R1,
        agent_names=["a", "b"],
        parallel=True,
        required=False,
        timeout_seconds=900,
        min_successful=3,
    )
    assert sd.parallel is True
    assert sd.timeout_seconds == 900
    assert sd.min_successful == 3


# ── Orchestrator.STAGES ─────────────────────────────────────────────


def test_stages_count_is_9():
    assert len(Orchestrator.STAGES) == 9


def test_stages_order():
    expected = [
        ProgressStage.COLLECTION,
        ProgressStage.EVENT_IDENTIFICATION,
        ProgressStage.TRAJECTORY,
        ProgressStage.DELPHI_R1,
        ProgressStage.DELPHI_R2,
        ProgressStage.CONSENSUS,
        ProgressStage.FRAMING,
        ProgressStage.GENERATION,
        ProgressStage.QUALITY_GATE,
    ]
    actual = [s.name for s in Orchestrator.STAGES]
    assert actual == expected


def test_collection_stage_is_parallel():
    stage = Orchestrator.STAGES[0]
    assert stage.parallel is True


def test_collection_stage_min_successful_is_2():
    stage = Orchestrator.STAGES[0]
    assert stage.min_successful == 2


def test_collection_stage_has_4_agents():
    stage = Orchestrator.STAGES[0]
    assert len(stage.agent_names) == 4
    assert "foresight_collector" in stage.agent_names


def test_delphi_r1_has_5_agents():
    stage = Orchestrator.STAGES[3]
    assert len(stage.agent_names) == 5


def test_delphi_r1_min_successful_is_3():
    """Delphi R1 requires majority quorum (3 of 5), not 4."""
    stage = Orchestrator.STAGES[3]
    assert stage.min_successful == 3


def test_delphi_r2_timeout_is_2400():
    """R2 timeout 2400s: mediator ~6min + 5 sequential personas ~8min each."""
    stage = Orchestrator.STAGES[4]
    assert stage.timeout_seconds == 2400


# ── _run_parallel() ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_parallel_all_succeed(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    agents = [populated_registry.get_required(n) for n in ["news_scout", "event_calendar"]]
    results = await orch._run_parallel(agents, make_context(), timeout_seconds=30)
    assert len(results) == 2
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_run_parallel_returns_all_results(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    agents = [
        populated_registry.get_required(n)
        for n in ["news_scout", "event_calendar", "outlet_historian"]
    ]
    results = await orch._run_parallel(agents, make_context(), timeout_seconds=30)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_run_parallel_preserves_completed_on_timeout(mock_router, make_context):
    """When stage timeout fires, already-completed agents keep their results.

    Regression test: previously asyncio.timeout() + gather() discarded ALL
    results on timeout, reporting 0 successes even when most agents finished.
    """
    from src.agents.base import BaseAgent

    class FastAgent(BaseAgent):
        name = "fast"

        async def execute(self, context):
            return {"done": True}

    class SlowAgent(BaseAgent):
        name = "slow"

        async def execute(self, context):
            await asyncio.sleep(30)
            return {"done": True}

    fast1 = FastAgent(mock_router)
    fast1.name = "fast_1"
    fast2 = FastAgent(mock_router)
    fast2.name = "fast_2"
    slow = SlowAgent(mock_router)

    orch = Orchestrator(AgentRegistry(mock_router))
    results = await orch._run_parallel([fast1, fast2, slow], make_context(), timeout_seconds=1)

    assert len(results) == 3
    # Fast agents must retain their success=True results
    assert results[0].success is True
    assert results[0].agent_name == "fast_1"
    assert results[1].success is True
    assert results[1].agent_name == "fast_2"
    # Slow agent must be marked as timed out
    assert results[2].success is False
    assert "timeout" in results[2].error.lower()


# ── _run_sequential() ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_sequential_all_succeed(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    agents = [populated_registry.get_required("event_trend_analyzer")]
    ctx = make_context()
    results = await orch._run_sequential(agents, ctx)
    assert len(results) == 1
    assert results[0].success is True


# ── _run_stage() ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_stage_parallel_success(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    stage = StageDefinition(
        name=ProgressStage.COLLECTION,
        agent_names=["news_scout", "event_calendar", "outlet_historian"],
        parallel=True,
        min_successful=2,
    )
    ctx = make_context()
    result = await orch._run_stage(stage, ctx)
    assert result.success is True
    assert len(result.agent_results) == 3


@pytest.mark.asyncio
async def test_run_stage_parallel_min_successful(mock_router, make_context):
    """2 of 3 succeed, min_successful=2 -> stage succeeds."""
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("a1", {"signals": []}))
    registry.register_class(make_stub_agent_class("a2", {"signals": []}))
    registry.register_class(make_stub_agent_class("a3", succeed=False))

    orch = Orchestrator(registry)
    stage = StageDefinition(
        name=ProgressStage.COLLECTION,
        agent_names=["a1", "a2", "a3"],
        parallel=True,
        min_successful=2,
    )
    result = await orch._run_stage(stage, make_context())
    assert result.success is True


@pytest.mark.asyncio
async def test_run_stage_parallel_below_min_fails(mock_router, make_context):
    """1 of 3 succeed, min_successful=2 -> stage fails."""
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("a1", {"signals": []}))
    registry.register_class(make_stub_agent_class("a2", succeed=False))
    registry.register_class(make_stub_agent_class("a3", succeed=False))

    orch = Orchestrator(registry)
    stage = StageDefinition(
        name=ProgressStage.COLLECTION,
        agent_names=["a1", "a2", "a3"],
        parallel=True,
        min_successful=2,
    )
    result = await orch._run_stage(stage, make_context())
    assert result.success is False
    assert "Insufficient" in result.error


@pytest.mark.asyncio
async def test_run_stage_sequential_success(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    stage = StageDefinition(
        name=ProgressStage.CONSENSUS,
        agent_names=["judge"],
    )
    ctx = make_context()
    result = await orch._run_stage(stage, ctx)
    assert result.success is True


@pytest.mark.asyncio
async def test_run_stage_missing_agent_continues(mock_router, make_context):
    """Missing agent is skipped, stage proceeds with available agents."""
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("a1", {"signals": []}))

    orch = Orchestrator(registry)
    stage = StageDefinition(
        name=ProgressStage.COLLECTION,
        agent_names=["a1", "ghost"],
        parallel=True,
        min_successful=1,
    )
    result = await orch._run_stage(stage, make_context())
    assert result.success is True
    assert len(result.agent_results) == 1


@pytest.mark.asyncio
async def test_run_stage_no_agents_fails(mock_router, make_context):
    registry = AgentRegistry(mock_router)
    orch = Orchestrator(registry)
    stage = StageDefinition(
        name=ProgressStage.COLLECTION,
        agent_names=["ghost1", "ghost2"],
    )
    result = await orch._run_stage(stage, make_context())
    assert result.success is False


# ── _run_delphi_r2() ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delphi_r2_mediator_then_parallel(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    stage = Orchestrator.STAGES[4]  # DELPHI_R2
    ctx = make_context()
    result = await orch._run_delphi_r2(stage, ctx, start_ns=0)
    assert result.success is True
    # Mediator + 5 delphi agents = 6 results
    assert len(result.agent_results) == 6


@pytest.mark.asyncio
async def test_delphi_r2_mediator_failure_aborts(mock_router, make_context):
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("mediator", succeed=False))
    for name in DELPHI_AGENT_NAMES:
        registry.register_class(
            make_stub_agent_class(name, {"revised_assessment": {"persona_id": name}})
        )

    orch = Orchestrator(registry)
    stage = Orchestrator.STAGES[4]
    result = await orch._run_delphi_r2(stage, make_context(), start_ns=0)
    assert result.success is False
    assert "mediator" in result.error.lower()


@pytest.mark.asyncio
async def test_delphi_r2_needs_3_of_5_agents(mock_router, make_context):
    """3 of 5 Delphi agents succeed -> R2 succeeds (majority quorum)."""
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("mediator", {"synthesis": {"ok": True}}))
    for i, name in enumerate(DELPHI_AGENT_NAMES):
        succeed = i < 3  # first 3 succeed, last 2 fail
        registry.register_class(
            make_stub_agent_class(
                name,
                {"revised_assessment": {"persona_id": name}} if succeed else None,
                succeed=succeed,
            )
        )

    orch = Orchestrator(registry)
    stage = Orchestrator.STAGES[4]
    result = await orch._run_delphi_r2(stage, make_context(), start_ns=0)
    assert result.success is True


@pytest.mark.asyncio
async def test_delphi_r2_below_3_fails(mock_router, make_context):
    """2 of 5 Delphi agents succeed -> R2 fails (below majority quorum)."""
    registry = AgentRegistry(mock_router)
    registry.register_class(make_stub_agent_class("mediator", {"synthesis": {"ok": True}}))
    for i, name in enumerate(DELPHI_AGENT_NAMES):
        succeed = i < 2  # first 2 succeed, last 3 fail
        registry.register_class(
            make_stub_agent_class(
                name,
                {"revised_assessment": {"persona_id": name}} if succeed else None,
                succeed=succeed,
            )
        )

    orch = Orchestrator(registry)
    stage = Orchestrator.STAGES[4]
    result = await orch._run_delphi_r2(stage, make_context(), start_ns=0)
    assert result.success is False
    assert "Insufficient" in result.error


@pytest.mark.asyncio
async def test_delphi_r2_emits_mid_stage_progress(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    stage = Orchestrator.STAGES[4]
    ctx = make_context()
    cb = AsyncMock()
    ctx.set_progress_callback(cb)
    await orch._run_delphi_r2(stage, ctx, start_ns=0)
    # Callback should have been called at least once during R2
    assert cb.await_count >= 1


# ── run_prediction() ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_prediction_returns_prediction_response(populated_registry, request_obj):
    orch = Orchestrator(populated_registry)
    result = await orch.run_prediction(request_obj)
    assert isinstance(result, PredictionResponse)


@pytest.mark.asyncio
async def test_run_prediction_happy_path_status_completed(populated_registry, request_obj):
    orch = Orchestrator(populated_registry)
    result = await orch.run_prediction(request_obj)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_run_prediction_creates_context_with_correct_fields(populated_registry, request_obj):
    orch = Orchestrator(populated_registry)
    result = await orch.run_prediction(request_obj)
    assert result.outlet == "TASS"
    assert result.target_date == date(2026, 4, 1)


@pytest.mark.asyncio
async def test_run_prediction_emits_progress(request_obj, populated_registry):
    cb = AsyncMock()
    orch = Orchestrator(populated_registry)
    await orch.run_prediction(request_obj, progress_callback=cb)
    assert cb.await_count >= 2  # at least queued + completed


@pytest.mark.asyncio
async def test_run_prediction_critical_failure_returns_failed(mock_router, request_obj):
    """Required stage fails -> status='failed'."""
    registry = AgentRegistry(mock_router)
    # Only register collectors (stage 1), but event_trend_analyzer (stage 2) is missing
    for name in ["news_scout", "event_calendar", "outlet_historian"]:
        registry.register_class(make_stub_agent_class(name, _agent_data(name)))

    orch = Orchestrator(registry)
    result = await orch.run_prediction(request_obj)
    assert result.status == "failed"
    assert result.failed_stage is not None


@pytest.mark.asyncio
async def test_run_prediction_records_duration(populated_registry, request_obj):
    orch = Orchestrator(populated_registry)
    result = await orch.run_prediction(request_obj)
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_run_prediction_records_stage_results(populated_registry, request_obj):
    orch = Orchestrator(populated_registry)
    result = await orch.run_prediction(request_obj)
    assert len(result.stage_results) > 0


# ── _build_response() ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_response_sets_status_completed(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    ctx = make_context()
    resp = orch._build_response(ctx, duration_ms=1000)
    assert resp.status == "completed"


@pytest.mark.asyncio
async def test_build_response_empty_headlines_if_no_finals(populated_registry, make_context):
    orch = Orchestrator(populated_registry)
    ctx = make_context()
    resp = orch._build_response(ctx, duration_ms=1000)
    assert resp.headlines == []


@pytest.mark.asyncio
async def test_build_response_preserves_rank_from_prediction(populated_registry, make_context):
    """_build_response must use rank from FinalPrediction, not enumerate index."""
    orch = Orchestrator(populated_registry)
    ctx = make_context()
    ctx.final_predictions = [
        {
            "rank": 3,
            "headline": "Test headline",
            "first_paragraph": "First paragraph.",
            "confidence": 0.75,
            "confidence_label": "high",
            "category": "politics",
            "reasoning": "Because reasons.",
            "evidence_chain": [],
            "agent_agreement": "consensus",
            "dissenting_views": [],
        }
    ]
    resp = orch._build_response(ctx, duration_ms=500)
    assert len(resp.headlines) == 1
    assert resp.headlines[0].rank == 3  # must be 3, not 1


# ── _build_error_response() ─────────────────────────────────────────


def test_build_error_response_status_failed(populated_registry, make_context):
    from src.schemas.agent import StageResult

    orch = Orchestrator(populated_registry)
    ctx = make_context()
    failed = StageResult(stage_name="collection", success=False, error="All collectors failed")
    resp = orch._build_error_response(ctx, failed)
    assert resp.status == "failed"


def test_build_error_response_includes_error_message(populated_registry, make_context):
    from src.schemas.agent import StageResult

    orch = Orchestrator(populated_registry)
    ctx = make_context()
    failed = StageResult(stage_name="collection", success=False, error="All collectors failed")
    resp = orch._build_error_response(ctx, failed)
    assert "All collectors failed" in resp.error


def test_build_error_response_includes_failed_stage(populated_registry, make_context):
    from src.schemas.agent import StageResult

    orch = Orchestrator(populated_registry)
    ctx = make_context()
    failed = StageResult(stage_name="collection", success=False, error="fail")
    resp = orch._build_error_response(ctx, failed)
    assert resp.failed_stage == "collection"


def test_build_error_response_empty_headlines(populated_registry, make_context):
    from src.schemas.agent import StageResult

    orch = Orchestrator(populated_registry)
    ctx = make_context()
    failed = StageResult(stage_name="collection", success=False, error="fail")
    resp = orch._build_error_response(ctx, failed)
    assert resp.headlines == []


# ── Timeout configuration ──────────────────────────────────────────


def test_event_identification_stage_timeout_600():
    """Stage 2 needs 600s for Opus trajectory_analysis on 20 threads."""
    stage = Orchestrator.STAGES[1]
    assert stage.name == ProgressStage.EVENT_IDENTIFICATION
    assert stage.timeout_seconds >= 600


def test_persona_agent_timeout_600():
    """Persona agents need 600s for complex JSON generation with Opus."""
    from src.agents.forecasters.personas import DelphiPersonaAgent

    # DelphiPersonaAgent requires persona config, check class method directly
    assert DelphiPersonaAgent.get_timeout_seconds(None) >= 600
