"""Tests for OutletHistorian collector agent."""

from __future__ import annotations

import json

import pytest

from src.agents.collectors.outlet_historian import OutletHistorian
from src.schemas.events import (
    EditorialPosition,
    HeadlineStyle,
    OutletProfile,
    WritingStyle,
)
from tests.test_agents.test_collectors.conftest import make_llm_response, make_scraped_article


@pytest.fixture
def agent(mock_router, mock_scraper, mock_catalog, mock_cache):
    return OutletHistorian(
        mock_router,
        scraper=mock_scraper,
        outlet_catalog=mock_catalog,
        profile_cache=mock_cache,
    )


# ── Helpers ───────────────────────────────────────────────────────────

HEADLINE_JSON = json.dumps(
    {
        "avg_length_chars": 55,
        "avg_length_words": 7,
        "uses_colons": True,
        "uses_quotes": False,
        "uses_questions": False,
        "uses_numbers": True,
        "capitalization": "sentence_case",
        "vocabulary_register": "formal",
        "emotional_tone": "neutral",
        "common_patterns": ["Topic: detail"],
    }
)

WRITING_JSON = json.dumps(
    {
        "first_paragraph_style": "inverted_pyramid",
        "avg_first_paragraph_sentences": 2,
        "avg_first_paragraph_words": 35,
        "attribution_style": "source_first",
        "uses_dateline": True,
        "paragraph_length": "short",
    }
)

EDITORIAL_JSON = json.dumps(
    {
        "tone": "neutral",
        "focus_topics": ["politics", "economy"],
        "avoided_topics": [],
        "framing_tendencies": ["analytical"],
        "source_preferences": ["official"],
        "stance_on_current_topics": {},
        "omissions": [],
    }
)


def _setup_scraper_and_llm(mock_scraper, mock_router, num_articles=10):
    """Configure scraper to return articles and router to return analysis JSON."""
    articles = [
        make_scraped_article(
            headline=f"Headline {i}",
            first_paragraph=f"Paragraph {i} content.",
            url=f"https://tass.com/article/{i}",
        )
        for i in range(num_articles)
    ]
    mock_scraper.scrape_articles.return_value = articles
    mock_router.complete.side_effect = [
        make_llm_response(HEADLINE_JSON, model="anthropic/claude-sonnet-4"),
        make_llm_response(WRITING_JSON, model="anthropic/claude-sonnet-4"),
        make_llm_response(EDITORIAL_JSON, model="anthropic/claude-sonnet-4"),
    ]


# ── Name & timeout ────────────────────────────────────────────────────


def test_outlet_historian_has_correct_name(agent):
    assert agent.name == "outlet_historian"


def test_outlet_historian_timeout_is_600(agent):
    assert agent.get_timeout_seconds() == 600


# ── Validation ────────────────────────────────────────────────────────


def test_validate_context_missing_outlet(agent, make_context):
    ctx = make_context(outlet="")
    assert agent.validate_context(ctx) is not None


def test_validate_context_valid(agent, make_context):
    assert agent.validate_context(make_context()) is None


# ── Cache hit ─────────────────────────────────────────────────────────


async def test_execute_returns_cached_profile(
    agent, make_context, mock_cache, mock_scraper, mock_router
):
    cached_profile = OutletProfile(
        outlet_name="TASS",
        headline_style=HeadlineStyle(),
        writing_style=WritingStyle(),
        editorial_position=EditorialPosition(),
    )
    mock_cache.get.return_value = cached_profile

    result = await agent.execute(make_context())
    assert result["outlet_profile"]["outlet_name"] == "TASS"
    mock_scraper.scrape_articles.assert_not_called()
    mock_router.complete.assert_not_called()


# ── Cache miss → full analysis ────────────────────────────────────────


async def test_execute_caches_new_profile(
    agent, make_context, mock_cache, mock_scraper, mock_router
):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    await agent.execute(make_context())
    mock_cache.put.assert_called_once()
    args = mock_cache.put.call_args
    assert args[0][0] == "TASS"


async def test_execute_returns_outlet_profile_key(agent, make_context, mock_scraper, mock_router):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    result = await agent.execute(make_context())
    assert "outlet_profile" in result
    assert result["outlet_profile"]["outlet_name"] == "TASS"


# ── Scraping ──────────────────────────────────────────────────────────


async def test_scrapes_articles(agent, make_context, mock_scraper, mock_router):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    await agent.execute(make_context())
    mock_scraper.scrape_articles.assert_called_once()
    call_kwargs = mock_scraper.scrape_articles.call_args
    assert call_kwargs.kwargs["days_back"] == 30
    assert call_kwargs.kwargs["max_articles"] == 100


# ── LLM calls ─────────────────────────────────────────────────────────


async def test_three_llm_calls(agent, make_context, mock_scraper, mock_router):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    await agent.execute(make_context())
    assert mock_router.complete.call_count == 3
    for call in mock_router.complete.call_args_list:
        assert call.kwargs["task"] == "outlet_historian"


async def test_tracks_llm_usage_for_all_calls(agent, make_context, mock_scraper, mock_router):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    await agent.execute(make_context())
    assert agent._tokens_in == 300  # 100 * 3
    assert agent._cost_usd == pytest.approx(0.003)


# ── Error handling ────────────────────────────────────────────────────


async def test_one_llm_call_fails_uses_defaults(agent, make_context, mock_scraper, mock_router):
    articles = [make_scraped_article(headline=f"H{i}", first_paragraph=f"P{i}") for i in range(10)]
    mock_scraper.scrape_articles.return_value = articles

    mock_router.complete.side_effect = [
        RuntimeError("LLM failed"),
        make_llm_response(WRITING_JSON, model="anthropic/claude-sonnet-4"),
        make_llm_response(EDITORIAL_JSON, model="anthropic/claude-sonnet-4"),
    ]

    result = await agent.execute(make_context())
    profile = result["outlet_profile"]
    # Headline style should be defaults since that call failed
    assert profile["headline_style"]["avg_length_chars"] == 60  # default
    # Writing style should be from LLM
    assert profile["writing_style"]["uses_dateline"] is True


async def test_no_articles_returns_default_profile(agent, make_context, mock_scraper, mock_router):
    mock_scraper.scrape_articles.return_value = []

    result = await agent.execute(make_context())
    profile = result["outlet_profile"]
    assert profile["outlet_name"] == "TASS"
    assert profile["articles_analyzed"] == 0
    # All styles should be defaults (no LLM called for empty lists)
    mock_router.complete.assert_not_called()


async def test_scraper_fails_returns_default_profile(
    agent, make_context, mock_scraper, mock_router
):
    mock_scraper.scrape_articles.side_effect = RuntimeError("Scraper down")

    result = await agent.execute(make_context())
    profile = result["outlet_profile"]
    assert profile["outlet_name"] == "TASS"
    assert profile["articles_analyzed"] == 0
    mock_router.complete.assert_not_called()


# ── Output quality ────────────────────────────────────────────────────


async def test_outlet_profile_has_sample_headlines(agent, make_context, mock_scraper, mock_router):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    result = await agent.execute(make_context())
    profile = result["outlet_profile"]
    assert len(profile["sample_headlines"]) == 10
    assert profile["sample_headlines"][0] == "Headline 0"


async def test_catalog_entry_used_for_url(
    agent, make_context, mock_scraper, mock_router, mock_catalog
):
    _setup_scraper_and_llm(mock_scraper, mock_router)

    result = await agent.execute(make_context())
    assert result["outlet_profile"]["outlet_url"] == "https://tass.com"
