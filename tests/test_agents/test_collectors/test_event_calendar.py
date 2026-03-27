"""Tests for EventCalendar collector agent."""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.agents.collectors.event_calendar import EventCalendar
from src.schemas.events import EventType, ScheduledEvent
from tests.test_agents.test_collectors.conftest import make_llm_response, make_search_result


@pytest.fixture
def agent(mock_router, mock_web_search):
    return EventCalendar(mock_router, web_search=mock_web_search)


# ── Name & validation ─────────────────────────────────────────────────


def test_event_calendar_has_correct_name(agent):
    assert agent.name == "event_calendar"


def test_validate_context_valid(agent, make_context):
    assert agent.validate_context(make_context()) is None


# ── Query generation ──────────────────────────────────────────────────


def test_build_event_queries_covers_domains():
    queries = EventCalendar._build_event_queries(date(2026, 4, 1))
    assert len(queries) >= 5
    topics = " ".join(queries).lower()
    assert "political" in topics
    assert "economic" in topics
    assert "diplomatic" in topics


# ── Execute happy path ────────────────────────────────────────────────


async def test_execute_returns_scheduled_events_key(
    agent, make_context, mock_web_search, mock_router
):
    mock_web_search.search.return_value = [
        make_search_result(title="UN Summit", snippet="UN meets on April 1"),
    ]

    extract_json = json.dumps(
        {
            "events": [
                {
                    "title": "UN General Assembly Session",
                    "description": "Annual session",
                    "event_date": "2026-04-01",
                    "event_type": "diplomatic",
                    "certainty": "confirmed",
                    "location": "New York",
                    "participants": ["UN"],
                    "source_url": "https://un.org",
                }
            ]
        }
    )
    assess_json = json.dumps(
        {
            "assessments": [
                {
                    "title": "UN General Assembly Session",
                    "newsworthiness": 0.8,
                    "potential_impact": "Major diplomatic event",
                }
            ]
        }
    )
    mock_router.complete.side_effect = [
        make_llm_response(extract_json),
        make_llm_response(assess_json, model="anthropic/claude-sonnet-4"),
    ]

    result = await agent.execute(make_context())
    assert "scheduled_events" in result
    assert len(result["scheduled_events"]) == 1
    assert result["scheduled_events"][0]["title"] == "UN General Assembly Session"
    assert result["scheduled_events"][0]["newsworthiness"] == 0.8


async def test_search_events_gathers_parallel(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = []
    mock_router.complete.return_value = make_llm_response(json.dumps({"events": []}))

    await agent.execute(make_context())
    assert mock_web_search.search.call_count >= 5


# ── LLM calls ─────────────────────────────────────────────────────────


async def test_extract_events_calls_llm(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = [make_search_result()]
    mock_router.complete.return_value = make_llm_response(json.dumps({"events": []}))

    await agent.execute(make_context())
    call_args = mock_router.complete.call_args_list[0]
    assert call_args.kwargs["task"] == "event_calendar"


async def test_assess_events_calls_llm(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = [make_search_result()]

    extract_json = json.dumps(
        {
            "events": [
                {
                    "title": "Test Event",
                    "event_date": "2026-04-01",
                    "event_type": "political",
                    "certainty": "likely",
                }
            ]
        }
    )
    assess_json = json.dumps(
        {"assessments": [{"title": "Test Event", "newsworthiness": 0.7, "potential_impact": ""}]}
    )
    mock_router.complete.side_effect = [
        make_llm_response(extract_json),
        make_llm_response(assess_json),
    ]

    await agent.execute(make_context())
    assert mock_router.complete.call_count == 2
    call_args = mock_router.complete.call_args_list[1]
    assert call_args.kwargs["task"] == "event_assessment"


async def test_tracks_llm_usage_for_both_calls(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = [make_search_result()]

    extract_json = json.dumps(
        {
            "events": [
                {
                    "title": "Event",
                    "event_date": "2026-04-01",
                    "event_type": "economic",
                    "certainty": "likely",
                }
            ]
        }
    )
    assess_json = json.dumps(
        {"assessments": [{"title": "Event", "newsworthiness": 0.5, "potential_impact": ""}]}
    )
    mock_router.complete.side_effect = [
        make_llm_response(extract_json),
        make_llm_response(assess_json),
    ]

    await agent.execute(make_context())
    assert agent._tokens_in == 200  # 100 + 100 from two calls
    assert agent._cost_usd == pytest.approx(0.002)


# ── Deduplication ─────────────────────────────────────────────────────


def test_deduplicate_events_by_levenshtein():
    events = [
        ScheduledEvent(
            id="evt_1",
            title="UN General Assembly Session",
            event_date=date(2026, 4, 1),
            event_type=EventType.DIPLOMATIC,
        ),
        ScheduledEvent(
            id="evt_2",
            title="UN General Assembly Session 2026",
            event_date=date(2026, 4, 1),
            event_type=EventType.DIPLOMATIC,
        ),
    ]
    result = EventCalendar._deduplicate_events(events)
    assert len(result) == 1


def test_deduplicate_keeps_different_events():
    events = [
        ScheduledEvent(
            id="evt_1",
            title="UN General Assembly",
            event_date=date(2026, 4, 1),
            event_type=EventType.DIPLOMATIC,
        ),
        ScheduledEvent(
            id="evt_2",
            title="Fed Interest Rate Decision",
            event_date=date(2026, 4, 1),
            event_type=EventType.ECONOMIC,
        ),
    ]
    result = EventCalendar._deduplicate_events(events)
    assert len(result) == 2


# ── Limits ────────────────────────────────────────────────────────────


async def test_caps_at_30_events(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = [make_search_result()]

    event_types = list(EventType)
    titles = [f"AAAAAA{i:04d}" for i in range(40)]
    events_list = [
        {
            "title": titles[i],
            "event_date": "2026-04-01",
            "event_type": event_types[i % len(event_types)].value,
            "certainty": "likely",
        }
        for i in range(40)
    ]
    extract_json = json.dumps({"events": events_list})
    assessments = [
        {"title": titles[i], "newsworthiness": 0.5, "potential_impact": ""} for i in range(40)
    ]
    assess_json = json.dumps({"assessments": assessments})

    mock_router.complete.side_effect = [
        make_llm_response(extract_json),
        make_llm_response(assess_json),
    ]

    result = await agent.execute(make_context())
    assert len(result["scheduled_events"]) == 30


# ── Empty results ─────────────────────────────────────────────────────


async def test_no_search_results_returns_empty(agent, make_context, mock_web_search, mock_router):
    mock_web_search.search.return_value = []

    result = await agent.execute(make_context())
    assert result["scheduled_events"] == []
    mock_router.complete.assert_not_called()
