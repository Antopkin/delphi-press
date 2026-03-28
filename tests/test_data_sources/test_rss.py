"""Tests for src.data_sources.rss."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.agents.collectors.protocols import RSSItem
from src.data_sources.rss import RSSFetcher, _CacheEntry, _clean_text, _parse_date

# Sample RSS XML for testing
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Breaking news headline</title>
      <link>https://example.com/article1</link>
      <description>This is a test article summary.</description>
      <pubDate>Mon, 24 Mar 2025 12:00:00 GMT</pubDate>
      <category>Politics</category>
    </item>
    <item>
      <title>Another headline</title>
      <link>https://example.com/article2</link>
      <description>Second article summary.</description>
      <pubDate>Mon, 24 Mar 2025 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def fetcher():
    return RSSFetcher(cache_ttl_seconds=5)


class TestRSSFetcher:
    @pytest.mark.asyncio
    async def test_fetch_feeds_with_mock(self, fetcher):
        """Test parsing a mocked RSS feed."""
        mock_response = httpx.Response(
            200,
            text=SAMPLE_RSS,
            headers={"ETag": '"abc123"'},
            request=httpx.Request("GET", "https://example.com/rss"),
        )
        with patch.object(
            fetcher._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            items = await fetcher.fetch_feeds(["https://example.com/rss"], days_back=365 * 10)

        assert len(items) == 2
        assert items[0].title == "Breaking news headline"
        assert items[0].source_name == "Test Feed"
        assert items[0].url == "https://example.com/article1"
        assert items[1].title == "Another headline"

    @pytest.mark.asyncio
    async def test_cache_hit(self, fetcher):
        """Second call should return from cache."""
        mock_response = httpx.Response(
            200,
            text=SAMPLE_RSS,
            request=httpx.Request("GET", "https://example.com/rss"),
        )
        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(fetcher._client, "get", mock_get):
            await fetcher.fetch_feeds(["https://example.com/rss"], days_back=365 * 10)
            await fetcher.fetch_feeds(["https://example.com/rss"], days_back=365 * 10)

        # Should only be called once (second call from cache)
        assert mock_get.await_count == 1

    @pytest.mark.asyncio
    async def test_conditional_get_304(self, fetcher):
        """HTTP 304 should return cached results."""
        # First call: populate cache
        mock_200 = httpx.Response(
            200,
            text=SAMPLE_RSS,
            headers={"ETag": '"abc"'},
            request=httpx.Request("GET", "https://example.com/rss"),
        )
        mock_304 = httpx.Response(
            304,
            request=httpx.Request("GET", "https://example.com/rss"),
        )

        # Expire cache by setting TTL to 0
        fetcher._cache_ttl = 0

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_200 if call_count == 1 else mock_304

        with patch.object(fetcher._client, "get", side_effect=side_effect):
            items1 = await fetcher.fetch_feeds(["https://example.com/rss"], days_back=365 * 10)
            items2 = await fetcher.fetch_feeds(["https://example.com/rss"], days_back=365 * 10)

        assert len(items1) == 2
        assert len(items2) == 2

    @pytest.mark.asyncio
    async def test_feed_error_returns_empty(self, fetcher):
        """HTTP errors should be handled gracefully."""
        with patch.object(
            fetcher._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            items = await fetcher.fetch_feeds(["https://bad.example.com/rss"])

        assert items == []

    @pytest.mark.asyncio
    async def test_dedup_by_url(self, fetcher):
        """Duplicate URLs across feeds should be deduplicated."""
        mock_response = httpx.Response(
            200,
            text=SAMPLE_RSS,
            request=httpx.Request("GET", "https://example.com/rss"),
        )
        with patch.object(
            fetcher._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            items = await fetcher.fetch_feeds(
                ["https://example.com/rss", "https://example.com/rss"],
                days_back=365 * 10,
            )

        # Same feed twice → should dedup
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_close(self, fetcher):
        """Close should not raise."""
        await fetcher.close()


class TestHelpers:
    def test_parse_date_rfc2822(self):
        entry = {"published": "Mon, 24 Mar 2025 12:00:00 GMT"}
        dt = _parse_date(entry)
        assert dt is not None
        assert dt.year == 2025

    def test_parse_date_iso(self):
        entry = {"published": "2025-03-24T12:00:00Z"}
        dt = _parse_date(entry)
        assert dt is not None

    def test_parse_date_none(self):
        assert _parse_date({}) is None

    def test_clean_text_html(self):
        assert _clean_text("<b>Hello</b> <i>world</i>") == "Hello world"

    def test_clean_text_empty(self):
        assert _clean_text("") == ""

    def test_parse_date_non_utc_timezone(self):
        """Bug 3: +0300 timezone should be converted to UTC, not replaced.

        Input: 12:00:00 +0300 → Expected output: 09:00:00 UTC.
        With bug (replace): output would be 12:00:00 UTC (wrong).
        """
        entry = {"published": "Mon, 24 Mar 2025 12:00:00 +0300"}
        dt = _parse_date(entry)
        assert dt is not None
        assert dt.tzinfo is not None
        # +0300 means UTC+3 → 12:00 local = 09:00 UTC
        assert dt.hour == 9, f"Expected hour=9 (UTC), got hour={dt.hour}"
        assert dt.day == 24
        assert dt.year == 2025


class TestRSSCacheEviction:
    """Bug 2: RSS cache should evict expired entries and stay bounded."""

    @pytest.mark.asyncio
    async def test_cache_evicts_expired_rss(self):
        """Expired RSS cache entries should be removed on next cache write."""
        fetcher = RSSFetcher(cache_ttl_seconds=300)

        # Insert 3 expired cache entries (fetched_at far in the past)
        old_ts = time.monotonic() - 9999.0  # way beyond 300s TTL
        for i in range(3):
            fetcher._cache[f"https://old.example.com/feed{i}"] = _CacheEntry(
                fetched_at=old_ts,
                records=[
                    RSSItem(
                        title=f"Old item {i}",
                        url=f"https://old.example.com/article{i}",
                    )
                ],
            )

        assert len(fetcher._cache) == 3

        # Trigger a real cache write via fetch_feeds
        mock_response = httpx.Response(
            200,
            text=SAMPLE_RSS,
            request=httpx.Request("GET", "https://example.com/fresh"),
        )
        with patch.object(
            fetcher._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            await fetcher.fetch_feeds(["https://example.com/fresh"], days_back=365 * 10)

        # Expired entries should be gone
        assert "https://old.example.com/feed0" not in fetcher._cache
        assert "https://old.example.com/feed1" not in fetcher._cache
        assert "https://old.example.com/feed2" not in fetcher._cache
        # Fresh entry should be present
        assert "https://example.com/fresh" in fetcher._cache

    @pytest.mark.asyncio
    async def test_cache_bounded_size_rss(self):
        """RSS cache should not exceed _MAX_CACHE_SIZE."""
        fetcher = RSSFetcher(cache_ttl_seconds=300)
        max_size = fetcher._MAX_CACHE_SIZE

        # Fill cache to max with non-expired entries
        now = time.monotonic()
        for i in range(max_size):
            fetcher._cache[f"https://feed{i}.example.com/rss"] = _CacheEntry(
                fetched_at=now,
                records=[],
            )

        assert len(fetcher._cache) == max_size

        # Trigger one more cache write
        mock_response = httpx.Response(
            200,
            text=SAMPLE_RSS,
            request=httpx.Request("GET", "https://example.com/overflow"),
        )
        with patch.object(
            fetcher._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            await fetcher.fetch_feeds(["https://example.com/overflow"], days_back=365 * 10)

        assert len(fetcher._cache) <= max_size
