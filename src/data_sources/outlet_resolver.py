"""Dynamic outlet resolver — enriches unknown media outlets.

Спека: docs/03-collectors.md (outlet catalog enrichment).
Контракт: outlet name → OutletInfo (from catalog, DB cache, or Wikidata + RSS discovery).

Resolution chain:
  1. Static catalog (hardcoded, 20 outlets) — instant
  2. DB cache (SQLite, TTL 30 days) — instant
  3. Wikidata SPARQL → website + language + country — ~1-2s
  4. RSS autodiscovery → feed URLs — ~1-3s
  5. Cache result in DB for future lookups
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.collectors.protocols import OutletCatalogProto, OutletInfo
from src.data_sources.feed_discovery import discover_feeds
from src.data_sources.wikidata_client import wikidata_lookup
from src.db.models import Outlet
from src.db.repositories import OutletRepository

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = 30


class OutletResolver:
    """Resolves outlet names to OutletInfo with enrichment fallback."""

    def __init__(
        self,
        *,
        catalog: OutletCatalogProto,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._catalog = catalog
        self._session_factory = session_factory

    # --- Sync methods (OutletCatalogProto) for collector compatibility ---

    def get_outlet(self, name: str) -> OutletInfo | None:
        """Sync lookup — delegates to static catalog only.

        Used by collectors (NewsScout, OutletHistorian) which need sync access.
        For async resolution with Wikidata/RSS, use resolve().
        """
        return self._catalog.get_outlet(name)

    def get_rss_feeds(self, name: str) -> list[str]:
        """Sync RSS feeds lookup — delegates to static catalog."""
        return self._catalog.get_rss_feeds(name)

    # --- Async methods (OutletResolverProto) for enrichment ---

    async def resolve(self, name: str) -> OutletInfo | None:
        """Resolve outlet name to OutletInfo.

        Priority: static catalog → DB cache → Wikidata + feed discovery.
        """
        # 1. Static catalog (fast path)
        info = self._catalog.get_outlet(name)
        if info is not None:
            return info

        # 2. DB cache
        info = await self._from_db_cache(name)
        if info is not None:
            return info

        # 3. Wikidata + feed discovery (slow path)
        return await self._resolve_via_wikidata(name)

    async def resolve_by_url(self, url: str) -> OutletInfo | None:
        """Resolve outlet from a website URL directly."""
        feeds = await discover_feeds(url)
        if not feeds and not url:
            return None

        # Extract domain as name
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain_name = parsed.netloc.replace("www.", "")

        info = OutletInfo(
            name=domain_name,
            website_url=url,
            rss_feeds=feeds,
        )
        await self._cache_to_db(info)
        return info

    async def _from_db_cache(self, name: str) -> OutletInfo | None:
        """Look up outlet in DB, respecting TTL."""
        normalized = name.strip().lower()
        async with self._session_factory() as session:
            repo = OutletRepository(session)
            outlet = await repo.get_by_name(normalized)
            if outlet is None:
                return None

            # Check TTL
            if outlet.last_analyzed_at is not None:
                age = datetime.now(timezone.utc) - outlet.last_analyzed_at.replace(
                    tzinfo=timezone.utc
                )
                if age > timedelta(days=_CACHE_TTL_DAYS):
                    logger.info("DB cache expired for %r (age: %s)", name, age)
                    return None

            rss_feeds = []
            if outlet.rss_feeds:
                rss_feeds = [f.get("url", "") for f in outlet.rss_feeds if f.get("url")]

            return OutletInfo(
                name=outlet.name,
                language=outlet.language or "ru",
                website_url=outlet.website_url or "",
                rss_feeds=rss_feeds,
            )

    async def _resolve_via_wikidata(self, name: str) -> OutletInfo | None:
        """Look up outlet via Wikidata SPARQL, then discover RSS feeds."""
        wiki_result = await wikidata_lookup(name)
        if wiki_result is None or not wiki_result.website_url:
            return None

        feeds = await discover_feeds(wiki_result.website_url)

        info = OutletInfo(
            name=wiki_result.name,
            language=wiki_result.language or "ru",
            website_url=wiki_result.website_url,
            rss_feeds=feeds,
        )
        await self._cache_to_db(info)
        return info

    async def _cache_to_db(self, info: OutletInfo) -> None:
        """Save resolved outlet to DB for future cache hits."""
        try:
            async with self._session_factory() as session:
                repo = OutletRepository(session)
                await repo.upsert(
                    {
                        "name": info.name,
                        "normalized_name": info.name.strip().lower(),
                        "language": info.language,
                        "website_url": info.website_url,
                        "rss_feeds": [{"url": url} for url in info.rss_feeds],
                        "last_analyzed_at": datetime.now(timezone.utc),
                    }
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to cache outlet %r: %s", info.name, exc)
