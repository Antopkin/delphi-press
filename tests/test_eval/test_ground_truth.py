"""Tests for src.eval.ground_truth.

All tests mock httpx responses to avoid real network calls.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.eval.ground_truth import (
    _extract_headlines_from_html,
    _looks_like_headline,
    fetch_headlines_from_wayback,
    fetch_headlines_from_wayback_html,
)

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

    @pytest.mark.asyncio
    async def test_short_window_produces_different_from_to(self) -> None:
        """window_hours=12 should produce date_to > date_from (not same)."""
        captured_urls: list[str] = []

        cdx_response = httpx.Response(
            200,
            json=CDX_RESPONSE_EMPTY,
            request=httpx.Request("GET", "https://web.archive.org/cdx/search/cdx"),
        )

        async def capture_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            captured_urls.append(url)
            return cdx_response

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=capture_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            await fetch_headlines_from_wayback(
                "https://example.com/rss",
                date(2025, 3, 24),
                window_hours=12,
            )

        # The CDX URL should have different from/to timestamps
        cdx_url = captured_urls[0]
        assert "from=20250324000000" in cdx_url
        # With 12h window, date_to should be 20250324120000 (not same day 000000)
        assert "to=20250324120000" in cdx_url


class TestLooksLikeHeadline:
    """Heuristic filter for headline candidates."""

    def test_accepts_real_headline(self) -> None:
        assert _looks_like_headline("Собянин рассказал о тревогах за судьбу Москвы")

    def test_rejects_short_string(self) -> None:
        assert not _looks_like_headline("Кратко")

    def test_rejects_city_section_header(self) -> None:
        assert not _looks_like_headline("Новости Санкт-Петербурга")
        assert not _looks_like_headline("Новости Нижнего Новгорода")
        assert not _looks_like_headline("Новости Екатеринбурга")

    def test_rejects_email(self) -> None:
        assert not _looks_like_headline("internet-group@rian.ru служба")

    def test_rejects_url(self) -> None:
        assert not _looks_like_headline("https://xn--c1acbl2abdlkab1og.xn--p1ai/")

    def test_rejects_nav_label(self) -> None:
        assert not _looks_like_headline("Национальные проекты")
        assert not _looks_like_headline("Кредитные рейтинги")

    def test_rejects_currency_line(self) -> None:
        assert not _looks_like_headline("Курс евро на 30 декабря 2023")

    def test_rejects_rubric_ending_with_year(self) -> None:
        # "Война Израиля с ХАМАС 2023" — topic rubric, not a headline
        assert not _looks_like_headline("Война Израиля с ХАМАС 2023")

    def test_rejects_mostly_digits(self) -> None:
        assert not _looks_like_headline("1234567890 12345 67890")

    def test_accepts_headline_with_number(self) -> None:
        assert _looks_like_headline("В России МРОТ вырос до 19 242 рублей")


class TestExtractHeadlinesFromHtml:
    """Multi-strategy headline extractor."""

    def test_extracts_item_title_spans(self) -> None:
        html = (
            "<html><body>"
            '<div class="main-news">'
            '<a href="/news/1">'
            '<span class="item__title news-feed__item_bold">'
            "Первая важная новость от РБК про экономику"
            "</span></a>"
            '<a href="/news/2">'
            '<span class="item__title">'
            "Вторая новость про политику и международные отношения"
            "</span></a>"
            "</div></body></html>"
        )
        result = _extract_headlines_from_html(html)
        assert any("Первая важная новость" in h for h in result)
        assert any("Вторая новость" in h for h in result)

    def test_deduplicates_duplicate_titles(self) -> None:
        html = """
        <html><body>
        <span class="item__title">Одна и та же новость дня повторяется</span>
        <span class="item__title">Одна и та же новость дня повторяется</span>
        </body></html>
        """
        result = _extract_headlines_from_html(html)
        matches = [h for h in result if "Одна и та же" in h]
        assert len(matches) == 1

    def test_filters_out_nav_items(self) -> None:
        html = """
        <html><body>
        <span class="item__title">Национальные проекты</span>
        <span class="item__title">Реальный заголовок про события в России сегодня</span>
        </body></html>
        """
        result = _extract_headlines_from_html(html)
        assert all("Национальные проекты" != h for h in result)
        assert any("Реальный заголовок" in h for h in result)


class TestFetchHeadlinesFromWaybackHtml:
    """HTML-based fetcher for outlets without archived RSS."""

    @pytest.mark.asyncio
    async def test_no_snapshots_returns_empty(self) -> None:
        """CDX returns only header row -> empty list, no fetch attempted."""
        cdx_response = httpx.Response(
            200,
            json=[["timestamp", "original"]],
            request=httpx.Request("GET", "https://web.archive.org/cdx/search/cdx"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=cdx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback_html(
                "https://tass.ru",
                date(2024, 1, 1),
            )

        assert headlines == []

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback_html(
                "https://tass.ru",
                date(2024, 1, 1),
            )

        assert headlines == []

    @pytest.mark.asyncio
    async def test_extracts_headlines_from_snapshot(self) -> None:
        """Full happy path: CDX -> snapshot -> headlines."""
        cdx_response = httpx.Response(
            200,
            json=[
                ["timestamp", "original"],
                ["20240101001016", "https://tass.ru/"],
            ],
            request=httpx.Request("GET", "https://web.archive.org/cdx/search/cdx"),
        )
        snapshot_html = """
        <html><body>
        <span class="item__title">Первая большая новость дня про политику России</span>
        <span class="item__title">Вторая важная новость про экономику и финансы</span>
        </body></html>
        """
        snapshot_response = httpx.Response(
            200,
            text=snapshot_html,
            request=httpx.Request(
                "GET", "https://web.archive.org/web/20240101001016/https://tass.ru/"
            ),
        )

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "cdx/search/cdx" in url:
                return cdx_response
            return snapshot_response

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.eval.ground_truth.httpx.AsyncClient", return_value=mock_client):
            headlines = await fetch_headlines_from_wayback_html(
                "https://tass.ru",
                date(2024, 1, 1),
            )

        assert any("Первая большая новость" in h for h in headlines)
        assert any("Вторая важная новость" in h for h in headlines)
