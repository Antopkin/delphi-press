"""Tests for src.schemas.timeline — HorizonBand, TimelineEntry, PredictedTimeline."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.schemas.headline import AgreementLevel, ConfidenceLabel
from src.schemas.timeline import (
    HorizonBand,
    PredictedTimeline,
    TimelineEntry,
    compute_horizon_band,
)


def _timeline_entry_kwargs(**overrides) -> dict:
    defaults = {
        "event_thread_id": "thread_001",
        "prediction": "Something will happen",
        "aggregated_probability": 0.72,
        "raw_probability": 0.68,
        "predicted_date": date(2026, 4, 1),
        "uncertainty_days": 1.0,
        "newsworthiness": 0.65,
        "agreement_level": AgreementLevel.CONSENSUS,
        "spread": 0.10,
        "confidence_label": ConfidenceLabel.HIGH,
        "reasoning": "Combined reasoning from 5 personas",
        "evidence_chain": [{"source": "agent", "summary": "fact1"}],
        "persona_count": 5,
    }
    defaults.update(overrides)
    return defaults


# ── HorizonBand ─────────────────────────────────────────────────────


def test_horizon_band_membership():
    assert len(HorizonBand) == 3
    assert HorizonBand.IMMEDIATE == "immediate"
    assert HorizonBand.NEAR == "near"
    assert HorizonBand.MEDIUM == "medium"


def test_compute_horizon_band_immediate():
    assert compute_horizon_band(1) == HorizonBand.IMMEDIATE
    assert compute_horizon_band(2) == HorizonBand.IMMEDIATE


def test_compute_horizon_band_near():
    assert compute_horizon_band(3) == HorizonBand.NEAR
    assert compute_horizon_band(4) == HorizonBand.NEAR


def test_compute_horizon_band_medium():
    assert compute_horizon_band(5) == HorizonBand.MEDIUM
    assert compute_horizon_band(7) == HorizonBand.MEDIUM
    assert compute_horizon_band(14) == HorizonBand.MEDIUM


# ── TimelineEntry ───────────────────────────────────────────────────


def test_timeline_entry_minimal():
    entry = TimelineEntry(**_timeline_entry_kwargs())
    assert entry.event_thread_id == "thread_001"
    assert entry.aggregated_probability == 0.72
    assert entry.predicted_date == date(2026, 4, 1)
    assert entry.persona_count == 5


def test_timeline_entry_defaults():
    entry = TimelineEntry(**_timeline_entry_kwargs())
    assert entry.dissenting_views == []
    assert entry.causal_dependencies == []
    assert entry.temporal_order == 0
    assert entry.scenario_types == []
    assert entry.is_wild_card is False


def test_timeline_entry_with_causal_deps():
    entry = TimelineEntry(
        **_timeline_entry_kwargs(causal_dependencies=["thread_002", "thread_003"])
    )
    assert entry.causal_dependencies == ["thread_002", "thread_003"]


def test_timeline_entry_serialization_roundtrip():
    entry = TimelineEntry(**_timeline_entry_kwargs(temporal_order=3))
    data = entry.model_dump()
    restored = TimelineEntry.model_validate(data)
    assert restored.event_thread_id == entry.event_thread_id
    assert restored.temporal_order == 3
    assert restored.predicted_date == date(2026, 4, 1)


def test_timeline_entry_probability_bounds():
    with pytest.raises(ValidationError):
        TimelineEntry(**_timeline_entry_kwargs(aggregated_probability=1.5))


# ── PredictedTimeline ───────────────────────────────────────────────


def test_predicted_timeline_with_entries():
    entries = [
        TimelineEntry(
            **_timeline_entry_kwargs(event_thread_id=f"thread_{i:03d}", temporal_order=i)
        )
        for i in range(1, 4)
    ]
    tl = PredictedTimeline(
        entries=entries,
        target_date=date(2026, 4, 1),
        horizon_band=HorizonBand.IMMEDIATE,
        horizon_days=1,
        total_events=20,
    )
    assert len(tl.entries) == 3
    assert tl.horizon_band == HorizonBand.IMMEDIATE
    assert tl.horizon_days == 1
    assert tl.total_events == 20
    assert tl.generated_at is not None


def test_predicted_timeline_serialization_roundtrip():
    entry = TimelineEntry(**_timeline_entry_kwargs())
    tl = PredictedTimeline(
        entries=[entry],
        target_date=date(2026, 4, 1),
        horizon_band=HorizonBand.MEDIUM,
        horizon_days=7,
        total_events=15,
    )
    data = tl.model_dump()
    restored = PredictedTimeline.model_validate(data)
    assert len(restored.entries) == 1
    assert restored.entries[0].event_thread_id == "thread_001"
    assert restored.horizon_band == HorizonBand.MEDIUM


def test_predicted_timeline_temporal_order_sorting():
    """Entries can be sorted by predicted_date."""
    e1 = TimelineEntry(
        **_timeline_entry_kwargs(
            event_thread_id="t1",
            predicted_date=date(2026, 4, 3),
            temporal_order=3,
        )
    )
    e2 = TimelineEntry(
        **_timeline_entry_kwargs(
            event_thread_id="t2",
            predicted_date=date(2026, 4, 1),
            temporal_order=1,
        )
    )
    e3 = TimelineEntry(
        **_timeline_entry_kwargs(
            event_thread_id="t3",
            predicted_date=date(2026, 4, 2),
            temporal_order=2,
        )
    )
    sorted_entries = sorted([e1, e2, e3], key=lambda e: e.predicted_date)
    assert [e.event_thread_id for e in sorted_entries] == ["t2", "t3", "t1"]


def test_predicted_timeline_empty_entries():
    tl = PredictedTimeline(
        entries=[],
        target_date=date(2026, 4, 1),
        horizon_band=HorizonBand.NEAR,
        horizon_days=3,
    )
    assert len(tl.entries) == 0
