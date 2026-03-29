"""Tests for src.data_sources.feed_discovery."""

from unittest.mock import AsyncMock, patch

import httpx

from src.data_sources.feed_discovery import discover_feeds

_PATCH_TARGET = "src.data_sources.feed_discovery.httpx.AsyncClient"


def _make_mock_client(responses: dict[str, httpx.Response]):
    """Mock client: URL → Response mapping."""
    client = AsyncMock()

    async def mock_get(url, **kwargs):
        for pattern, resp in responses.items():
            if pattern in str(url):
                return resp
        return httpx.Response(404, request=httpx.Request("GET", str(url)))

    client.get = mock_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestDiscoverFeeds:
    async def test_from_link_tags(self):
        """Discovers RSS feeds from HTML <link rel='alternate'> tags."""
        html = """
        <html>
        <head>
            <link rel="alternate" type="application/rss+xml" href="/rss/all" title="All">
            <link rel="alternate" type="application/atom+xml" href="https://example.com/atom.xml">
        </head>
        <body></body>
        </html>
        """
        resp = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com"),
            text=html,
            headers={"content-type": "text/html"},
        )
        mock = _make_mock_client({"example.com": resp})

        with patch(_PATCH_TARGET, return_value=mock):
            feeds = await discover_feeds("https://example.com")

        assert len(feeds) >= 2
        assert "https://example.com/rss/all" in feeds
        assert "https://example.com/atom.xml" in feeds

    async def test_from_common_paths(self):
        """Falls back to probing common paths when no link tags found."""
        html_no_feeds = "<html><head><title>News</title></head><body></body></html>"
        homepage_resp = httpx.Response(
            200,
            request=httpx.Request("GET", "https://news.example.com"),
            text=html_no_feeds,
            headers={"content-type": "text/html"},
        )
        rss_resp = httpx.Response(
            200,
            request=httpx.Request("GET", "https://news.example.com/rss.xml"),
            text="<rss></rss>",
            headers={"content-type": "application/rss+xml"},
        )
        responses = {
            "news.example.com/rss.xml": rss_resp,
            "news.example.com": homepage_resp,
        }
        mock = _make_mock_client(responses)

        with patch(_PATCH_TARGET, return_value=mock):
            feeds = await discover_feeds("https://news.example.com")

        assert "https://news.example.com/rss.xml" in feeds

    async def test_all_paths_fail_returns_empty(self):
        """Returns empty list when nothing works."""
        html_no_feeds = "<html><head></head><body></body></html>"
        resp = httpx.Response(
            200,
            request=httpx.Request("GET", "https://dead.example.com"),
            text=html_no_feeds,
            headers={"content-type": "text/html"},
        )
        mock = _make_mock_client({"dead.example.com": resp})

        with patch(_PATCH_TARGET, return_value=mock):
            feeds = await discover_feeds("https://dead.example.com")

        assert feeds == []

    async def test_deduplicates_urls(self):
        """Duplicate feed URLs are removed."""
        html = """
        <html><head>
            <link rel="alternate" type="application/rss+xml" href="/feed">
            <link rel="alternate" type="application/rss+xml" href="/feed">
            <link rel="alternate" type="application/rss+xml" href="https://dup.example.com/feed">
        </head></html>
        """
        resp = httpx.Response(
            200,
            request=httpx.Request("GET", "https://dup.example.com"),
            text=html,
            headers={"content-type": "text/html"},
        )
        mock = _make_mock_client({"dup.example.com": resp})

        with patch(_PATCH_TARGET, return_value=mock):
            feeds = await discover_feeds("https://dup.example.com")

        assert len(feeds) == len(set(feeds)), f"Duplicates found: {feeds}"
