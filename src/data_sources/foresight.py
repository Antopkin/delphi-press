"""Форсайт-центры -- клиенты Metaculus, Polymarket, GDELT.

Стадия: Stage 1 (сбор данных).
Спека: docs/01-data-sources.md.
Контракт: каждый клиент возвращает list[dict], маппинг в Pydantic-схемы
          делает ForesightCollector (src/agents/collectors/foresight_collector.py).

Все три API публичные -- авторизация не требуется.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)"


class MetaculusClient:
    """Metaculus crowd probability API.

    Endpoint: GET https://www.metaculus.com/api2/questions/
    No auth required. Cache TTL: 30 min.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": _USER_AGENT},
        )
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._cache_ttl = 1800  # 30 min

    async def fetch_questions(
        self,
        query: str = "",
        *,
        resolve_days_ahead: int = 14,
        limit: int = 100,
        min_forecasters: int = 10,
        status: str = "open",
    ) -> list[dict]:
        """Fetch open binary questions resolving within resolve_days_ahead.

        Returns:
            List of dicts with keys: id, title, url, q2 (median probability),
            q1, q3, resolve_time, categories, number_of_forecasters.
            Filters out questions with < min_forecasters.
        """
        cache_key = f"metaculus:{resolve_days_ahead}:{limit}:{min_forecasters}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        now = datetime.now(UTC)
        resolve_gt = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        resolve_lt = (now + timedelta(days=resolve_days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "status": "open",
            "forecast_type": "binary",
            "resolve_time__gt": resolve_gt,
            "resolve_time__lt": resolve_lt,
            "order_by": "-activity",
            "limit": limit,
            "include_description": "false",
        }

        try:
            response = await self._client.get(
                "https://www.metaculus.com/api2/questions/",
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Metaculus API failed: %s", exc)
            return []

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Metaculus response parse error: %s", exc)
            return []

        results: list[dict] = []
        for q in data.get("results", []):
            cp = q.get("community_prediction")
            if cp is None:
                continue

            forecasters = q.get("number_of_forecasters", 0)
            if forecasters < min_forecasters:
                continue

            full = cp.get("full", {})
            results.append(
                {
                    "id": q.get("id"),
                    "title": q.get("title", ""),
                    "url": q.get("url", ""),
                    "q2": full.get("q2"),
                    "q1": full.get("q1"),
                    "q3": full.get("q3"),
                    "resolve_time": q.get("resolve_time"),
                    "categories": [c.get("name", "") for c in q.get("categories", [])],
                    "number_of_forecasters": forecasters,
                }
            )

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


class PolymarketClient:
    """Polymarket prediction market API.

    Endpoint: GET https://gamma-api.polymarket.com/markets
    No auth required. Cache TTL: 15 min.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://gamma-api.polymarket.com",
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": _USER_AGENT},
        )
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._cache_ttl = 900  # 15 min

    async def fetch_markets(
        self,
        query: str = "",
        *,
        limit: int = 100,
        min_liquidity: float = 5000.0,
        end_date_days_ahead: int = 30,
    ) -> list[dict]:
        """Fetch active markets with sufficient liquidity.

        Returns:
            List of dicts with keys: id, question, slug, description,
            yes_probability (float), volume, liquidity, end_date, categories.

        Note:
            outcomePrices is a JSON-stringified string, not an array.
            Must json.loads() before float().
        """
        cache_key = f"polymarket:{limit}:{min_liquidity}:{end_date_days_ahead}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        params = {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": limit,
        }

        try:
            response = await self._client.get("/markets", params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Polymarket API failed: %s", exc)
            return []

        try:
            markets_raw = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Polymarket response parse error: %s", exc)
            return []

        cutoff = datetime.now(UTC) + timedelta(days=end_date_days_ahead)
        results: list[dict] = []

        for market in markets_raw:
            # Parse liquidity, filter below threshold
            try:
                liquidity = float(market.get("liquidity") or 0)
            except (ValueError, TypeError):
                liquidity = 0.0
            if liquidity < min_liquidity:
                continue

            # Parse end date, filter beyond cutoff
            end_date_str = market.get("endDate")
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    if end_date > cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            # Parse outcomePrices -- JSON-stringified string
            try:
                prices = json.loads(market.get("outcomePrices", "[]"))
                yes_prob = float(prices[0]) if prices else 0.0
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                yes_prob = 0.0

            # Parse volume
            try:
                volume = float(market.get("volume") or 0)
            except (ValueError, TypeError):
                volume = 0.0

            # Extract categories from tags
            categories = [t.get("label", "") for t in market.get("tags", [])]

            results.append(
                {
                    "id": market.get("id", ""),
                    "question": market.get("question", ""),
                    "slug": market.get("slug", ""),
                    "description": market.get("description", ""),
                    "yes_probability": yes_prob,
                    "volume": volume,
                    "liquidity": liquidity,
                    "end_date": end_date_str,
                    "categories": categories,
                }
            )

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


class GdeltDocClient:
    """GDELT DOC 2.0 API -- article search.

    Endpoint: GET https://api.gdeltproject.org/api/v2/doc/doc
    No auth required. Rate limit: ~1 req/sec. Cache TTL: 15 min.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": _USER_AGENT},
        )
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._cache_ttl = 900  # 15 min
        self._last_request_time: float = 0.0

    async def search_articles(
        self,
        query: str = "*",
        *,
        timespan: str = "24h",
        max_records: int = 100,
        sourcelang: str | None = None,
        sourcecountry: str | None = None,
        themes: list[str] | None = None,
        sort: str = "hybridrel",
    ) -> list[dict]:
        """Search GDELT DOC 2.0 ArtList API.

        Returns:
            List of dicts with keys: url, title, seendate (parsed to datetime),
            domain, language, sourcecountry.

        Note:
            Advanced query operators can be embedded in query string:
            - theme:ECON_CENTRAL_BANK
            - sourcelang:russian (English name, not ISO code!)
            - sourcecountry:RS (FIPS code, not ISO! Russia=RS not RU)
            - tone<-5, toneabs>10
        """
        # Build query string with operators
        full_query = query
        if themes:
            theme_filter = " OR ".join(f"theme:{t}" for t in themes)
            full_query = f"({full_query}) ({theme_filter})"
        if sourcelang:
            full_query += f" sourcelang:{sourcelang}"
        if sourcecountry:
            full_query += f" sourcecountry:{sourcecountry}"

        # Check cache
        cache_key = f"gdelt:{full_query}:{timespan}:{max_records}:{sort}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        # Rate limit: wait at least 1 sec between requests
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        params = {
            "query": full_query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "timespan": timespan,
            "sort": sort,
        }

        try:
            response = await self._client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("GDELT DOC API failed: %s", exc)
            self._last_request_time = time.monotonic()
            return []

        self._last_request_time = time.monotonic()

        # GDELT returns HTML (not JSON) for invalid queries (e.g. Cyrillic text)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            logger.warning(
                "GDELT returned HTML instead of JSON (bad query?): %s",
                response.text[:200],
            )
            return []

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("GDELT response parse error: %s", exc)
            return []

        results: list[dict] = []
        for article in data.get("articles") or []:
            # Parse seendate: "20260328T143000Z" -> datetime
            seen_dt = None
            raw_date = article.get("seendate", "")
            if raw_date:
                try:
                    seen_dt = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=UTC,
                    )
                except (ValueError, TypeError):
                    pass

            results.append(
                {
                    "url": article.get("url", ""),
                    "title": article.get("title", ""),
                    "seendate": seen_dt,
                    "domain": article.get("domain", ""),
                    "language": article.get("language", ""),
                    "sourcecountry": article.get("sourcecountry", ""),
                }
            )

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def fetch_articles(
        self,
        query: str,
        *,
        language: str = "english",
        limit: int = 50,
        days_back: int = 3,
    ) -> list[dict]:
        """Protocol-compliant wrapper around search_articles.

        Maps GdeltClientProto.fetch_articles() to the underlying
        search_articles() with appropriate parameter translation.
        """
        timespan = f"{days_back * 24}h"
        return await self.search_articles(
            query,
            timespan=timespan,
            max_records=limit,
            sourcelang=language,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
