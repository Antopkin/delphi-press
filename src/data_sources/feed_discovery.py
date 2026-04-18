"""RSS feed autodiscovery for media outlets.

Спека: docs-site/docs/data-collection/stages-1-2.md (outlet catalog enrichment).
Контракт: website URL → list[str] of RSS/Atom feed URLs.

Two-pass strategy:
  1. Parse <link rel="alternate"> tags from homepage HTML
  2. Probe common feed paths (/feed, /rss.xml, etc.) in parallel
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 8

COMMON_FEED_PATHS = [
    "/feed",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/rss",
    "/rss/",
    "/feeds/posts/default",
    "/feed/rss2.xml",
    "/index.xml",
    "/rss/all",
    "/?feed=rss2",
]

_LINK_TAG_RE = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_TYPE_RE = re.compile(r'type=["\']([^"\']+)["\']', re.IGNORECASE)

_FEED_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "application/feed+json"}


def _extract_feed_urls_from_html(html: str, base_url: str) -> list[str]:
    """Extract RSS/Atom feed URLs from HTML <link> tags."""
    feeds: list[str] = []
    for tag_match in _LINK_TAG_RE.finditer(html):
        tag = tag_match.group(0)
        type_match = _TYPE_RE.search(tag)
        if not type_match:
            continue
        content_type = type_match.group(1).strip()
        if content_type not in _FEED_CONTENT_TYPES:
            continue
        href_match = _HREF_RE.search(tag)
        if not href_match:
            continue
        href = href_match.group(1).strip()
        full_url = href if href.startswith("http") else urljoin(base_url.rstrip("/") + "/", href)
        feeds.append(full_url)
    return feeds


async def _probe_feed_path(client: httpx.AsyncClient, url: str) -> str | None:
    """Check if a URL returns RSS/Atom content."""
    try:
        resp = await client.get(url)
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and any(x in ct for x in ("xml", "rss", "atom", "feed")):
            return url
    except httpx.HTTPError:
        pass
    return None


async def discover_feeds(base_url: str) -> list[str]:
    """Discover RSS/Atom feeds for a website.

    Pass 1: parse <link rel="alternate"> from homepage HTML.
    Pass 2: probe common feed paths in parallel (only if pass 1 finds nothing).

    Returns list of feed URLs (may be empty).
    """
    base_url = base_url.rstrip("/")
    feeds: list[str] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (DelphiPress/1.0)"},
    ) as client:
        # Pass 1: HTML link tags
        try:
            resp = await client.get(base_url)
            if resp.status_code == 200:
                feeds = _extract_feed_urls_from_html(resp.text, base_url)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch %s: %s", base_url, exc)

        if feeds:
            return list(dict.fromkeys(feeds))  # deduplicate, preserve order

        # Pass 2: probe common paths
        probe_urls = [f"{base_url}{path}" for path in COMMON_FEED_PATHS]
        results = await asyncio.gather(
            *[_probe_feed_path(client, url) for url in probe_urls],
            return_exceptions=True,
        )
        feeds = [r for r in results if isinstance(r, str)]

    return list(dict.fromkeys(feeds))
