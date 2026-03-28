"""Article scraper — реализация ArticleScraperProto через trafilatura.

Спека: docs/01-data-sources.md (§4).
Контракт: TrafilaturaScraper.scrape_articles(url, days_back=30, max_articles=100)
          → list[ScrapedArticle].

Стек: httpx (async HTTP) + trafilatura (extraction) + robots.txt compliance.
NoopScraper сохранён для тестов и fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from trafilatura.spider import extract_links

from src.agents.collectors.protocols import ScrapedArticle
from src.utils.retry import retry_with_backoff
from src.utils.url_validator import SSRFBlockedError, validate_url_safe

logger = logging.getLogger(__name__)

# robots.txt cache TTL in seconds (1 hour)
_ROBOTS_TTL_SECONDS = 3600.0


class NoopScraper:
    """Заглушка скрейпера — всегда возвращает пустой результат.

    Позволяет зарегистрировать OutletHistorian в registry,
    но он вернёт пустой профиль и пайплайн продолжит (min_successful=2).
    """

    async def scrape_articles(
        self,
        url: str,
        *,
        days_back: int = 30,
        max_articles: int = 100,
    ) -> list[ScrapedArticle]:
        """Return empty list — scraper not yet implemented."""
        logger.info("NoopScraper called for %s (not implemented yet)", url)
        return []


class TrafilaturaScraper:
    """Article scraper using httpx + trafilatura.

    Implements ArticleScraperProto. Respects robots.txt, applies per-domain
    rate limiting, and extracts article content via trafilatura.

    The ``url`` parameter can be either a single article URL or an
    archive/index page. For index pages the scraper discovers article links
    via trafilatura's ``extract_links`` and then fetches each individually.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 5,
        delay_range: tuple[float, float] = (1.0, 3.0),
        timeout_seconds: float = 30.0,
        user_agent: str = "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)",
    ) -> None:
        self._max_concurrent = max_concurrent
        self._delay_range = delay_range
        self._timeout = timeout_seconds
        self._user_agent = user_agent

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

        # Per-domain rate limiting: one request at a time per domain
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        # Global concurrency limiter across all domains
        self._global_semaphore = asyncio.Semaphore(max_concurrent)
        # robots.txt cache: domain -> (fetched_at_monotonic, RobotFileParser)
        self._robots_cache: dict[str, tuple[float, RobotFileParser]] = {}

    async def scrape_articles(
        self,
        url: str,
        *,
        days_back: int = 30,
        max_articles: int = 100,
    ) -> list[ScrapedArticle]:
        """Scrape articles from a URL.

        Args:
            url: Single article URL or archive/index page URL.
            days_back: Only return articles published within this many days.
            max_articles: Maximum number of articles to return.

        Returns:
            List of ScrapedArticle. Empty list on any error (never raises).
        """
        try:
            return await self._scrape_impl(url, days_back=days_back, max_articles=max_articles)
        except Exception as exc:
            logger.warning("Unexpected error scraping %s: %s", url, exc)
            return []

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _scrape_impl(
        self,
        url: str,
        *,
        days_back: int,
        max_articles: int,
    ) -> list[ScrapedArticle]:
        """Core scraping logic: fetch, detect page type, extract articles."""
        # Check robots.txt
        if not await self._is_allowed(url):
            logger.info("robots.txt disallows scraping %s", url)
            return []

        # Fetch the page
        html = await self._fetch_page(url)
        if html is None:
            return []

        # Try to extract as a single article first
        article = await self._extract_single_article(html, url, days_back)
        if article is not None:
            return [article]

        # If extraction returned nothing useful, treat as index page:
        # discover article links and fetch each one.
        return await self._scrape_index_page(
            html, url, days_back=days_back, max_articles=max_articles
        )

    async def _fetch_page(self, url: str) -> str | None:
        """Fetch a single page with rate limiting. Returns HTML or None."""
        try:
            validate_url_safe(url)
        except SSRFBlockedError as exc:
            logger.warning("SSRF blocked: %s", exc)
            return None

        domain = urlparse(url).hostname or ""
        domain_sem = self._domain_semaphores.setdefault(domain, asyncio.Semaphore(1))

        async with self._global_semaphore:
            async with domain_sem:
                # Polite delay before each request
                await asyncio.sleep(random.uniform(*self._delay_range))
                try:

                    async def _do_fetch() -> httpx.Response:
                        resp = await self._client.get(url)
                        resp.raise_for_status()
                        return resp

                    response = await retry_with_backoff(_do_fetch, max_retries=2, base_delay=2.0)
                    return response.text
                except httpx.TimeoutException:
                    logger.warning("Timeout fetching %s", url)
                    return None
                except httpx.HTTPError as exc:
                    logger.warning("HTTP error fetching %s: %s", url, exc)
                    return None

    async def _extract_single_article(
        self,
        html: str,
        url: str,
        days_back: int,
    ) -> ScrapedArticle | None:
        """Extract a single article from HTML via trafilatura.

        Returns None if extraction fails or the page doesn't look like an article.
        """
        raw_json = await asyncio.to_thread(
            trafilatura.extract,
            html,
            url=url,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        if raw_json is None:
            return None

        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse trafilatura JSON for %s", url)
            return None

        title = (data.get("title") or "").strip()
        if not title:
            return None

        text = (data.get("text") or "").strip()
        first_paragraph = text[:500] if text else ""

        # Parse date
        published_at = _parse_trafilatura_date(data.get("date"))
        if published_at is not None:
            cutoff = datetime.now(UTC) - timedelta(days=days_back)
            if published_at < cutoff:
                return None

        # Parse categories / tags
        categories = _parse_categories(data.get("categories") or data.get("tags"))

        return ScrapedArticle(
            headline=title,
            first_paragraph=first_paragraph,
            url=url,
            published_at=published_at,
            categories=categories,
        )

    async def _scrape_index_page(
        self,
        html: str,
        index_url: str,
        *,
        days_back: int,
        max_articles: int,
    ) -> list[ScrapedArticle]:
        """Discover article links from an index page and scrape each."""
        # Use trafilatura to extract internal links
        links = await asyncio.to_thread(
            extract_links,
            html,
            url=index_url,
            external_bool=False,
            no_filter=False,
            with_nav=False,
        )
        if not links:
            return []

        # Limit to max_articles candidate links
        link_list = list(links)[: max_articles * 2]  # fetch extra in case some fail

        articles: list[ScrapedArticle] = []
        for link_url in link_list:
            if len(articles) >= max_articles:
                break

            if not await self._is_allowed(link_url):
                continue

            page_html = await self._fetch_page(link_url)
            if page_html is None:
                continue

            article = await self._extract_single_article(page_html, link_url, days_back)
            if article is not None:
                articles.append(article)

        return articles

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    async def _is_allowed(self, url: str) -> bool:
        """Check whether the URL is allowed by robots.txt.

        Caches parsed robots.txt per domain for 1 hour.
        On any error fetching robots.txt, defaults to allowed.
        """
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"

        now = time.monotonic()
        cached = self._robots_cache.get(domain)
        if cached is not None:
            fetched_at, rp = cached
            if (now - fetched_at) < _ROBOTS_TTL_SECONDS:
                return rp.can_fetch(self._user_agent, url)

        # Fetch and parse robots.txt
        rp = RobotFileParser()
        try:
            response = await self._client.get(robots_url)
            if response.status_code == 200:
                # RobotFileParser.parse() expects a list of lines
                lines = response.text.splitlines()
                rp.parse(lines)
            else:
                # No robots.txt → everything allowed
                rp.allow_all = True
        except (httpx.HTTPError, httpx.TimeoutException):
            # Can't fetch robots.txt → assume allowed
            rp.allow_all = True

        self._robots_cache[domain] = (now, rp)
        return rp.can_fetch(self._user_agent, url)


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _parse_trafilatura_date(raw: str | None) -> datetime | None:
    """Parse date string from trafilatura metadata (typically YYYY-MM-DD)."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    # Trafilatura often returns YYYY-MM-DD without timezone
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    return None


def _parse_categories(raw: str | list[str] | None) -> list[str]:
    """Parse categories from trafilatura metadata.

    Trafilatura may return categories as a semicolon-separated string
    or as a list.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [c.strip() for c in raw if c.strip()]
    if isinstance(raw, str):
        return [c.strip() for c in raw.split(";") if c.strip()]
    return []
