"""Ground truth fetcher using Wayback Machine CDX API.

Pipeline stage: Evaluation (data collection).
Spec: docs-site/docs/evaluation/metrics.md SS Datasets.

Two entry points:
    fetch_headlines_from_wayback(rss_url, target_date)
        Legacy RSS-based fetcher. Works for outlets whose RSS feeds are
        archived by the Wayback Machine (notably missing for ru-lang outlets).
    fetch_headlines_from_wayback_html(homepage_url, target_date)
        HTML-based fetcher for outlets whose RSS feeds are not archived but
        whose homepages are. Uses trafilatura + regex fallbacks. Covers ТАСС,
        РИА, РБК where RSS feeds yield zero snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import httpx
import trafilatura

logger = logging.getLogger(__name__)

_CDX_BASE = "https://web.archive.org/cdx/search/cdx"
_WAYBACK_BASE = "https://web.archive.org/web"


async def fetch_headlines_from_wayback(
    rss_url: str,
    target_date: date,
    *,
    window_hours: int = 24,
) -> list[str]:
    """Fetch actual headlines from Wayback Machine RSS snapshots.

    Queries the CDX API for archived RSS snapshots within a time window
    around the target date, then extracts <title> elements from each
    snapshot's XML.

    Args:
        rss_url: RSS feed URL to look up in Wayback Machine.
        target_date: Date to fetch headlines for.
        window_hours: Time window size in hours (default 24).

    Returns:
        Deduplicated list of headline strings. Empty list on any error.
    """
    try:
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(hours=window_hours)
        date_from = start_dt.strftime("%Y%m%d%H%M%S")
        date_to = end_dt.strftime("%Y%m%d%H%M%S")

        cdx_url = (
            f"{_CDX_BASE}?url={rss_url}&output=json"
            f"&from={date_from}&to={date_to}"
            f"&fl=timestamp,original&statuscode=200&limit=5"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            cdx_resp = await client.get(cdx_url)
            cdx_resp.raise_for_status()
            rows = cdx_resp.json()

            # First row is header ["timestamp", "original"], skip it
            snapshots = rows[1:] if len(rows) > 1 else []
            if not snapshots:
                return []

            headlines: list[str] = []
            for i, (timestamp, original_url) in enumerate(snapshots):
                if i > 0:
                    await asyncio.sleep(1.0)  # Politeness delay

                snapshot_url = f"{_WAYBACK_BASE}/{timestamp}/{original_url}"
                snap_resp = await client.get(snapshot_url)
                snap_resp.raise_for_status()

                titles = _extract_titles_from_rss(snap_resp.text)
                headlines.extend(titles)

            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for h in headlines:
                if h not in seen:
                    seen.add(h)
                    unique.append(h)
            return unique

    except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
        logger.warning("Failed to fetch headlines from Wayback: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Unexpected error fetching Wayback headlines: %s", exc)
        return []


def _extract_titles_from_rss(xml_text: str) -> list[str]:
    """Extract <title> text from RSS XML items.

    Args:
        xml_text: Raw RSS XML content.

    Returns:
        List of title strings from <item><title> elements.
    """
    root = ET.fromstring(xml_text)
    titles: list[str] = []
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            titles.append(title_el.text.strip())
    return titles


# --- HTML homepage fetcher --------------------------------------------------

# Regex patterns for RBC-style markup where trafilatura fails to pick up the
# news feed. Each pattern captures one headline per match. Order matters:
# more specific patterns are tried first.
_HTML_HEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # RBC: <span class="item__title ..."> ... </span>
    re.compile(
        r'<span[^>]*class="[^"]*item__title[^"]*"[^>]*>([^<]{10,250})</span>',
        re.IGNORECASE,
    ),
    # Generic headline anchors: <a class="...title..."> ... </a>
    re.compile(
        r'<a[^>]*class="[^"]*(?:headline|article-title|news-title|card-title)[^"]*"[^>]*>([^<]{10,250})</a>',
        re.IGNORECASE,
    ),
)

# Noise filter — strings we never want as "headlines"
_NOISE_SUBSTRINGS: tuple[str, ...] = (
    "cookie",
    "javascript",
    "web.archive.org",
    "Перейти",
    "подписаться",
    "рубрик",
    "все новости",
    "Загрузить",
    "Курс евро",
    "Курс доллара",
    "Нефть Brent",
    # Site chrome / navigation labels
    "Ваше местоположение",
    "Новая версия",
    "Национальные проекты",
    "Дискуссионный клуб",
    "Кредитные рейтинги",
    "Спецпроекты",
    "Проверка контрагентов",
    "Конференции",
    "Технологии и медиа",
    "Мероприятия",
    # РИА footer
    "ФГУП",
    "internet-group",
    "Отправить еще",
    "Регистрация пройдена",
    "Пожалуйста, перейдите",
    "Ошибка воспроизведения",
    # Advertising
    "Подарите себе",
    "со скидкой",
    "Купить со скидкой",
    "Весь РБК Pro",
)

# Regex ban: city-section headers like "Новости Екатеринбурга",
# "Новости Санкт-Петербурга", "Новости Нижнего Новгорода"
# Matches "Новости" followed by 1-3 cyrillic words (possibly hyphenated).
_CITY_SECTION_RE = re.compile(
    r"^Новости\s+(?:[А-ЯA-Z][а-яa-zА-ЯA-Z\-]*)(?:\s+[А-ЯA-Z][а-яa-zА-ЯA-Z\-]*){0,2}$"
)

# Regex ban: rubric-style labels that end in a year (e.g. "Война в ХАМАС 2023")
_RUBRIC_YEAR_RE = re.compile(r"^[^.!?]{5,45}\s20[12]\d$")

# Regex ban: URL / email lines
_URL_RE = re.compile(r"^https?://|^[\w.+-]+@[\w.-]+\.\w+")


def _looks_like_headline(text: str) -> bool:
    """Heuristic: does this string look like a news headline?

    Rejects: nav items, currency quotes, short labels, URLs, emails,
    section headers ("Новости Екатеринбурга"), numeric-only strings.
    """
    s = text.strip()
    if len(s) < 20 or len(s) > 300:
        return False
    if any(noise.lower() in s.lower() for noise in _NOISE_SUBSTRINGS):
        return False
    if _URL_RE.search(s):
        return False
    if _CITY_SECTION_RE.match(s):
        return False
    if _RUBRIC_YEAR_RE.match(s):
        return False
    # Reject very short "rubric-like" strings: ≤4 words and no verb-like ending
    word_count = len(s.split())
    if word_count <= 4 and not any(s.endswith(p) for p in (".", "!", "?")):
        return False
    # Must contain at least a few cyrillic or latin letters
    letter_count = sum(1 for c in s if c.isalpha())
    if letter_count < 12:
        return False
    # Reject if mostly digits
    digit_ratio = sum(1 for c in s if c.isdigit()) / max(len(s), 1)
    if digit_ratio > 0.3:
        return False
    # Must contain at least one space (single words are never headlines)
    if " " not in s:
        return False
    return True


def _extract_headlines_from_html(html: str) -> list[str]:
    """Extract headlines from an archived homepage HTML snapshot.

    Strategy:
        1. Run trafilatura's text extractor (catches SSR headlines on ТАСС, РИА).
        2. Run regex fallbacks for outlets where trafilatura fails (РБК's
           item__title spans, generic headline anchors).
        3. Merge, deduplicate, filter via _looks_like_headline.

    Args:
        html: Raw HTML string (Wayback snapshot).

    Returns:
        Ordered deduplicated list of candidate headlines.
    """
    candidates: list[str] = []

    # Strategy 1: trafilatura
    try:
        extracted = trafilatura.extract(
            html,
            include_links=False,
            include_tables=False,
            favor_recall=True,
            no_fallback=False,
        )
        if extracted:
            for line in extracted.split("\n"):
                candidates.append(line.strip())
    except Exception as exc:  # noqa: BLE001  — extraction is best-effort
        logger.debug("trafilatura extract failed: %s", exc)

    # Strategy 2: regex fallback patterns
    for pattern in _HTML_HEADLINE_PATTERNS:
        for match in pattern.findall(html):
            candidates.append(match.strip())

    # Deduplicate while preserving order + filter
    seen: set[str] = set()
    result: list[str] = []
    for raw in candidates:
        if not _looks_like_headline(raw):
            continue
        normalized = " ".join(raw.split())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


async def fetch_headlines_from_wayback_html(
    homepage_url: str,
    target_date: date,
    *,
    window_hours: int = 24,
    max_snapshots: int = 3,
) -> list[str]:
    """Fetch actual headlines from Wayback HTML homepage snapshots.

    Use this when the outlet's RSS feed is not archived by the Wayback Machine
    (common for Russian-language outlets such as ТАСС, РИА, РБК). The function
    queries CDX for homepage snapshots within a window, downloads up to
    ``max_snapshots`` of them, and extracts candidate headlines via a hybrid
    trafilatura + regex pipeline.

    Args:
        homepage_url: Outlet homepage URL (e.g. "https://tass.ru").
        target_date: Date to fetch headlines for.
        window_hours: Time window size in hours (default 24).
        max_snapshots: Maximum number of snapshots to download (default 3,
            to stay polite to the Wayback Machine).

    Returns:
        Deduplicated list of headline strings. Empty list on any error.
    """
    try:
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(hours=window_hours)
        date_from = start_dt.strftime("%Y%m%d%H%M%S")
        date_to = end_dt.strftime("%Y%m%d%H%M%S")

        cdx_url = (
            f"{_CDX_BASE}?url={homepage_url}&output=json"
            f"&from={date_from}&to={date_to}"
            f"&fl=timestamp,original&statuscode=200&limit={max_snapshots}"
        )

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            cdx_resp = await client.get(cdx_url)
            cdx_resp.raise_for_status()
            rows = cdx_resp.json()

            snapshots = rows[1:] if len(rows) > 1 else []
            if not snapshots:
                logger.info(
                    "No Wayback HTML snapshots for %s on %s",
                    homepage_url,
                    target_date.isoformat(),
                )
                return []

            all_headlines: list[str] = []
            for i, (timestamp, original_url) in enumerate(snapshots):
                if i > 0:
                    await asyncio.sleep(2.0)  # Politeness delay

                snapshot_url = f"{_WAYBACK_BASE}/{timestamp}/{original_url}"
                try:
                    snap_resp = await client.get(snapshot_url)
                    snap_resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.debug("Snapshot fetch failed for %s: %s", snapshot_url, exc)
                    continue

                headlines = _extract_headlines_from_html(snap_resp.text)
                all_headlines.extend(headlines)

            # Deduplicate across snapshots while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for h in all_headlines:
                if h not in seen:
                    seen.add(h)
                    unique.append(h)
            return unique

    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Failed to fetch HTML headlines from Wayback: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching Wayback HTML headlines: %s", exc)
        return []
