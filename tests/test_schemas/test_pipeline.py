"""Tests for src.schemas.pipeline — PipelineContext."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.schemas.agent import AgentResult, StageResult
from src.schemas.pipeline import PipelineContext

# ── PipelineContext creation ─────────────────────────────────────────


def test_pipeline_context_creation():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    assert ctx.outlet == "TASS"
    assert ctx.target_date == date(2026, 4, 1)


def test_pipeline_context_prediction_id_is_uuid_string():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    assert isinstance(ctx.prediction_id, str)
    assert len(ctx.prediction_id) == 36  # UUID4 string


# ── merge_agent_result ───────────────────────────────────────────────


def test_merge_agent_result_news_scout_signals():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    result = AgentResult(
        agent_name="news_scout",
        success=True,
        data={"signals": ["sig1", "sig2"]},
    )
    ctx.merge_agent_result(result)
    assert ctx.signals == ["sig1", "sig2"]


def test_merge_agent_result_delphi_round1_assessment():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    assessment_data = {"persona_id": "realist", "round": 1}
    result = AgentResult(
        agent_name="delphi_realist",
        success=True,
        data={"assessment": assessment_data},
    )
    ctx.merge_agent_result(result)
    assert len(ctx.round1_assessments) == 1
    assert ctx.round1_assessments[0] == assessment_data


def test_merge_agent_result_delphi_round2_revised():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    revised = {"persona_id": "realist", "round": 2}
    result = AgentResult(
        agent_name="delphi_realist",
        success=True,
        data={"revised_assessment": revised},
    )
    ctx.merge_agent_result(result)
    assert len(ctx.round2_assessments) == 1


def test_merge_agent_result_mediator_synthesis():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    synthesis = {"summary": "All agreed"}
    result = AgentResult(
        agent_name="mediator",
        success=True,
        data={"synthesis": synthesis},
    )
    ctx.merge_agent_result(result)
    assert ctx.mediator_synthesis == synthesis


def test_merge_agent_result_quality_gate_empty_list():
    """Empty list from quality_gate must be stored as [], not as the raw dict."""
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    result = AgentResult(
        agent_name="quality_gate",
        success=True,
        data={"final_predictions": []},
    )
    ctx.merge_agent_result(result)
    assert ctx.final_predictions == []
    assert isinstance(ctx.final_predictions, list)


def test_merge_agent_result_skips_failed():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    result = AgentResult(
        agent_name="news_scout",
        success=False,
        error="timeout",
    )
    ctx.merge_agent_result(result)
    assert ctx.signals == []


# ── emit_progress ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_progress_noop_without_callback():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    await ctx.emit_progress("collection", "Collecting...", 0.1)


@pytest.mark.asyncio
async def test_emit_progress_calls_callback():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    mock_cb = AsyncMock()
    ctx.set_progress_callback(mock_cb)
    await ctx.emit_progress("collection", "Collecting...", 0.1)
    mock_cb.assert_awaited_once_with("collection", "Collecting...", 0.1)


# ── Cost and duration aggregation ────────────────────────────────────


def test_get_total_cost_usd():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    ctx.stage_results = [
        StageResult(
            stage_name="collection",
            success=True,
            agent_results=[
                AgentResult(agent_name="a", success=True, cost_usd=0.10),
            ],
        ),
        StageResult(
            stage_name="delphi_r1",
            success=True,
            agent_results=[
                AgentResult(agent_name="b", success=True, cost_usd=0.25),
            ],
        ),
    ]
    assert ctx.get_total_cost_usd() == pytest.approx(0.35)


def test_get_total_duration_ms():
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    ctx.stage_results = [
        StageResult(stage_name="collection", success=True, duration_ms=1000),
        StageResult(stage_name="delphi_r1", success=True, duration_ms=2500),
    ]
    assert ctx.get_total_duration_ms() == 3500
