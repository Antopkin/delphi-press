"""Tests for src.schemas.agent — AgentResult, StageResult, Delphi schemas."""

import dataclasses

import pytest
from pydantic import ValidationError

from src.schemas.agent import (
    AgentResult,
    ConsensusArea,
    DisputeArea,
    MediatorSynthesis,
    PersonaAssessment,
    PredictionItem,
    ScenarioType,
    StageResult,
)

# ── AgentResult ──────────────────────────────────────────────────────


def test_agent_result_instantiation():
    r = AgentResult(agent_name="scout", success=True, tokens_in=100, cost_usd=0.01)
    assert r.agent_name == "scout"
    assert r.success is True


def test_agent_result_is_frozen():
    r = AgentResult(agent_name="scout", success=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.agent_name = "other"


# ── StageResult ──────────────────────────────────────────────────────


def test_stage_result_total_cost_usd():
    sr = StageResult(
        stage_name="collection",
        success=True,
        agent_results=[
            AgentResult(agent_name="a", success=True, cost_usd=0.10),
            AgentResult(agent_name="b", success=True, cost_usd=0.25),
        ],
    )
    assert sr.total_cost_usd == pytest.approx(0.35)


def test_stage_result_total_tokens_in():
    sr = StageResult(
        stage_name="collection",
        success=True,
        agent_results=[
            AgentResult(agent_name="a", success=True, tokens_in=100),
            AgentResult(agent_name="b", success=True, tokens_in=200),
        ],
    )
    assert sr.total_tokens_in == 300


def test_stage_result_total_tokens_out():
    sr = StageResult(
        stage_name="collection",
        success=True,
        agent_results=[
            AgentResult(agent_name="a", success=True, tokens_out=50),
            AgentResult(agent_name="b", success=True, tokens_out=75),
        ],
    )
    assert sr.total_tokens_out == 125


# ── ScenarioType ─────────────────────────────────────────────────────


def test_scenario_type_membership():
    assert ScenarioType.BASELINE == "baseline"
    assert ScenarioType.BLACK_SWAN == "black_swan"
    assert len(ScenarioType) == 5


# ── PredictionItem ───────────────────────────────────────────────────


def _prediction_item_kwargs(**overrides) -> dict:
    defaults = {
        "event_thread_id": "thread_001",
        "prediction": "Something will happen",
        "probability": 0.7,
        "newsworthiness": 0.5,
        "scenario_type": ScenarioType.BASELINE,
        "reasoning": "Because of X, Y, Z.",
        "key_assumptions": ["A", "B"],
        "evidence": ["fact1"],
    }
    defaults.update(overrides)
    return defaults


def test_prediction_item_instantiation():
    item = PredictionItem(**_prediction_item_kwargs())
    assert item.probability == 0.7


def test_prediction_item_probability_above_1_rejected():
    with pytest.raises(ValidationError):
        PredictionItem(**_prediction_item_kwargs(probability=1.01))


def test_prediction_item_temporal_fields_have_defaults():
    """New temporal fields are Optional with defaults — backward compat."""
    item = PredictionItem(**_prediction_item_kwargs())
    assert item.predicted_date is None
    assert item.uncertainty_days == 1.0
    assert item.causal_dependencies == []
    assert item.confidence_interval_95 is None


def test_prediction_item_with_predicted_date():
    from datetime import date

    item = PredictionItem(
        **_prediction_item_kwargs(
            predicted_date=date(2026, 4, 1),
            uncertainty_days=0.5,
        )
    )
    assert item.predicted_date == date(2026, 4, 1)
    assert item.uncertainty_days == 0.5


def test_prediction_item_with_causal_dependencies():
    item = PredictionItem(
        **_prediction_item_kwargs(causal_dependencies=["thread_002", "thread_003"])
    )
    assert item.causal_dependencies == ["thread_002", "thread_003"]


def test_prediction_item_with_confidence_interval():
    item = PredictionItem(**_prediction_item_kwargs(confidence_interval_95=(0.55, 0.85)))
    assert item.confidence_interval_95 == (0.55, 0.85)


# ── PersonaAssessment ────────────────────────────────────────────────


def _persona_assessment_kwargs(num_predictions: int = 5, **overrides) -> dict:
    predictions = [_prediction_item_kwargs() for _ in range(num_predictions)]
    defaults = {
        "persona_id": "realist",
        "round_number": 1,
        "predictions": predictions,
        "confidence_self_assessment": 0.8,
    }
    defaults.update(overrides)
    return defaults


def test_persona_assessment_min_5_predictions():
    with pytest.raises(ValidationError):
        PersonaAssessment(**_persona_assessment_kwargs(num_predictions=4))


def test_persona_assessment_valid_with_5_predictions():
    pa = PersonaAssessment(**_persona_assessment_kwargs(num_predictions=5))
    assert len(pa.predictions) == 5


# ── ConsensusArea ────────────────────────────────────────────────────


def test_consensus_area_spread_below_015():
    c = ConsensusArea(event_thread_id="t1", median_probability=0.6, spread=0.10, num_agents=5)
    assert c.spread == 0.10


def test_consensus_area_spread_015_rejected():
    with pytest.raises(ValidationError):
        ConsensusArea(event_thread_id="t1", median_probability=0.6, spread=0.15, num_agents=5)


# ── DisputeArea ──────────────────────────────────────────────────────


def test_dispute_area_spread_at_015():
    d = DisputeArea(
        event_thread_id="t1",
        median_probability=0.5,
        spread=0.15,
        positions=[],
    )
    assert d.spread == 0.15


def test_dispute_area_spread_below_015_accepted():
    """Spreads below 0.15 are now accepted — LLMs cannot enforce precise thresholds."""
    d = DisputeArea(
        event_thread_id="t1",
        median_probability=0.5,
        spread=0.14,
        positions=[],
    )
    assert d.spread == 0.14


# ── MediatorSynthesis ────────────────────────────────────────────────


def test_mediator_synthesis_instantiation():
    ms = MediatorSynthesis(
        consensus_areas=[],
        disputes=[],
        gaps=[],
        cross_impact_flags=[],
        overall_summary="Summary text",
    )
    assert ms.overall_summary == "Summary text"
