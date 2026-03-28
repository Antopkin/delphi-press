"""Async RSS fetcher — реализация RSSFetcherProto.

Спека: docs/01-data-sources.md (§2).
Контракт: RSSFetcher.fetch_feeds(urls, days_back=7) → list[RSSItem].

Стек: httpx (async HTTP) + fastfeedparser (fast parse) + feedparser (fallback).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import fastfeedparser
import feedparser
import httpx

from src.agents.collectors.protocols import RSSItem

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    """In-memory cache entry for a single feed."""

    fetched_at: float  # time.monotonic()
    etag: str | None = None
    last_modified: str | None = None
    records: list[RSSItem] = field(default_factory=list)


class RSSFetcher:
    """Асинхронный сборщик RSS-фидов с кешированием и concurrency control.

    Реализует RSSFetcherProto для NewsScout.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 20,
        timeout_seconds: float = 15.0,
        cache_ttl_seconds: int = 300,
        user_agent: str = "DelphiPress/1.0 (RSS fetcher)",
    ) -> None:
        self._timeout = timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cache: dict[str, _CacheEntry] = {}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    async def fetch_feeds(
        self,
        urls: list[str],
        *,
        days_back: int = 7,
    ) -> list[RSSItem]:
        """Load and parse multiple RSS feeds in parallel.

        Matches RSSFetcherProto signature: fetch_feeds(urls, days_back=7) -> list[RSSItem].
        Returns deduplicated list sorted by published_at (newest first).
        """
        since = datetime.now(UTC) - timedelta(days=days_back)

        tasks = [self._fetch_single_with_cache(url, since) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[RSSItem] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("RSS feed error for %s: %s", urls[i], result)
                continue
            all_items.extend(result)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped: list[RSSItem] = []
        for item in all_items:
            url_key = item.url.rstrip("/").lower()
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                deduped.append(item)

        # Sort by published_at (newest first), None last
        deduped.sort(
            key=lambda r: r.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return deduped

    async def _fetch_single_with_cache(
        self,
        feed_url: str,
        since: datetime,
    ) -> list[RSSItem]:
        """Fetch single feed with caching and conditional GET."""
        # Check cache
        cached = self._cache.get(feed_url)
        now = time.monotonic()
        if cached and (now - cached.fetched_at) < self._cache_ttl:
            return [r for r in cached.records if _after(r.published_at, since)]

        # Fetch with semaphore
        async with self._semaphore:
            return await self._fetch_and_parse(feed_url, since, cached)

    async def _fetch_and_parse(
        self,
        feed_url: str,
        since: datetime,
        cached: _CacheEntry | None,
    ) -> list[RSSItem]:
        """HTTP GET with conditional headers, parse, cache."""
        headers: dict[str, str] = {}
        if cached:
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified

        try:
            response = await self._client.get(feed_url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("HTTP error fetching %s: %s", feed_url, exc)
            return cached.records if cached else []

        # 304 Not Modified → return cache
        if response.status_code == 304 and cached:
            cached.fetched_at = time.monotonic()
            return [r for r in cached.records if _after(r.published_at, since)]

        if response.status_code != 200:
            logger.warning("HTTP %d for %s", response.status_code, feed_url)
            return cached.records if cached else []

        # Parse
        text = response.text
        items = self._parse_feed(text, feed_url, since)

        # Update cache
        self._cache[feed_url] = _CacheEntry(
            fetched_at=time.monotonic(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            records=items,
        )

        return items

    def _parse_feed(
        self,
        text: str,
        feed_url: str,
        since: datetime,
    ) -> list[RSSItem]:
        """Parse RSS/Atom text into RSSItem list.

        Uses fastfeedparser with feedparser fallback.
        """
        try:
            parsed = fastfeedparser.parse(text)
            entries = parsed.get("entries", [])
        except Exception:
            logger.debug("fastfeedparser failed for %s, trying feedparser", feed_url)
            try:
                parsed = feedparser.parse(text)
                entries = parsed.get("entries", [])
            except Exception as exc:
                logger.warning("All parsers failed for %s: %s", feed_url, exc)
                return []

        items: list[RSSItem] = []
        source_name = self._extract_source_name(parsed, feed_url)

        for entry in entries:
            published_at = _parse_date(entry)
            if published_at and published_at < since:
                continue

            title = _clean_text(entry.get("title", ""))
            if not title:
                continue

            summary = _clean_text(entry.get("summary", entry.get("description", "")))
            url = entry.get("link", entry.get("id", ""))
            categories = [
                t.get("term", t) if isinstance(t, dict) else str(t) for t in entry.get("tags", [])
            ]

            items.append(
                RSSItem(
                    title=title,
                    summary=summary[:1000] if summary else "",
                    url=url,
                    published_at=published_at,
                    source_name=source_name,
                    categories=categories,
                )
            )

        return items

    def _extract_source_name(self, parsed: dict, feed_url: str) -> str:
        """Extract source name from feed metadata or URL."""
        feed_info = parsed.get("feed", {})
        title = feed_info.get("title", "")
        if title:
            return title
        # Fallback: extract domain
        from urllib.parse import urlparse

        return urlparse(feed_url).hostname or feed_url

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()


def _parse_date(entry: dict) -> datetime | None:
    """Try to parse date from RSS entry."""
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            # Try _parsed variant (feedparser format)
            parsed_key = f"{key}_parsed"
            struct = entry.get(parsed_key)
            if struct:
                try:
                    from calendar import timegm

                    ts = timegm(struct)
                    return datetime.fromtimestamp(ts, tz=UTC)
                except (TypeError, ValueError, OverflowError):
                    continue
            continue
        if isinstance(raw, str):
            try:
                return parsedate_to_datetime(raw).replace(tzinfo=UTC)
            except (TypeError, ValueError):
                pass
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                pass
    return None


def _after(dt: datetime | None, since: datetime) -> bool:
    """Check if datetime is after since. None → True (keep undated items)."""
    if dt is None:
        return True
    return dt >= since


def _clean_text(text: str) -> str:
    """Strip HTML tags and whitespace from text."""
    if not text:
        return ""
    import re

    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
