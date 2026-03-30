"""E2E integration test fixtures.

Provides a complete mock environment for running all 18 agents through
the 9-stage pipeline without any real LLM calls or external API calls.

Every external dependency (RSS, web search, scraper, foresight APIs)
is replaced with an AsyncMock/Mock returning Pydantic models that match
the Protocol interfaces defined in ``src/agents/collectors/protocols.py``.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.collectors.protocols import (
    OutletInfo,
    RSSItem,
    ScrapedArticle,
    SearchResult,
)
from src.agents.orchestrator import Orchestrator
from src.agents.registry import build_default_registry
from src.schemas.prediction import PredictionRequest
from tests.fixtures.llm_responses import build_all_dispatchers
from tests.fixtures.mock_llm import MockLLMClient

# =====================================================================
# LLM client
# =====================================================================


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """MockLLMClient with all task dispatchers registered."""
    client = MockLLMClient()
    dispatchers = build_all_dispatchers()
    for task, dispatcher in dispatchers.items():
        client.register(task, dispatcher)
    return client


# =====================================================================
# Data source mocks (Protocol-compatible return types)
# =====================================================================


@pytest.fixture
def mock_rss_fetcher() -> AsyncMock:
    """Mock ``RSSFetcherProto`` returning 15 ``RSSItem`` instances."""
    fetcher = AsyncMock()
    fetcher.fetch_feeds.return_value = [
        RSSItem(
            title=f"Новость {i}: Важное событие в мире",
            url=f"https://tass.ru/news/{i}",
            published_at=datetime(2026, 3, 28, 10, 0, 0),
            summary=f"Краткое описание новости номер {i} о важном событии.",
            source_name="ТАСС",
            categories=["politics"],
        )
        for i in range(15)
    ]
    return fetcher


@pytest.fixture
def mock_web_search() -> AsyncMock:
    """Mock ``WebSearchProto`` returning 10 ``SearchResult`` per query."""
    search = AsyncMock()
    search.search.return_value = [
        SearchResult(
            title=f"Результат поиска {i}",
            url=f"https://example.com/result/{i}",
            snippet=f"Описание результата поиска {i}",
        )
        for i in range(10)
    ]
    return search


@pytest.fixture
def mock_outlet_catalog() -> Mock:
    """Mock ``OutletCatalogProto`` with TASS outlet info."""
    catalog = Mock()
    catalog.get_outlet.return_value = OutletInfo(
        name="ТАСС",
        language="ru",
        website_url="https://tass.ru",
        rss_feeds=["https://tass.ru/rss/v2.xml"],
        description="Информационное агентство России",
    )
    catalog.get_rss_feeds.return_value = ["https://tass.ru/rss/v2.xml"]
    return catalog


@pytest.fixture
def mock_scraper() -> AsyncMock:
    """Mock ``ArticleScraperProto`` returning 20 ``ScrapedArticle`` instances."""
    scraper = AsyncMock()
    scraper.scrape_articles.return_value = [
        ScrapedArticle(
            headline=f"Заголовок статьи {i}",
            first_paragraph=f"Первый абзац статьи {i} с ключевой информацией о событии.",
            url=f"https://tass.ru/article/{i}",
            published_at=datetime(2026, 3, 28 - i, 10, 0, 0),
            categories=["politics", "economy"],
        )
        for i in range(20)
    ]
    return scraper


@pytest.fixture
def mock_profile_cache() -> AsyncMock:
    """Mock ``ProfileCacheProto`` -- always cache miss."""
    cache = AsyncMock()
    cache.get.return_value = None
    cache.put.return_value = None
    return cache


@pytest.fixture
def mock_metaculus() -> AsyncMock:
    """Mock ``MetaculusClientProto``."""
    client = AsyncMock()
    client.fetch_questions.return_value = [
        {"id": 1, "title": "Question 1", "probability": 0.6, "url": "https://metaculus.com/q/1"},
    ]
    return client


@pytest.fixture
def mock_polymarket() -> AsyncMock:
    """Mock ``PolymarketClientProto``."""
    client = AsyncMock()
    client.fetch_markets.return_value = [
        {
            "id": "pm1",
            "title": "Market 1",
            "probability": 0.55,
            "url": "https://polymarket.com/m/1",
        },
    ]
    client.fetch_trades_batch.return_value = {}
    return client


@pytest.fixture
def mock_gdelt() -> AsyncMock:
    """Mock ``GdeltClientProto``."""
    client = AsyncMock()
    client.fetch_articles.return_value = [
        {"title": "GDELT Article 1", "url": "https://example.com/gdelt/1", "tone": 0.5},
    ]
    return client


# =====================================================================
# Combined dependencies
# =====================================================================


@pytest.fixture
def collector_deps(
    mock_rss_fetcher: AsyncMock,
    mock_web_search: AsyncMock,
    mock_outlet_catalog: Mock,
    mock_scraper: AsyncMock,
    mock_profile_cache: AsyncMock,
    mock_metaculus: AsyncMock,
    mock_polymarket: AsyncMock,
    mock_gdelt: AsyncMock,
) -> dict:
    """Combined collector dependencies dict for ``build_default_registry``."""
    return {
        "rss_fetcher": mock_rss_fetcher,
        "web_search": mock_web_search,
        "outlet_catalog": mock_outlet_catalog,
        "scraper": mock_scraper,
        "profile_cache": mock_profile_cache,
        "metaculus_client": mock_metaculus,
        "polymarket_client": mock_polymarket,
        "gdelt_client": mock_gdelt,
    }


# =====================================================================
# Registry, Orchestrator, Request
# =====================================================================


@pytest.fixture
def e2e_registry(mock_llm_client: MockLLMClient, collector_deps: dict):
    """Full AgentRegistry with all 18 real agents and mock LLM."""
    return build_default_registry(mock_llm_client, collector_deps=collector_deps)


@pytest.fixture
def e2e_orchestrator(e2e_registry) -> Orchestrator:
    """Orchestrator ready for E2E test."""
    return Orchestrator(e2e_registry)


@pytest.fixture
def prediction_request() -> PredictionRequest:
    """Standard test prediction request for TASS, 2026-03-29."""
    return PredictionRequest(outlet="ТАСС", target_date=date(2026, 3, 29))
