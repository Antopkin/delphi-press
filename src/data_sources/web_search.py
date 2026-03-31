"""Web search — реализация WebSearchProto.

Спека: docs/01-data-sources.md (§3).
Контракт: WebSearchService.search(query, num_results=10) → list[SearchResult].

Провайдеры: Exa (primary) + Jina (fallback). Оба — через httpx.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from src.agents.collectors.protocols import SearchResult
from src.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class _TokenBucket:
    """Simple token bucket for async rate limiting."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last_refill = now

                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._rate
            # Sleep OUTSIDE the lock so other coroutines are not blocked
            await asyncio.sleep(wait)


class ExaSearchProvider:
    """Exa API search provider."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
            },
        )
        self._bucket = _TokenBucket(rate=20 / 60, capacity=20)

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
    ) -> list[SearchResult]:
        """Search via Exa API."""
        await self._bucket.acquire()

        start_date = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {
            "query": query,
            "numResults": num_results,
            "type": "neural",
            "startPublishedDate": start_date,
            "contents": {"text": True},
        }

        try:

            async def _do_exa() -> httpx.Response:
                resp = await self._client.post("https://api.exa.ai/search", json=payload)
                resp.raise_for_status()
                return resp

            response = await retry_with_backoff(_do_exa, max_retries=2, base_delay=2.0)
        except httpx.HTTPError as exc:
            logger.warning("Exa search failed: %s", exc)
            return []

        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("results", []):
            published_at = None
            if item.get("publishedDate"):
                try:
                    published_at = datetime.fromisoformat(
                        item["publishedDate"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("text", "") or "")[:500],
                    published_at=published_at,
                )
            )

        return results

    async def close(self) -> None:
        await self._client.aclose()


class JinaSearchProvider:
    """Jina search provider."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "X-Return-Format": "json",
            },
        )
        self._bucket = _TokenBucket(rate=15 / 60, capacity=15)

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
    ) -> list[SearchResult]:
        """Search via Jina API."""
        await self._bucket.acquire()

        try:

            async def _do_jina() -> httpx.Response:
                resp = await self._client.get(
                    f"https://s.jina.ai/{query}",
                    params={"count": num_results},
                )
                resp.raise_for_status()
                return resp

            response = await retry_with_backoff(_do_jina, max_retries=2, base_delay=2.0)
        except httpx.HTTPError as exc:
            logger.warning("Jina search failed: %s", exc)
            return []

        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("data", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("description", "") or "")[:500],
                    published_at=None,
                )
            )

        return results

    async def close(self) -> None:
        await self._client.aclose()


class WebSearchService:
    """Facade: search with fallback between providers.

    Implements WebSearchProto: search(query, num_results=10) -> list[SearchResult].
    """

    _MAX_CACHE_SIZE = 500

    def __init__(
        self,
        *,
        exa_api_key: str = "",
        jina_api_key: str = "",
    ) -> None:
        self._providers: list[ExaSearchProvider | JinaSearchProvider] = []
        if exa_api_key:
            self._providers.append(ExaSearchProvider(exa_api_key))
        if jina_api_key:
            self._providers.append(JinaSearchProvider(jina_api_key))
        self._cache: dict[str, tuple[float, list[SearchResult]]] = {}
        self._cache_ttl = 600.0  # 10 minutes

    def _evict_expired(self) -> None:
        """Remove cache entries whose TTL has expired."""
        now = time.monotonic()
        expired_keys = [k for k, (ts, _) in self._cache.items() if now - ts >= self._cache_ttl]
        for k in expired_keys:
            del self._cache[k]

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
    ) -> list[SearchResult]:
        """Search with fallback. Matches WebSearchProto signature."""
        if not self._providers:
            logger.debug("No search providers configured (no API keys)")
            return []

        # Check cache
        cache_key = f"{query}:{num_results}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        # Try providers in order (primary → fallback)
        for provider in self._providers:
            try:
                results = await provider.search(query, num_results=num_results)
                if results:
                    # Deduplicate by URL
                    seen: set[str] = set()
                    deduped: list[SearchResult] = []
                    for r in results:
                        url_key = r.url.rstrip("/").lower()
                        if url_key not in seen:
                            seen.add(url_key)
                            deduped.append(r)

                    self._evict_expired()
                    if len(self._cache) >= self._MAX_CACHE_SIZE:
                        # Remove the oldest entry by timestamp
                        oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                        del self._cache[oldest_key]
                    self._cache[cache_key] = (time.monotonic(), deduped)
                    return deduped
            except Exception as exc:
                name = type(provider).__name__
                logger.warning("Search provider %s failed: %s", name, exc)
                continue

        return []

    async def multi_search(
        self,
        queries: list[str],
        *,
        num_results_per_query: int = 10,
    ) -> list[SearchResult]:
        """Parallel search over multiple queries with deduplication."""
        tasks = [self.search(q, num_results=num_results_per_query) for q in queries]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[SearchResult] = []
        for result in results_lists:
            if isinstance(result, Exception):
                continue
            all_results.extend(result)

        # Global dedup
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in all_results:
            url_key = r.url.rstrip("/").lower()
            if url_key not in seen:
                seen.add(url_key)
                deduped.append(r)

        return deduped

    async def close(self) -> None:
        """Close all provider HTTP clients."""
        for provider in self._providers:
            await provider.close()
