"""Ground truth fetcher using Wayback Machine CDX API.

Pipeline stage: Evaluation (data collection).
Spec: tasks/research/retrospective_testing.md SS Datasets.
Contract: (rss_url, target_date) -> list[str] of actual headlines.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

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
        date_from = target_date.strftime("%Y%m%d000000")
        next_day = target_date + timedelta(hours=window_hours)
        date_to = next_day.strftime("%Y%m%d000000")

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
