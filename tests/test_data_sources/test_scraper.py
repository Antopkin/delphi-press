"""Tests for src.data_sources.scraper — TrafilaturaScraper and NoopScraper."""

import json
from unittest.mock import patch

import httpx
import pytest

from src.agents.collectors.protocols import ScrapedArticle
from src.data_sources.scraper import (
    NoopScraper,
    TrafilaturaScraper,
    _parse_categories,
    _parse_trafilatura_date,
)

# Sample HTML that trafilatura can (in mocked form) process
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<article>
<h1>Breaking: Major Policy Change Announced</h1>
<p>The government today announced sweeping changes to economic policy
that will affect millions of citizens across the country.</p>
<p>Experts weigh in on the implications of these changes.</p>
</article>
</body>
</html>
"""

SAMPLE_INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>News Archive</title></head>
<body>
<div class="articles">
<a href="https://example.com/article/1">Article One</a>
<a href="https://example.com/article/2">Article Two</a>
<a href="https://example.com/article/3">Article Three</a>
</div>
</body>
</html>
"""

# JSON output from trafilatura.extract() with output_format="json"
SAMPLE_TRAFILATURA_JSON = json.dumps(
    {
        "title": "Breaking: Major Policy Change Announced",
        "text": (
            "The government today announced sweeping changes to economic policy "
            "that will affect millions of citizens across the country. "
            "Experts weigh in on the implications of these changes."
        ),
        "date": "2026-03-25",
        "categories": "Politics;Economy",
        "url": "https://example.com/article/1",
    }
)

ROBOTS_TXT_ALLOW_ALL = """User-agent: *
Allow: /
"""

ROBOTS_TXT_DISALLOW_ALL = """User-agent: *
Disallow: /
"""


@pytest.fixture
def scraper() -> TrafilaturaScraper:
    return TrafilaturaScraper(
        max_concurrent=2,
        delay_range=(0.0, 0.0),  # no delay in tests
        timeout_seconds=5.0,
    )


def _mock_robots_response(text: str = ROBOTS_TXT_ALLOW_ALL) -> httpx.Response:
    """Build a mock httpx.Response for robots.txt."""
    return httpx.Response(
        200,
        text=text,
        request=httpx.Request("GET", "https://example.com/robots.txt"),
    )


def _mock_html_response(
    html: str = SAMPLE_HTML,
    url: str = "https://example.com/article/1",
    status_code: int = 200,
) -> httpx.Response:
    """Build a mock httpx.Response for an HTML page."""
    return httpx.Response(
        status_code,
        text=html,
        request=httpx.Request("GET", url),
    )


class TestTrafilatureScraperSatisfiesProtocol:
    def test_structural_subtyping(self) -> None:
        """TrafilaturaScraper must satisfy ArticleScraperProto structurally."""
        scraper = TrafilaturaScraper(delay_range=(0.0, 0.0))
        # Protocol check: the object must have a scrape_articles method
        # with the correct signature. runtime_checkable Protocol.
        assert hasattr(scraper, "scrape_articles")
        assert callable(scraper.scrape_articles)

    def test_noop_scraper_also_satisfies_protocol(self) -> None:
        """NoopScraper must also satisfy ArticleScraperProto."""
        noop = NoopScraper()
        assert hasattr(noop, "scrape_articles")
        assert callable(noop.scrape_articles)


class TestScrapeSingleArticle:
    @pytest.mark.asyncio
    async def test_single_article_extraction(self, scraper: TrafilaturaScraper) -> None:
        """Mock httpx + trafilatura: verify ScrapedArticle output."""
        call_count = 0

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if "robots.txt" in url:
                return _mock_robots_response()
            return _mock_html_response()

        with (
            patch.object(scraper._client, "get", side_effect=mock_get),
            patch(
                "src.data_sources.scraper.trafilatura.extract",
                return_value=SAMPLE_TRAFILATURA_JSON,
            ),
        ):
            articles = await scraper.scrape_articles(
                "https://example.com/article/1",
                days_back=30,
                max_articles=10,
            )

        assert len(articles) == 1
        art = articles[0]
        assert isinstance(art, ScrapedArticle)
        assert art.headline == "Breaking: Major Policy Change Announced"
        assert "sweeping changes" in art.first_paragraph
        assert art.url == "https://example.com/article/1"
        assert art.published_at is not None
        assert art.published_at.year == 2026
        assert "Politics" in art.categories
        assert "Economy" in art.categories

    @pytest.mark.asyncio
    async def test_trafilatura_returns_none(self, scraper: TrafilaturaScraper) -> None:
        """When trafilatura.extract returns None, scrape_articles returns []."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                return _mock_robots_response()
            return _mock_html_response()

        with (
            patch.object(scraper._client, "get", side_effect=mock_get),
            patch("src.data_sources.scraper.trafilatura.extract", return_value=None),
            patch(
                "src.data_sources.scraper.extract_links",
                return_value=set(),
            ),
        ):
            articles = await scraper.scrape_articles("https://example.com/article/1")

        assert articles == []


class TestRobotsTxtDisallowed:
    @pytest.mark.asyncio
    async def test_disallowed_returns_empty(self, scraper: TrafilaturaScraper) -> None:
        """If robots.txt disallows the URL, return empty list."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                return _mock_robots_response(ROBOTS_TXT_DISALLOW_ALL)
            return _mock_html_response()

        with patch.object(scraper._client, "get", side_effect=mock_get):
            articles = await scraper.scrape_articles("https://example.com/article/1")

        assert articles == []

    @pytest.mark.asyncio
    async def test_robots_fetch_failure_allows(self, scraper: TrafilaturaScraper) -> None:
        """If robots.txt fetch fails, default to allowed and proceed."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                raise httpx.ConnectError("Connection refused")
            return _mock_html_response()

        with (
            patch.object(scraper._client, "get", side_effect=mock_get),
            patch(
                "src.data_sources.scraper.trafilatura.extract",
                return_value=SAMPLE_TRAFILATURA_JSON,
            ),
        ):
            articles = await scraper.scrape_articles(
                "https://example.com/article/1",
                days_back=30,
            )

        assert len(articles) == 1


class TestHTTPErrorReturnsEmpty:
    @pytest.mark.asyncio
    async def test_http_500_returns_empty(self, scraper: TrafilaturaScraper) -> None:
        """HTTP 500 should return empty list."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                return _mock_robots_response()
            return _mock_html_response(status_code=500)

        with patch.object(scraper._client, "get", side_effect=mock_get):
            articles = await scraper.scrape_articles("https://example.com/article/1")

        assert articles == []

    @pytest.mark.asyncio
    async def test_http_404_returns_empty(self, scraper: TrafilaturaScraper) -> None:
        """HTTP 404 should return empty list."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                return _mock_robots_response()
            return _mock_html_response(status_code=404)

        with patch.object(scraper._client, "get", side_effect=mock_get):
            articles = await scraper.scrape_articles("https://example.com/article/1")

        assert articles == []


class TestTimeoutReturnsEmpty:
    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self, scraper: TrafilaturaScraper) -> None:
        """httpx.TimeoutException should return empty list."""

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            if "robots.txt" in url:
                return _mock_robots_response()
            raise httpx.ReadTimeout("Read timed out")

        with patch.object(scraper._client, "get", side_effect=mock_get):
            articles = await scraper.scrape_articles("https://example.com/article/1")

        assert articles == []


class TestNoopScraper:
    @pytest.mark.asyncio
    async def test_returns_empty(self) -> None:
        """NoopScraper always returns empty list for backward compat."""
        noop = NoopScraper()
        articles = await noop.scrape_articles("https://example.com", days_back=7)
        assert articles == []


class TestIndexPageScraping:
    @pytest.mark.asyncio
    async def test_index_page_discovers_links(self, scraper: TrafilaturaScraper) -> None:
        """When first extraction yields nothing, discover links and scrape each."""
        call_count = 0

        async def mock_get(url: str, **kwargs) -> httpx.Response:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if "robots.txt" in url:
                return _mock_robots_response()
            if url == "https://example.com/news":
                return _mock_html_response(html=SAMPLE_INDEX_HTML, url=url)
            # Individual article pages
            return _mock_html_response(url=url)

        extract_call_count = 0

        def mock_extract(html, **kwargs):  # noqa: ARG001
            nonlocal extract_call_count
            extract_call_count += 1
            if extract_call_count == 1:
                # First call is the index page → return None (not an article)
                return None
            # Subsequent calls are individual articles
            return json.dumps(
                {
                    "title": f"Article {extract_call_count - 1}",
                    "text": "Some article content here.",
                    "date": "2026-03-26",
                    "categories": "News",
                }
            )

        discovered_links = {
            "https://example.com/article/1",
            "https://example.com/article/2",
        }

        with (
            patch.object(scraper._client, "get", side_effect=mock_get),
            patch("src.data_sources.scraper.trafilatura.extract", side_effect=mock_extract),
            patch(
                "src.data_sources.scraper.extract_links",
                return_value=discovered_links,
            ),
        ):
            articles = await scraper.scrape_articles(
                "https://example.com/news",
                days_back=30,
                max_articles=5,
            )

        assert len(articles) == 2
        assert all(isinstance(a, ScrapedArticle) for a in articles)


class TestHelpers:
    def test_parse_date_iso(self) -> None:
        dt = _parse_trafilatura_date("2026-03-25T12:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 25

    def test_parse_date_ymd(self) -> None:
        dt = _parse_trafilatura_date("2026-03-25")
        assert dt is not None
        assert dt.year == 2026

    def test_parse_date_none(self) -> None:
        assert _parse_trafilatura_date(None) is None

    def test_parse_date_empty(self) -> None:
        assert _parse_trafilatura_date("") is None

    def test_parse_date_garbage(self) -> None:
        assert _parse_trafilatura_date("not-a-date") is None

    def test_parse_categories_string(self) -> None:
        assert _parse_categories("Politics;Economy;Tech") == ["Politics", "Economy", "Tech"]

    def test_parse_categories_list(self) -> None:
        assert _parse_categories(["Politics", "Economy"]) == ["Politics", "Economy"]

    def test_parse_categories_none(self) -> None:
        assert _parse_categories(None) == []

    def test_parse_categories_empty_string(self) -> None:
        assert _parse_categories("") == []

    def test_parse_categories_strips_whitespace(self) -> None:
        assert _parse_categories(" Politics ; Economy ") == ["Politics", "Economy"]


class TestClose:
    @pytest.mark.asyncio
    async def test_close_does_not_raise(self, scraper: TrafilaturaScraper) -> None:
        """close() should cleanly close the HTTP client."""
        await scraper.close()
