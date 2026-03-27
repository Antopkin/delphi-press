"""Shared fixtures for collector agent tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.collectors.protocols import OutletInfo, RSSItem, ScrapedArticle, SearchResult
from src.schemas.llm import LLMResponse


@pytest.fixture
def mock_rss_fetcher() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_web_search() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_catalog() -> Mock:
    catalog = Mock()
    catalog.get_outlet.return_value = OutletInfo(
        name="TASS",
        language="ru",
        website_url="https://tass.com",
        rss_feeds=["https://tass.com/rss/v2.xml"],
    )
    catalog.get_rss_feeds.return_value = ["https://tass.com/rss/v2.xml"]
    return catalog


@pytest.fixture
def mock_scraper() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_cache() -> AsyncMock:
    cache = AsyncMock()
    cache.get.return_value = None
    return cache


def make_rss_item(**kwargs: object) -> RSSItem:
    """Factory for RSSItem test instances."""
    defaults: dict = {
        "title": "Test News",
        "url": "https://example.com/1",
        "source_name": "Reuters",
    }
    defaults.update(kwargs)
    return RSSItem(**defaults)


def make_search_result(**kwargs: object) -> SearchResult:
    """Factory for SearchResult test instances."""
    defaults: dict = {
        "title": "Search Result",
        "url": "https://example.com/2",
        "snippet": "Some text",
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


def make_scraped_article(**kwargs: object) -> ScrapedArticle:
    """Factory for ScrapedArticle test instances."""
    defaults: dict = {
        "headline": "Test Headline",
        "first_paragraph": "Test paragraph with some content.",
        "url": "https://tass.com/article/1",
    }
    defaults.update(kwargs)
    return ScrapedArticle(**defaults)


def make_llm_response(content: str, model: str = "openai/gpt-4o-mini") -> LLMResponse:
    """Factory for LLMResponse test instances."""
    return LLMResponse(
        content=content,
        model=model,
        provider="openrouter",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.001,
        duration_ms=500,
    )
