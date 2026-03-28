"""Слой сбора данных — конкретные реализации протоколов из collectors.

Спека: docs/01-data-sources.md.
Потребители: NewsScout, EventCalendar, OutletHistorian (src/agents/collectors/).
"""

from src.data_sources.outlets_catalog import OutletsCatalog
from src.data_sources.profile_cache import RedisProfileCache
from src.data_sources.rss import RSSFetcher
from src.data_sources.scraper import NoopScraper
from src.data_sources.web_search import WebSearchService

__all__ = [
    "NoopScraper",
    "OutletsCatalog",
    "RedisProfileCache",
    "RSSFetcher",
    "WebSearchService",
]
