"""Shared fixtures for forecaster agent tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.schemas.agent import (
    AnonymizedPosition,
    ConsensusArea,
    DisputeArea,
    MediatorSynthesis,
    PersonaAssessment,
    PredictionItem,
    ScenarioType,
)
from src.schemas.events import (
    CrossImpactEntry,
    CrossImpactMatrix,
    EventTrajectory,
    Scenario,
)
from src.schemas.llm import LLMResponse


def make_prediction_item(
    thread_id: str = "thread_0001",
    probability: float = 0.6,
    newsworthiness: float = 0.7,
    **kwargs: object,
) -> PredictionItem:
    """Factory for PredictionItem test instances."""
    defaults: dict = {
        "event_thread_id": thread_id,
        "prediction": "Some specific event will occur with measurable impact.",
        "probability": probability,
        "newsworthiness": newsworthiness,
        "scenario_type": ScenarioType.BASELINE,
        "reasoning": "Base rate reasoning with specific historical precedents and analysis.",
        "key_assumptions": ["Assumption 1", "Assumption 2"],
        "evidence": ["Evidence from input data"],
        "conditional_on": [],
    }
    defaults.update(kwargs)
    return PredictionItem(**defaults)


def make_persona_assessment(
    persona_id: str = "realist",
    round_number: int = 1,
    predictions: list[PredictionItem] | None = None,
    **kwargs: object,
) -> PersonaAssessment:
    """Factory for PersonaAssessment test instances."""
    if predictions is None:
        predictions = [
            make_prediction_item(f"thread_{i:04d}", probability=0.5 + i * 0.05) for i in range(5)
        ]
    defaults: dict = {
        "persona_id": persona_id,
        "round_number": round_number,
        "predictions": predictions,
        "cross_impacts_noted": [],
        "blind_spots": [],
        "confidence_self_assessment": 0.7,
        "revisions_made": [],
        "revision_rationale": "",
    }
    defaults.update(kwargs)
    return PersonaAssessment(**defaults)


def make_mediator_synthesis(**kwargs: object) -> MediatorSynthesis:
    """Factory for MediatorSynthesis test instances."""
    defaults: dict = {
        "consensus_areas": [
            ConsensusArea(
                event_thread_id="thread_0001",
                median_probability=0.65,
                spread=0.08,
                num_agents=5,
            )
        ],
        "disputes": [
            DisputeArea(
                event_thread_id="thread_0002",
                median_probability=0.50,
                spread=0.35,
                positions=[
                    AnonymizedPosition(
                        agent_label="Expert A",
                        probability=0.7,
                        reasoning_summary="Strong evidence of escalation.",
                        key_assumptions=["Escalation likely"],
                    ),
                    AnonymizedPosition(
                        agent_label="Expert B",
                        probability=0.35,
                        reasoning_summary="Historical base rate suggests low probability.",
                        key_assumptions=["Status quo prevails"],
                    ),
                ],
                key_question="Will the deadline trigger actual policy change or just rhetoric?",
            )
        ],
        "gaps": [],
        "cross_impact_flags": [],
        "overall_summary": "Consensus on 1 event, dispute on 1 event.",
        "supplementary_facts": [],
    }
    defaults.update(kwargs)
    return MediatorSynthesis(**defaults)


def make_trajectory(thread_id: str = "thread_0000", **kwargs: object) -> EventTrajectory:
    """Factory for EventTrajectory test instances."""
    defaults: dict = {
        "thread_id": thread_id,
        "current_state": "Situation is developing.",
        "momentum": "escalating",
        "momentum_explanation": "Multiple actors increasing pressure.",
        "scenarios": [
            Scenario(
                scenario_type="baseline",
                description="Continued tensions.",
                probability=0.5,
                key_indicators=["diplomatic meetings"],
                headline_potential="Tensions continue",
            ),
            Scenario(
                scenario_type="optimistic",
                description="De-escalation via talks.",
                probability=0.3,
                key_indicators=["joint statement"],
                headline_potential="Talks succeed",
            ),
            Scenario(
                scenario_type="wildcard",
                description="Unexpected shift.",
                probability=0.2,
                key_indicators=["surprise announcement"],
                headline_potential="Shock move",
            ),
        ],
        "key_drivers": ["US policy", "China response"],
        "uncertainties": ["Election outcome"],
    }
    defaults.update(kwargs)
    return EventTrajectory(**defaults)


def make_cross_impact_matrix() -> CrossImpactMatrix:
    """Factory for CrossImpactMatrix test instances."""
    return CrossImpactMatrix(
        entries=[
            CrossImpactEntry(
                source_thread_id="thread_0000",
                target_thread_id="thread_0001",
                impact_score=0.3,
                explanation="Trade escalation raises market volatility.",
            )
        ],
        generated_at=datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
    )


def make_llm_response(content: str, model: str = "anthropic/claude-sonnet-4") -> LLMResponse:
    """Factory for LLMResponse test instances."""
    return LLMResponse(
        content=content,
        model=model,
        provider="openrouter",
        tokens_in=500,
        tokens_out=300,
        cost_usd=0.005,
        duration_ms=1000,
    )
