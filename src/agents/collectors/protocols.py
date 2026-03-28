"""Протоколы внешних зависимостей для коллекторов.

Спека: docs/03-collectors.md.

Коллекторы зависят от внешних сервисов (RSS, поиск, скрейпинг, кеш).
Все зависимости — Protocol-based для тестируемости.
Реализации — в src/data_sources/ (отдельный модуль).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.schemas.events import OutletProfile

# =====================================================================
# Data classes for intermediate results (not in PipelineContext)
# =====================================================================


class RSSItem(BaseModel):
    """Нормализованный элемент RSS-ленты."""

    title: str
    summary: str = ""
    url: str
    published_at: datetime | None = None
    source_name: str = ""
    categories: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Результат веб-поиска."""

    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None


class ScrapedArticle(BaseModel):
    """Статья, извлечённая скрейпером."""

    headline: str
    first_paragraph: str = ""
    url: str = ""
    published_at: datetime | None = None
    categories: list[str] = Field(default_factory=list)


class OutletInfo(BaseModel, frozen=True):
    """Запись каталога изданий."""

    name: str
    language: str = "ru"
    website_url: str = ""
    rss_feeds: list[str] = Field(default_factory=list)
    description: str = ""


# =====================================================================
# Protocol interfaces
# =====================================================================


class RSSFetcherProto(Protocol):
    """Протокол для загрузки и парсинга RSS-лент."""

    async def fetch_feeds(self, urls: list[str], *, days_back: int = 7) -> list[RSSItem]: ...


class WebSearchProto(Protocol):
    """Протокол для веб-поиска."""

    async def search(self, query: str, *, num_results: int = 10) -> list[SearchResult]: ...


class ArticleScraperProto(Protocol):
    """Протокол для скрейпинга статей издания."""

    async def scrape_articles(
        self, url: str, *, days_back: int = 30, max_articles: int = 100
    ) -> list[ScrapedArticle]: ...


class OutletCatalogProto(Protocol):
    """Протокол для каталога изданий."""

    def get_outlet(self, name: str) -> OutletInfo | None: ...

    def get_rss_feeds(self, name: str) -> list[str]: ...


class ProfileCacheProto(Protocol):
    """Протокол для кеша профилей изданий."""

    async def get(self, outlet: str, ttl_days: int = 7) -> OutletProfile | None: ...

    async def put(self, outlet: str, profile: OutletProfile) -> None: ...


# =====================================================================
# Foresight data source protocols
# =====================================================================


class MetaculusClientProto(Protocol):
    """Протокол для Metaculus API клиента."""

    async def fetch_questions(
        self, query: str, *, limit: int = 20, status: str = "open"
    ) -> list[dict[str, Any]]: ...


class PolymarketClientProto(Protocol):
    """Протокол для Polymarket CLOB API клиента."""

    async def fetch_markets(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]: ...

    async def fetch_enriched_markets(
        self, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]: ...


class GdeltClientProto(Protocol):
    """Протокол для GDELT DOC 2.0 API клиента."""

    async def fetch_articles(
        self, query: str, *, language: str = "english", limit: int = 50, days_back: int = 3
    ) -> list[dict[str, Any]]: ...
