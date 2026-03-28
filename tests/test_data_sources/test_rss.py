"""Tests for src.data_sources.rss."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.data_sources.rss import RSSFetcher, _clean_text, _parse_date

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
