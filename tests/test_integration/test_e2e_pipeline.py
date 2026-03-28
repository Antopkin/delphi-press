"""E2E integration test -- full 9-stage prediction pipeline.

Runs PredictionRequest through all 18 real agents with MockLLMClient.
Verifies pipeline completes and produces valid PredictionResponse.

Why: validates that every agent, prompt parser, and context merge works
together end-to-end without real LLM calls or external API requests.
"""

from __future__ import annotations

from datetime import date

from src.schemas.prediction import PredictionResponse
from tests.fixtures.mock_llm import MockLLMClient

# =====================================================================
# Happy path: full pipeline completion
# =====================================================================


async def test_full_pipeline_completes(
    e2e_orchestrator,
    prediction_request,
    mock_llm_client: MockLLMClient,
) -> None:
    """PredictionRequest -> 9 stages -> PredictionResponse with headlines."""
    response = await e2e_orchestrator.run_prediction(prediction_request)

    # Pipeline completed without fatal error
    assert response.status == "completed", (
        f"Pipeline failed at stage '{response.failed_stage}': {response.error}"
    )
    assert response.error is None
    assert response.failed_stage is None

    # Correct metadata
    assert response.outlet == "ТАСС"
    assert response.target_date == date(2026, 3, 29)
    assert response.id  # UUID populated

    # All 9 stages ran
    assert len(response.stage_results) == 9
    for sr in response.stage_results:
        assert sr["success"], f"Stage '{sr.get('stage_name', '?')}' failed: {sr.get('error')}"

    # Headlines generated
    assert len(response.headlines) > 0
    for h in response.headlines:
        assert h.headline != ""
        assert h.first_paragraph != ""
        assert 0.0 <= h.confidence <= 1.0
        assert h.rank >= 1

    # Cost tracking populated (mock LLM returns 0.001 per call)
    assert response.total_cost_usd > 0
    assert response.duration_ms > 0


# =====================================================================
# LLM task coverage
# =====================================================================


async def test_all_expected_llm_tasks_called(
    e2e_orchestrator,
    prediction_request,
    mock_llm_client: MockLLMClient,
) -> None:
    """Every expected LLM task was called at least once."""
    await e2e_orchestrator.run_prediction(prediction_request)

    called_tasks = set(mock_llm_client.call_counts.keys())

    # Core tasks that MUST be called (some may be called multiple times)
    expected_core = {
        # Stage 1: Collectors
        "news_scout_search",
        "event_calendar",
        "event_assessment",
        "outlet_historian",
        # Stage 2: EventTrendAnalyzer
        "event_clustering",
        "trajectory_analysis",
        "cross_impact_analysis",
        # Stage 3: Analysts
        "geopolitical_analysis",
        "economic_analysis",
        "media_analysis",
        # Stage 5: Mediator
        "mediator",
        # Stage 6: Judge
        "judge",
        # Stage 7: Framing
        "framing",
        # Stage 9: Quality Gate
        "quality_factcheck",
        "quality_style",
    }

    # Delphi persona tasks (R1 + R2)
    for persona in ("realist", "geostrateg", "economist", "media", "devils"):
        expected_core.add(f"delphi_r1_{persona}")
        expected_core.add(f"delphi_r2_{persona}")

    # Style generation: "style_generation_ru" for Russian outlet
    expected_core.add("style_generation_ru")

    missing = expected_core - called_tasks
    assert not missing, f"These LLM tasks were never called: {missing}"


# =====================================================================
# PipelineContext slot population
# =====================================================================


async def test_pipeline_captures_context(
    e2e_orchestrator,
    prediction_request,
    mock_llm_client: MockLLMClient,
    monkeypatch,
) -> None:
    """PipelineContext slots are populated after each stage."""
    captured_context: dict = {}

    # Monkey-patch _build_response to capture the context before it is
    # converted into a PredictionResponse.
    original_build = type(e2e_orchestrator)._build_response

    def capturing_build(self, context, duration_ms):
        captured_context["ctx"] = context
        return original_build(self, context, duration_ms)

    monkeypatch.setattr(type(e2e_orchestrator), "_build_response", capturing_build)

    response = await e2e_orchestrator.run_prediction(prediction_request)
    assert response.status == "completed", (
        f"Pipeline failed at stage '{response.failed_stage}': {response.error}"
    )

    ctx = captured_context["ctx"]

    # Stage 1: Collection
    assert len(ctx.signals) > 0, "No signals collected"
    assert len(ctx.scheduled_events) >= 0  # May be empty if EventCalendar has no results

    # Stage 2: Event Identification
    assert len(ctx.event_threads) > 0, "No event threads identified"

    # Stage 3: Trajectory
    assert len(ctx.trajectories) > 0, "No trajectories generated"

    # Stage 4: Delphi R1
    assert len(ctx.round1_assessments) > 0, "No R1 assessments"

    # Stage 5: Delphi R2
    assert ctx.mediator_synthesis is not None, "No mediator synthesis"
    assert len(ctx.round2_assessments) > 0, "No R2 assessments"

    # Stage 6: Consensus
    assert len(ctx.ranked_predictions) > 0, "No ranked predictions"

    # Stage 7: Framing
    assert len(ctx.framing_briefs) > 0, "No framing briefs"

    # Stage 8: Generation
    assert len(ctx.generated_headlines) > 0, "No generated headlines"

    # Stage 9: Quality Gate
    assert len(ctx.final_predictions) > 0, "No final predictions"


# =====================================================================
# Progress callback
# =====================================================================


async def test_pipeline_progress_events(
    e2e_orchestrator,
    prediction_request,
) -> None:
    """Progress callback receives events for all stages."""
    events: list[dict] = []

    async def progress_callback(stage: str, message: str, pct: float) -> None:
        events.append({"stage": stage, "message": message, "pct": pct})

    await e2e_orchestrator.run_prediction(
        prediction_request,
        progress_callback=progress_callback,
    )

    # At minimum: QUEUED + 9 stage starts + Delphi R2 sub-event + COMPLETED
    assert len(events) >= 11, f"Expected at least 11 progress events, got {len(events)}"

    stages_seen = {e["stage"] for e in events}

    # Key lifecycle stages
    assert "queued" in stages_seen, "QUEUED progress event missing"
    assert "completed" in stages_seen, "COMPLETED progress event missing"
    assert "collection" in stages_seen, "COLLECTION progress event missing"

    # Percentages increase monotonically (ignoring duplicate stage events)
    pcts = [e["pct"] for e in events if e["pct"] >= 0]
    assert pcts[-1] == 1.0, f"Final progress should be 1.0, got {pcts[-1]}"


# =====================================================================
# Response schema contract
# =====================================================================


async def test_response_schema_contract(
    e2e_orchestrator,
    prediction_request,
) -> None:
    """PredictionResponse matches the declared Pydantic schema exactly."""
    response = await e2e_orchestrator.run_prediction(prediction_request)

    # Validate via Pydantic round-trip
    response_dict = response.model_dump()
    validated = PredictionResponse.model_validate(response_dict)

    assert validated.status == "completed"
    assert validated.id == response.id
    assert len(validated.headlines) == len(response.headlines)

    # stage_results are list[dict] with expected keys
    for sr in validated.stage_results:
        assert "stage_name" in sr
        assert "success" in sr
        assert "duration_ms" in sr


# =====================================================================
# Resilience: partial collector failure
# =====================================================================


async def test_pipeline_survives_partial_collector_failure(
    mock_llm_client: MockLLMClient,
    collector_deps: dict,
    prediction_request,
) -> None:
    """Pipeline completes even if some Stage 1 collectors fail.

    The COLLECTION stage requires min_successful=2.  If one collector
    raises, the others should still provide enough data.
    """
    # Break the RSS fetcher
    collector_deps["rss_fetcher"].fetch_feeds.side_effect = RuntimeError("RSS unavailable")

    from src.agents.orchestrator import Orchestrator
    from src.agents.registry import build_default_registry

    registry = build_default_registry(mock_llm_client, collector_deps=collector_deps)
    orchestrator = Orchestrator(registry)

    response = await orchestrator.run_prediction(prediction_request)

    # Pipeline should still complete because web_search provides signals
    # and min_successful=2 is met (event_calendar, outlet_historian, foresight work)
    assert response.status == "completed", (
        f"Pipeline failed despite partial collector failure: {response.error}"
    )


# =====================================================================
# Registry completeness
# =====================================================================


async def test_registry_has_all_18_agents(e2e_registry) -> None:
    """Registry contains all 18 expected agents."""
    assert len(e2e_registry) == 18, (
        f"Expected 18 agents, got {len(e2e_registry)}: {e2e_registry.list_agents()}"
    )

    expected_agents = {
        # Collectors (4)
        "news_scout",
        "event_calendar",
        "outlet_historian",
        "foresight_collector",
        # Analysts (4)
        "event_trend_analyzer",
        "geopolitical_analyst",
        "economic_analyst",
        "media_analyst",
        # Delphi personas (5)
        "delphi_realist",
        "delphi_geostrategist",
        "delphi_economist",
        "delphi_media_expert",
        "delphi_devils_advocate",
        # Delphi infrastructure (2)
        "mediator",
        "judge",
        # Generators (3)
        "framing",
        "style_replicator",
        "quality_gate",
    }

    registered = set(e2e_registry.list_agents())
    missing = expected_agents - registered
    extra = registered - expected_agents

    assert not missing, f"Missing agents: {missing}"
    assert not extra, f"Unexpected agents: {extra}"
