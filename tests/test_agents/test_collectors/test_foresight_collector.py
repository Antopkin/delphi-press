"""Tests for ForesightCollector agent."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.collectors.foresight_collector import (
    MAX_FORESIGHT_EVENTS,
    MAX_FORESIGHT_SIGNALS,
    ForesightCollector,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_metaculus() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_polymarket() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_gdelt() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def agent(
    mock_router,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
) -> ForesightCollector:
    return ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
    )


# ── Sample data factories ───────────────────────────────────────────


def make_metaculus_questions(count: int = 3) -> list[dict]:
    """Create sample Metaculus question dicts."""
    return [
        {
            "title": f"Will event {i} happen?",
            "url": f"https://www.metaculus.com/questions/{1000 + i}/",
            "q2": 0.6 + i * 0.05,
            "resolve_time": "2026-06-01T00:00:00Z",
            "categories": ["politics", "world"],
            "nr_forecasters": 100 + i * 10,
        }
        for i in range(count)
    ]


def make_polymarket_markets(count: int = 3) -> list[dict]:
    """Create sample Polymarket market dicts."""
    return [
        {
            "question": f"Market question {i}?",
            "slug": f"market-slug-{i}",
            "yes_probability": 0.55 + i * 0.1,
            "volume": 50000 + i * 10000,
            "categories": ["crypto", "politics"],
        }
        for i in range(count)
    ]


def make_gdelt_articles(count: int = 3) -> list[dict]:
    """Create sample GDELT article dicts."""
    return [
        {
            "title": f"GDELT Article Title {i}",
            "url": f"https://example.com/article-{i}",
            "seendate": f"20260328T12000{i}",
            "domain": f"example{i}.com",
            "language": "English",
        }
        for i in range(count)
    ]


# ── Name & timeout ──────────────────────────────────────────────────


def test_foresight_collector_has_correct_name(agent):
    assert agent.name == "foresight_collector"


def test_foresight_collector_timeout_is_120(agent):
    assert agent.get_timeout_seconds() == 120


# ── Validation ───────────────────────────────────────────────────────


def test_validate_context_missing_outlet(agent, make_context):
    ctx = make_context(outlet="")
    assert agent.validate_context(ctx) is not None


def test_validate_context_valid(agent, make_context):
    ctx = make_context()
    assert agent.validate_context(ctx) is None


# ── Execute: all 3 APIs succeed ─────────────────────────────────────


async def test_foresight_collector_success(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """All 3 APIs return data -- collector combines them."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(2)
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(2)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(3)

    result = await agent.execute(make_context())

    assert "foresight_events" in result
    assert "foresight_signals" in result
    assert "sources_used" in result

    assert len(result["foresight_events"]) == 2
    # polymarket(2) + gdelt(3) = 5
    assert len(result["foresight_signals"]) == 5
    assert set(result["sources_used"]) == {"metaculus", "polymarket", "gdelt"}


# ── Execute: partial failure ────────────────────────────────────────


async def test_foresight_collector_partial_failure(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """One API fails, others succeed -- collector continues."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("Metaculus down")
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(2)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(1)

    result = await agent.execute(make_context())

    assert len(result["foresight_events"]) == 0  # metaculus failed
    assert len(result["foresight_signals"]) == 3  # polymarket(2) + gdelt(1)
    assert "metaculus" not in result["sources_used"]
    assert "polymarket" in result["sources_used"]
    assert "gdelt" in result["sources_used"]


async def test_foresight_collector_polymarket_fails(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket fails, others succeed."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(3)
    mock_polymarket.fetch_enriched_markets.side_effect = ConnectionError("timeout")
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(2)

    result = await agent.execute(make_context())

    assert len(result["foresight_events"]) == 3
    # only gdelt signals (polymarket failed)
    assert len(result["foresight_signals"]) == 2
    assert "polymarket" not in result["sources_used"]
    assert "metaculus" in result["sources_used"]
    assert "gdelt" in result["sources_used"]


# ── Execute: all APIs fail ──────────────────────────────────────────


async def test_foresight_collector_all_fail(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """All APIs fail -- returns empty but success=True (no raise)."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("down")
    mock_polymarket.fetch_enriched_markets.side_effect = RuntimeError("down")
    mock_gdelt.fetch_articles.side_effect = RuntimeError("down")

    result = await agent.execute(make_context())

    assert result["foresight_events"] == []
    assert result["foresight_signals"] == []
    assert result["sources_used"] == []


# ── Run integration: all fail still returns success=True ────────────


async def test_foresight_collector_run_all_fail_still_success(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """run() wrapping: even with empty data, agent returns success=True."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("down")
    mock_polymarket.fetch_enriched_markets.side_effect = RuntimeError("down")
    mock_gdelt.fetch_articles.side_effect = RuntimeError("down")

    agent_result = await agent.run(make_context())

    assert agent_result.success is True
    assert agent_result.data["foresight_events"] == []
    assert agent_result.data["sources_used"] == []


# ── Mapping: Metaculus ──────────────────────────────────────────────


async def test_foresight_collector_maps_metaculus_questions(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify Metaculus question mapping structure."""
    mock_metaculus.fetch_questions.return_value = [
        {
            "title": "Will there be a ceasefire?",
            "url": "https://www.metaculus.com/questions/42/",
            "q2": 0.73,
            "resolve_time": "2026-07-01T00:00:00Z",
            "categories": ["geopolitics"],
            "nr_forecasters": 456,
        }
    ]
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    events = result["foresight_events"]

    assert len(events) == 1
    evt = events[0]
    assert evt["title"] == "Will there be a ceasefire?"
    assert evt["source"] == "metaculus"
    assert evt["source_url"] == "https://www.metaculus.com/questions/42/"
    assert evt["certainty"] == 0.73
    assert evt["resolve_date"] == "2026-07-01T00:00:00Z"
    assert evt["categories"] == ["geopolitics"]
    assert evt["forecasters"] == 456


# ── Mapping: Polymarket ─────────────────────────────────────────────


async def test_foresight_collector_maps_polymarket_markets(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify Polymarket market mapping structure."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "question": "Will BTC exceed 100k?",
            "slug": "btc-100k",
            "yes_probability": 0.42,
            "volume": 250000,
            "categories": ["crypto"],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    assert sig["title"] == "Will BTC exceed 100k?"
    assert sig["source"] == "polymarket"
    assert sig["source_url"] == "https://polymarket.com/market/btc-100k"
    assert sig["probability"] == 0.42
    assert sig["volume_usd"] == 250000
    assert sig["categories"] == ["crypto"]
    assert sig["market_id"] == ""  # no id in input dict


# ── Mapping: Polymarket enrichment ─────────────────────────────────


async def test_foresight_collector_maps_polymarket_with_enrichment(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket markets with price_history get distribution metrics."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "id": "m1",
            "question": "Will BTC exceed 100k?",
            "slug": "btc-100k",
            "yes_probability": 0.65,
            "volume": 500000,
            "liquidity": 80000,
            "categories": ["crypto"],
            "price_history": [
                0.5,
                0.52,
                0.55,
                0.58,
                0.6,
                0.62,
                0.65,
                0.63,
                0.64,
                0.65,
                0.64,
                0.65,
                0.65,
                0.65,
            ],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    assert sig["market_id"] == "m1"
    assert "volatility_7d" in sig
    assert "trend_7d" in sig
    assert "lw_probability" in sig
    assert "liquidity" in sig
    assert sig["liquidity"] == 80000
    assert sig["distribution_reliable"] is True
    assert sig["ci_low"] is not None


async def test_foresight_collector_maps_polymarket_without_price_history(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket markets without price_history get only base fields."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "question": "Simple market?",
            "slug": "simple",
            "yes_probability": 0.5,
            "volume": 10000,
            "categories": [],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]

    assert sig["source"] == "polymarket"
    assert "volatility_7d" not in sig
    assert "distribution_reliable" not in sig


# ── Mapping: GDELT ──────────────────────────────────────────────────


async def test_foresight_collector_maps_gdelt_articles(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify GDELT article mapping structure."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = [
        {
            "title": "Major Summit Begins",
            "url": "https://reuters.com/summit",
            "seendate": "20260328T120000",
            "domain": "reuters.com",
            "language": "English",
        }
    ]

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    assert sig["title"] == "Major Summit Begins"
    assert sig["source"] == "gdelt"
    assert sig["source_url"] == "https://reuters.com/summit"
    assert sig["published_at"] == "20260328T120000"
    assert sig["domain"] == "reuters.com"
    assert sig["language"] == "English"


# ── Capping ──────────────────────────────────────────────────────────


async def test_foresight_events_capped(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Metaculus results are capped at MAX_FORESIGHT_EVENTS."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(50)
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    assert len(result["foresight_events"]) == MAX_FORESIGHT_EVENTS


async def test_foresight_signals_capped(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Combined Polymarket + GDELT signals are capped at MAX_FORESIGHT_SIGNALS."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(60)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(60)

    result = await agent.execute(make_context())
    assert len(result["foresight_signals"]) == MAX_FORESIGHT_SIGNALS


# ── Language resolution ──────────────────────────────────────────────


def test_resolve_gdelt_language_russian_outlet():
    assert ForesightCollector._resolve_gdelt_language("ТАСС") == "russian"


def test_resolve_gdelt_language_english_outlet():
    assert ForesightCollector._resolve_gdelt_language("BBC News") == "english"


def test_resolve_gdelt_language_ria():
    assert ForesightCollector._resolve_gdelt_language("РИА Новости") == "russian"


# ── Query building ───────────────────────────────────────────────────


def test_build_query_contains_outlet_and_date():
    from datetime import date

    query = ForesightCollector._build_query("TASS", date(2026, 4, 1))
    assert "TASS" in query
    assert "2026-04-01" in query


# ── Empty returns from APIs (not failures) ───────────────────────────


async def test_foresight_collector_empty_returns(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """APIs succeed but return empty lists -- sources_used is empty."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())

    assert result["foresight_events"] == []
    assert result["foresight_signals"] == []
    assert result["sources_used"] == []
