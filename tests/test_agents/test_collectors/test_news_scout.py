"""Tests for NewsScout collector agent."""

from __future__ import annotations

import json

import pytest

from src.agents.collectors.news_scout import GLOBAL_RSS_FEEDS, NewsScout
from src.schemas.events import SignalSource
from tests.test_agents.test_collectors.conftest import (
    make_llm_response,
    make_rss_item,
    make_search_result,
)


@pytest.fixture
def agent(mock_router, mock_rss_fetcher, mock_web_search, mock_catalog):
    return NewsScout(
        mock_router,
        rss_fetcher=mock_rss_fetcher,
        web_search=mock_web_search,
        outlet_catalog=mock_catalog,
    )


# ── Name & timeout ────────────────────────────────────────────────────


def test_news_scout_has_correct_name(agent):
    assert agent.name == "news_scout"


def test_news_scout_timeout_is_600(agent):
    assert agent.get_timeout_seconds() == 600


# ── Validation ────────────────────────────────────────────────────────


def test_validate_context_missing_outlet(agent, make_context):
    ctx = make_context(outlet="")
    assert agent.validate_context(ctx) is not None


def test_validate_context_valid(agent, make_context):
    ctx = make_context()
    assert agent.validate_context(ctx) is None


# ── Execute happy path ────────────────────────────────────────────────


async def test_execute_returns_signals_key(agent, make_context, mock_rss_fetcher, mock_web_search):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(title="RSS News", url="https://rss.com/1"),
    ]
    mock_web_search.search.return_value = [
        make_search_result(title="Web News", url="https://web.com/1"),
    ]

    result = await agent.execute(make_context())
    assert "signals" in result
    assert isinstance(result["signals"], list)
    assert len(result["signals"]) == 2


async def test_execute_collects_from_rss_and_search(
    agent, make_context, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(url="https://rss.com/a"),
    ]
    mock_web_search.search.return_value = [
        make_search_result(url="https://web.com/b"),
    ]

    await agent.execute(make_context())
    mock_rss_fetcher.fetch_feeds.assert_called_once()
    assert mock_web_search.search.call_count >= 1


# ── Deduplication ─────────────────────────────────────────────────────


async def test_execute_deduplicates_by_url(agent, make_context, mock_rss_fetcher, mock_web_search):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(title="Same story", url="https://example.com/dup"),
    ]
    mock_web_search.search.return_value = [
        make_search_result(title="Same story again", url="https://example.com/dup"),
    ]

    result = await agent.execute(make_context())
    assert len(result["signals"]) == 1


# ── Graceful degradation ─────────────────────────────────────────────


async def test_execute_rss_fails_uses_search_only(
    agent, make_context, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.side_effect = RuntimeError("RSS down")
    mock_web_search.search.return_value = [
        make_search_result(url="https://web.com/1"),
    ]

    result = await agent.execute(make_context())
    assert len(result["signals"]) >= 1


async def test_execute_search_fails_uses_rss_only(
    agent, make_context, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(url="https://rss.com/1"),
    ]
    mock_web_search.search.side_effect = RuntimeError("Search down")

    result = await agent.execute(make_context())
    assert len(result["signals"]) >= 1


async def test_execute_both_fail_raises(agent, make_context, mock_rss_fetcher, mock_web_search):
    mock_rss_fetcher.fetch_feeds.side_effect = RuntimeError("RSS down")
    mock_web_search.search.side_effect = RuntimeError("Search down")

    with pytest.raises(RuntimeError, match="Both RSS and web search"):
        await agent.execute(make_context())


# ── Classification ────────────────────────────────────────────────────


async def test_classify_signals_skips_already_classified(
    agent, make_context, mock_router, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(
            url="https://rss.com/1",
            categories=["politics"],
        ),
    ]
    mock_web_search.search.return_value = []

    await agent.execute(make_context())
    mock_router.complete.assert_not_called()


async def test_classify_signals_calls_llm_for_unclassified(
    agent, make_context, mock_router, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(url="https://rss.com/1"),
    ]
    mock_web_search.search.return_value = []

    classify_response = make_llm_response(
        json.dumps({"items": [{"index": 0, "categories": ["politics"], "entities": ["EU"]}]})
    )
    mock_router.complete.return_value = classify_response

    result = await agent.execute(make_context())
    mock_router.complete.assert_called_once()
    signal = result["signals"][0]
    assert signal["categories"] == ["politics"]
    assert signal["entities"] == ["EU"]


async def test_classify_signals_tracks_llm_usage(
    agent, make_context, mock_router, mock_rss_fetcher, mock_web_search
):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(url="https://rss.com/1"),
    ]
    mock_web_search.search.return_value = []

    classify_response = make_llm_response(
        json.dumps({"items": [{"index": 0, "categories": ["tech"], "entities": []}]})
    )
    mock_router.complete.return_value = classify_response

    await agent.execute(make_context())
    assert agent._tokens_in > 0
    assert agent._cost_usd > 0


# ── Limits ────────────────────────────────────────────────────────────


async def test_execute_caps_at_200_signals(agent, make_context, mock_rss_fetcher, mock_web_search):
    mock_rss_fetcher.fetch_feeds.return_value = [
        make_rss_item(url=f"https://rss.com/{i}", categories=["news"]) for i in range(250)
    ]
    mock_web_search.search.return_value = []

    result = await agent.execute(make_context())
    assert len(result["signals"]) == 200


# ── Helpers ───────────────────────────────────────────────────────────


def test_make_signal_id_deterministic():
    id1 = NewsScout._make_signal_id("rss", "https://x.com/1", "Title")
    id2 = NewsScout._make_signal_id("rss", "https://x.com/1", "Title")
    assert id1 == id2
    assert id1.startswith("rss_")


def test_get_rss_sources_includes_catalog_and_global(agent, mock_catalog):
    mock_catalog.get_rss_feeds.return_value = ["https://custom.com/rss"]
    sources = agent._get_rss_sources("TASS")
    assert "https://custom.com/rss" in sources
    for global_feed in GLOBAL_RSS_FEEDS[:3]:
        assert global_feed in sources


def test_rss_item_to_signal():
    item = make_rss_item(title="News", url="https://x.com/1", source_name="Reuters")
    signal = NewsScout._rss_item_to_signal(item)
    assert signal.source_type == SignalSource.RSS
    assert signal.source_name == "Reuters"
    assert signal.id.startswith("rss_")


def test_search_result_to_signal():
    result = make_search_result(title="Found", url="https://x.com/2")
    signal = NewsScout._search_result_to_signal(result)
    assert signal.source_type == SignalSource.WEB_SEARCH
    assert signal.id.startswith("ws_")


def test_global_rss_feeds_no_dead_reuters():
    """Reuters closed public RSS in 2020 — feeds.reuters.com must not be in global list."""
    from src.agents.collectors.news_scout import GLOBAL_RSS_FEEDS

    for url in GLOBAL_RSS_FEEDS:
        assert "feeds.reuters.com" not in url, f"Dead Reuters feed in GLOBAL_RSS_FEEDS: {url}"
