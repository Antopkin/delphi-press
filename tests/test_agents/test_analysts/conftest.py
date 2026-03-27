"""Shared fixtures for analyst agent tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.schemas.events import (
    EditorialPosition,
    EventThread,
    EventTrajectory,
    HeadlineStyle,
    OutletProfile,
    Scenario,
    SignalRecord,
    SignalSource,
    WritingStyle,
)
from src.schemas.llm import LLMResponse


def make_signal(idx: int = 0, **kwargs: object) -> SignalRecord:
    """Factory for SignalRecord test instances."""
    defaults: dict = {
        "id": f"rss_{idx:04d}",
        "title": f"Test signal {idx}",
        "summary": f"Summary for test signal number {idx}.",
        "url": f"https://example.com/news/{idx}",
        "source_name": ["Reuters", "BBC", "TASS", "Al Jazeera"][idx % 4],
        "source_type": SignalSource.RSS,
        "published_at": datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
        "language": "en",
        "categories": ["politics"],
        "entities": ["EU"],
        "relevance_score": 0.7,
    }
    defaults.update(kwargs)
    return SignalRecord(**defaults)


def make_event_thread(idx: int = 0, **kwargs: object) -> EventThread:
    """Factory for EventThread test instances."""
    defaults: dict = {
        "id": f"thread_{idx:04d}",
        "title": f"Test event thread {idx}",
        "summary": f"Summary describing event thread {idx} in detail.",
        "signal_ids": [f"rss_{idx:04d}"],
        "cluster_size": 5,
        "category": "politics",
        "entities": ["EU", "NATO"],
        "source_diversity": 0.8,
        "earliest_signal": datetime(2026, 3, 26, 10, 0, tzinfo=UTC),
        "latest_signal": datetime(2026, 3, 27, 14, 0, tzinfo=UTC),
        "recency_score": 0.9,
        "significance_score": 0.75,
        "importance": 0.8,
        "entity_prominence": 0.7,
    }
    defaults.update(kwargs)
    return EventThread(**defaults)


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


def make_outlet_profile(**kwargs: object) -> OutletProfile:
    """Factory for OutletProfile test instances."""
    defaults: dict = {
        "outlet_name": "TASS",
        "outlet_url": "https://tass.com",
        "language": "ru",
        "headline_style": HeadlineStyle(avg_length_chars=60, avg_length_words=8),
        "writing_style": WritingStyle(),
        "editorial_position": EditorialPosition(
            tone="neutral",
            focus_topics=["politics", "economy", "military"],
            framing_tendencies=["official", "factual"],
        ),
        "sample_headlines": [
            "Путин провёл встречу с Си Цзиньпином",
            "ЦБ повысил ключевую ставку до 21%",
        ],
    }
    defaults.update(kwargs)
    return OutletProfile(**defaults)


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


@pytest.fixture
def sample_signals() -> list[SignalRecord]:
    """10 sample signals across different topics for clustering tests."""
    signals = []
    topics = [
        ("Trump tariffs on China", "politics", ["Trump", "China"]),
        ("EU tariff response to US", "politics", ["EU", "Trump"]),
        ("China retaliatory tariffs", "economy", ["China", "US"]),
        ("FOMC interest rate decision", "economy", ["Fed", "Powell"]),
        ("Fed signals rate pause", "economy", ["Fed"]),
        ("Russia-Ukraine ceasefire talks", "military", ["Russia", "Ukraine"]),
        ("NATO summit on Ukraine", "military", ["NATO", "Ukraine"]),
        ("Oil prices surge on Middle East", "economy", ["OPEC"]),
        ("Tech layoffs at major firms", "technology", ["Google", "Meta"]),
        ("Climate summit in Berlin", "environment", ["UN", "EU"]),
    ]
    for i, (title, cat, ents) in enumerate(topics):
        signals.append(
            make_signal(
                idx=i,
                title=title,
                categories=[cat],
                entities=ents,
                source_name=["Reuters", "BBC", "TASS", "Al Jazeera", "NYT"][i % 5],
            )
        )
    return signals


@pytest.fixture
def sample_threads() -> list[EventThread]:
    """3 sample event threads for Stage 3 analyst tests."""
    return [
        make_event_thread(0, title="US-China trade war escalation", category="economy"),
        make_event_thread(1, title="Russia-Ukraine ceasefire talks", category="military"),
        make_event_thread(2, title="FOMC rate decision", category="economy"),
    ]


@pytest.fixture
def sample_trajectories(sample_threads) -> list[EventTrajectory]:
    """Trajectories matching sample_threads."""
    return [make_trajectory(t.id) for t in sample_threads]
