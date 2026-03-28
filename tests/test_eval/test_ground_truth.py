"""Tests for src.eval.ground_truth.

All tests mock httpx responses to avoid real network calls.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.eval.ground_truth import fetch_headlines_from_wayback

CDX_RESPONSE_WITH_SNAPSHOT = [
    ["timestamp", "original"],
    ["20250324120000", "https://example.com/rss"],
]

CDX_RESPONSE_EMPTY = [
    ["timestamp", "original"],
]

RSS_BODY = """\
<?xml version="1.0"?>
<rss><channel>
  <item><title>Headline One</title></item>
  <item><title>Headline Two</title></item>
</channel></rss>
"""


class TestFetchHeadlinesFromWayback:
    """Ground truth fetcher via Wayback Machine CDX API."""

    @pytest.mark.asyncio
    async def test_fetch_wayback_success(self) -> None:
        """Mock CDX + RSS: returns 2 headlines from one snapshot."""
        cdx_response = httpx.Response(
            200,
            json=CDX_RESPONSE_WITH_SNAPSHOT,
            request=httpx.Request("GET", "https://web.archive.org/cdx/search/cdx"),
        )
        rss_response = httpx.Response(
            200,
            text=RSS_BODY,
            request=httpx.Request(
                "GET",
                "https://web.archive.org/web/20250324120000/https://example.com/rss",
            ),
        )

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "cdx/search/cdx" in url:
                return cdx_response
            return rss_response

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback(
                "https://example.com/rss",
                date(2025, 3, 24),
            )

        assert len(headlines) == 2
        assert "Headline One" in headlines
        assert "Headline Two" in headlines

    @pytest.mark.asyncio
    async def test_fetch_wayback_no_snapshots(self) -> None:
        """CDX returns only header row (no snapshots) -> empty list."""
        cdx_response = httpx.Response(
            200,
            json=CDX_RESPONSE_EMPTY,
            request=httpx.Request("GET", "https://web.archive.org/cdx/search/cdx"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=cdx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback(
                "https://example.com/rss",
                date(2025, 3, 24),
            )

        assert headlines == []

    @pytest.mark.asyncio
    async def test_fetch_wayback_http_error(self) -> None:
        """Network error returns empty list (no exception propagation)."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback(
                "https://example.com/rss",
                date(2025, 3, 24),
            )

        assert headlines == []
