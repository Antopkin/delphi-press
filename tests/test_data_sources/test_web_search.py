"""Tests for src.data_sources.web_search."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.agents.collectors.protocols import SearchResult
from src.data_sources.web_search import (
    ExaSearchProvider,
    JinaSearchProvider,
    WebSearchService,
    _TokenBucket,
)

EXA_RESPONSE = {
    "results": [
        {
            "title": "Test Article",
            "url": "https://example.com/1",
            "text": "Some content here.",
            "publishedDate": "2025-03-24T12:00:00Z",
        },
        {
            "title": "Another Article",
            "url": "https://example.com/2",
            "text": "More content.",
        },
    ]
}

JINA_RESPONSE = {
    "data": [
        {
            "title": "Jina Result",
            "url": "https://example.com/3",
            "description": "Found via Jina.",
        },
    ]
}


class TestExaSearchProvider:
    @pytest.mark.asyncio
    async def test_search(self):
        provider = ExaSearchProvider("test-key")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            provider._client, "post", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("test query")

        assert len(results) == 2
        assert results[0].title == "Test Article"
        assert results[0].url == "https://example.com/1"
        assert results[0].published_at is not None

    @pytest.mark.asyncio
    async def test_search_error(self):
        provider = ExaSearchProvider("test-key")
        with patch.object(
            provider._client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            results = await provider.search("test query")
        assert results == []


class TestJinaSearchProvider:
    @pytest.mark.asyncio
    async def test_search(self):
        provider = JinaSearchProvider("test-key")
        mock_response = httpx.Response(
            200,
            json=JINA_RESPONSE,
            request=httpx.Request("GET", "https://s.jina.ai/test"),
        )
        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("test query")

        assert len(results) == 1
        assert results[0].title == "Jina Result"


class TestWebSearchService:
    @pytest.mark.asyncio
    async def test_search_with_exa(self):
        service = WebSearchService(exa_api_key="test-exa")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            results = await service.search("test")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_no_providers(self):
        service = WebSearchService()
        results = await service.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_fallback_to_jina(self):
        service = WebSearchService(exa_api_key="exa", jina_api_key="jina")
        # Exa fails
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("exa down"),
        ):
            mock_jina = httpx.Response(
                200,
                json=JINA_RESPONSE,
                request=httpx.Request("GET", "https://s.jina.ai/test"),
            )
            with patch.object(
                service._providers[1]._client,
                "get",
                new_callable=AsyncMock,
                return_value=mock_jina,
            ):
                results = await service.search("test")

        assert len(results) == 1
        assert results[0].title == "Jina Result"

    @pytest.mark.asyncio
    async def test_multi_search_dedup(self):
        service = WebSearchService(exa_api_key="test")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            results = await service.multi_search(["query1", "query2"])

        # Same results from both queries → should dedup
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        service = WebSearchService(exa_api_key="test")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        mock_post = AsyncMock(return_value=mock_response)
        with patch.object(service._providers[0]._client, "post", mock_post):
            await service.search("same query")
            await service.search("same query")

        assert mock_post.await_count == 1


class TestTokenBucketNoLockDuringSleep:
    """Bug 1: Token bucket should NOT hold lock during sleep."""

    @pytest.mark.asyncio
    async def test_lock_released_during_sleep(self):
        """Verify the lock is NOT held while sleeping.

        Strategy: drain the bucket, start acquire() (which must sleep),
        then check if the lock can be acquired concurrently.

        With bug: lock is held during sleep → try_lock fails.
        With fix: lock is released during sleep → try_lock succeeds.
        """
        bucket = _TokenBucket(rate=1.0, capacity=1)
        # Drain the only token
        await bucket.acquire()

        lock_was_free = False

        async def probe_lock() -> None:
            """Wait a tiny bit for acquire() to start sleeping, then try the lock."""
            nonlocal lock_was_free
            await asyncio.sleep(0.05)  # give acquire() time to enter sleep
            # Try to acquire the lock with a short timeout.
            # If the lock is free (fix applied), this succeeds instantly.
            # If the lock is held (bug), this times out.
            try:
                async with asyncio.timeout(0.1):
                    async with bucket._lock:
                        lock_was_free = True
            except TimeoutError:
                lock_was_free = False

        # Start acquire (will sleep ~1s waiting for a token) and probe concurrently
        await asyncio.gather(bucket.acquire(), probe_lock())

        assert lock_was_free, "Lock was held during sleep — bug still present"


class TestWebSearchCacheEviction:
    """Bug 2: Cache should evict expired entries and stay bounded."""

    @pytest.mark.asyncio
    async def test_cache_evicts_expired(self):
        """Expired cache entries should be removed on next cache write."""
        service = WebSearchService(exa_api_key="test")

        # Manually insert 3 expired entries (timestamp far in the past)
        old_ts = time.monotonic() - 9999.0  # way beyond 600s TTL
        for i in range(3):
            service._cache[f"expired_query_{i}:10"] = (
                old_ts,
                [SearchResult(title=f"Old {i}", url=f"https://old.example.com/{i}")],
            )

        assert len(service._cache) == 3

        # Trigger a real cache write via search()
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            await service.search("fresh query")

        # Expired entries should be gone; only the fresh entry remains
        assert "expired_query_0:10" not in service._cache
        assert "expired_query_1:10" not in service._cache
        assert "expired_query_2:10" not in service._cache
        assert "fresh query:10" in service._cache

    @pytest.mark.asyncio
    async def test_cache_bounded_size(self):
        """Cache should not exceed _MAX_CACHE_SIZE."""
        service = WebSearchService(exa_api_key="test")
        max_size = service._MAX_CACHE_SIZE

        # Fill cache to max with non-expired entries
        now = time.monotonic()
        for i in range(max_size):
            service._cache[f"query_{i}:10"] = (
                now,
                [SearchResult(title=f"Result {i}", url=f"https://example.com/{i}")],
            )

        assert len(service._cache) == max_size

        # Trigger one more cache write
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            await service.search("overflow query")

        assert len(service._cache) <= max_size
