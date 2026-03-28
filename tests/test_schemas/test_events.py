"""Tests for src.schemas.events — collector and analyst schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.schemas.events import (
    CrossImpactEntry,
    CrossImpactMatrix,
    EventCertainty,
    EventThread,
    EventTrajectory,
    EventType,
    NewsworthinessScore,
    OutletProfile,
    Scenario,
    ScenarioType,
    ScheduledEvent,
    SignalRecord,
    SignalSource,
    ToneProfile,
)

# ── Enums ────────────────────────────────────────────────────────────


def test_signal_source_values():
    assert SignalSource.RSS == "rss"
    assert SignalSource.WEB_SEARCH == "web_search"
    assert SignalSource.SOCIAL == "social"
    assert SignalSource.WIRE == "wire"


def test_event_type_values():
    assert EventType.POLITICAL == "political"
    assert EventType.ECONOMIC == "economic"
    assert len(EventType) == 9


def test_event_certainty_values():
    assert EventCertainty.CONFIRMED == "confirmed"
    assert EventCertainty.SPECULATIVE == "speculative"


def test_tone_profile_values():
    assert ToneProfile.NEUTRAL == "neutral"
    assert ToneProfile.SENSATIONALIST == "sensationalist"
    assert len(ToneProfile) == 7


# ── SignalRecord ─────────────────────────────────────────────────────


def _signal_kwargs(**overrides) -> dict:
    defaults = {
        "id": "rss_abc123",
        "title": "Breaking news",
        "url": "https://example.com/news",
        "source_name": "Reuters",
        "source_type": SignalSource.RSS,
    }
    defaults.update(overrides)
    return defaults


def test_signal_record_required_fields():
    s = SignalRecord(**_signal_kwargs())
    assert s.id == "rss_abc123"
    assert s.source_type == SignalSource.RSS


def test_signal_record_relevance_score_bounds():
    with pytest.raises(ValidationError):
        SignalRecord(**_signal_kwargs(relevance_score=1.1))


def test_signal_record_relevance_score_valid():
    s = SignalRecord(**_signal_kwargs(relevance_score=0.9))
    assert s.relevance_score == 0.9


# ── ScheduledEvent ───────────────────────────────────────────────────


def _scheduled_event_kwargs(**overrides) -> dict:
    defaults = {
        "id": "evt_001",
        "title": "G20 Summit",
        "event_date": date(2026, 4, 1),
        "event_type": EventType.DIPLOMATIC,
    }
    defaults.update(overrides)
    return defaults


def test_scheduled_event_required_fields():
    e = ScheduledEvent(**_scheduled_event_kwargs())
    assert e.title == "G20 Summit"


def test_scheduled_event_newsworthiness_default():
    e = ScheduledEvent(**_scheduled_event_kwargs())
    assert e.newsworthiness == 0.5


# ── OutletProfile ────────────────────────────────────────────────────


def _outlet_profile_kwargs(**overrides) -> dict:
    from src.schemas.events import EditorialPosition, HeadlineStyle, WritingStyle

    defaults = {
        "outlet_name": "TASS",
        "headline_style": HeadlineStyle(),
        "writing_style": WritingStyle(),
        "editorial_position": EditorialPosition(),
    }
    defaults.update(overrides)
    return defaults


def test_outlet_profile_nested_types():
    op = OutletProfile(**_outlet_profile_kwargs())
    assert op.headline_style.avg_length_chars == 60
    assert op.writing_style.first_paragraph_style == "inverted_pyramid"
    assert op.editorial_position.tone == ToneProfile.NEUTRAL


# ── EventThread ──────────────────────────────────────────────────────


def test_event_thread_defaults():
    et = EventThread(
        id="thread_abc",
        title="Thread title",
        summary="Summary of the thread",
    )
    assert et.cluster_size == 0
    assert et.signal_ids == []
    assert et.source_diversity == 0.0


# ── ScenarioType: unified enum ──────────────────────────────────────


def test_scenario_type_unified_has_five_members():
    assert len(ScenarioType) == 5


def test_scenario_type_unified_values():
    expected = {"baseline", "optimistic", "pessimistic", "black_swan", "wildcard"}
    assert {s.value for s in ScenarioType} == expected


def test_scenario_type_has_black_swan():
    assert ScenarioType.BLACK_SWAN == "black_swan"


def test_scenario_type_importable_from_agent():
    """After unification, import from agent module still works."""
    from src.schemas.agent import ScenarioType as AgentST

    assert AgentST is ScenarioType


# ── EventTrajectory ──────────────────────────────────────────────────


def _scenario_kwargs(**overrides) -> dict:
    defaults = {
        "scenario_type": ScenarioType.BASELINE,
        "description": "Baseline scenario description",
        "probability": 0.5,
    }
    defaults.update(overrides)
    return defaults


def test_event_trajectory_scenarios_min_length_2():
    scenarios = [Scenario(**_scenario_kwargs())]
    with pytest.raises(ValidationError):
        EventTrajectory(
            thread_id="thread_1",
            current_state="Ongoing",
            momentum="stable",
            scenarios=scenarios,
        )


def test_event_trajectory_valid_with_2_scenarios():
    scenarios = [
        Scenario(**_scenario_kwargs(probability=0.6)),
        Scenario(**_scenario_kwargs(scenario_type=ScenarioType.OPTIMISTIC, probability=0.4)),
    ]
    et = EventTrajectory(
        thread_id="thread_1",
        current_state="Ongoing",
        momentum="stable",
        scenarios=scenarios,
    )
    assert len(et.scenarios) == 2


# ── CrossImpactMatrix ───────────────────────────────────────────────


def _matrix_with_entries() -> CrossImpactMatrix:
    entries = [
        CrossImpactEntry(source_thread_id="A", target_thread_id="B", impact_score=0.5),
        CrossImpactEntry(source_thread_id="A", target_thread_id="C", impact_score=-0.3),
        CrossImpactEntry(source_thread_id="B", target_thread_id="C", impact_score=0.2),
    ]
    return CrossImpactMatrix(entries=entries)


def test_cross_impact_matrix_get_impact_found():
    m = _matrix_with_entries()
    assert m.get_impact("A", "B") == 0.5


def test_cross_impact_matrix_get_impact_not_found():
    m = _matrix_with_entries()
    assert m.get_impact("B", "A") == 0.0


def test_cross_impact_matrix_get_influences_on():
    m = _matrix_with_entries()
    influences = m.get_influences_on("C")
    assert len(influences) == 2


def test_cross_impact_matrix_get_influences_from():
    m = _matrix_with_entries()
    influences = m.get_influences_from("A")
    assert len(influences) == 2


# ── NewsworthinessScore ──────────────────────────────────────────────


def test_newsworthiness_composite_score_formula():
    ns = NewsworthinessScore(
        timeliness=1.0,
        impact=1.0,
        prominence=1.0,
        proximity=1.0,
        conflict=1.0,
        novelty=1.0,
    )
    # 0.25*1 + 0.20*1 + 0.20*1 + 0.15*1 + 0.10*1 + 0.10*1 = 1.0
    assert ns.composite_score == pytest.approx(1.0)


def test_newsworthiness_composite_score_weighted():
    ns = NewsworthinessScore(
        timeliness=0.5,
        impact=0.8,
        prominence=0.3,
        proximity=0.2,
        conflict=0.6,
        novelty=0.4,
    )
    expected = 0.25 * 0.8 + 0.20 * 0.5 + 0.20 * 0.3 + 0.15 * 0.6 + 0.10 * 0.2 + 0.10 * 0.4
    assert ns.composite_score == pytest.approx(expected)
