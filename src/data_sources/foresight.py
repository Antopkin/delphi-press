"""Форсайт-центры -- к��иенты Metaculus, Polymarket, GDELT.

Стадия: Stage 1 (сбор данных).
Сп��ка: docs/01-data-sources.md.
Контракт: к��ждый клиент возвращает list[dict], маппинг в Pydantic-схемы
          делает ForesightCollector (src/agents/collectors/foresight_collector.py).

Metaculus: опциональный Token auth (бесплатный, metaculus.com/aib).
Polymarket, GDELT: публичные API, авто��изация не требуется.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from src.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_USER_AGENT = "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)"


class MetaculusClient:
    """Metaculus crowd probability API.

    Endpoint: GET https://www.metaculus.com/api/posts/
    Auth: optional Token (free, from metaculus.com/aib). Cache TTL: 30 min.
    """

    def __init__(
        self,
        *,
        token: str = "",
        tournaments: list[int] | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {"User-Agent": _USER_AGENT}
        if token:
            headers["Authorization"] = f"Token {token}"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers=headers,
        )
        self._tournaments = tournaments
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
        """Fetch binary questions from Metaculus /api/posts/ endpoint.

        Returns:
            List of dicts with keys: id, title, url, q2 (median probability),
            q1, q3, resolve_time, categories, nr_forecasters.
            Filters out questions with < min_forecasters.
        """
        cache_key = f"metaculus:{query}:{resolve_days_ahead}:{limit}:{min_forecasters}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        now = datetime.now(UTC)
        resolve_gt = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        resolve_lt = (now + timedelta(days=resolve_days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params: dict[str, str | int] = {
            "statuses": status,
            "forecast_type": "binary",
            "scheduled_resolve_time__gt": resolve_gt,
            "scheduled_resolve_time__lt": resolve_lt,
            "order_by": "-hotness",
            "limit": limit,
            "with_cp": "true",
        }
        if self._tournaments:
            params["tournaments"] = ",".join(str(t) for t in self._tournaments)
        if query:
            params["search"] = query

        try:
            response = await self._client.get(
                "https://www.metaculus.com/api/posts/",
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
        for post in data.get("results", []):
            forecasters = post.get("nr_forecasters", 0)
            if forecasters < min_forecasters:
                continue

            question = post.get("question") or {}
            agg = question.get("aggregations") or {}
            rw = agg.get("recency_weighted") or agg.get("unweighted") or {}
            latest = rw.get("latest") or {}
            centers = latest.get("centers") or []
            q2 = centers[0] if centers else None
            if q2 is None:
                continue

            lb = latest.get("interval_lower_bounds") or []
            ub = latest.get("interval_upper_bounds") or []

            # Extract categories from projects.category
            categories_raw = post.get("projects", {}).get("category", [])
            categories = [c.get("name", "") for c in categories_raw if isinstance(c, dict)]

            results.append(
                {
                    "id": post.get("id"),
                    "title": post.get("title", ""),
                    "url": post.get("url", ""),
                    "q2": q2,
                    "q1": lb[0] if lb else None,
                    "q3": ub[0] if ub else None,
                    "resolve_time": question.get("scheduled_resolve_time"),
                    "categories": categories,
                    "nr_forecasters": forecasters,
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
        self._clob_client = httpx.AsyncClient(
            base_url="https://clob.polymarket.com",
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": _USER_AGENT},
        )
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._price_cache: dict[str, tuple[float, list[float]]] = {}
        self._cache_ttl = 900  # 15 min
        self._semaphore = asyncio.Semaphore(10)

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
        cache_key = f"polymarket:{query}:{limit}:{min_liquidity}:{end_date_days_ahead}"
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
            response = await retry_with_backoff(
                lambda: self._client.get("/markets", params=params),
                max_retries=2,
                base_delay=1.0,
            )
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

            # Extract CLOB token ID for price history
            try:
                clob_ids = json.loads(market.get("clobTokenIds", "[]"))
                clob_token_id = clob_ids[0] if clob_ids else ""
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                clob_token_id = ""

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
                    "clob_token_id": clob_token_id,
                }
            )

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def fetch_price_history(
        self,
        token_id: str,
        *,
        interval: str = "1d",
        fidelity: int = 60,
    ) -> list[float]:
        """Fetch CLOB price history for a token.

        Returns:
            Chronological list of prices (floats). Empty on error.
        """
        if not token_id:
            return []

        cache_key = f"clob_prices:{token_id}"
        cached = self._price_cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        params = {"market": token_id, "interval": interval, "fidelity": fidelity}
        try:
            async with self._semaphore:
                response = await retry_with_backoff(
                    lambda: self._clob_client.get("/prices-history", params=params),
                    max_retries=2,
                    base_delay=1.0,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("CLOB price history failed for %s: %s", token_id, exc)
            return []

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("CLOB price history parse error: %s", exc)
            return []

        history = data.get("history", [])
        prices = []
        for point in history:
            try:
                prices.append(float(point["p"]))
            except (KeyError, ValueError, TypeError):
                continue

        self._price_cache[cache_key] = (time.monotonic(), prices)
        return prices

    async def fetch_resolved_markets(
        self,
        *,
        limit: int = 100,
        min_volume: float = 10_000.0,
    ) -> list[dict]:
        """Fetch resolved (closed) markets from Gamma API.

        Resolution outcome is determined from outcomePrices:
        winning side = "1". Uses closedTime as resolution timestamp
        (resolvedAt field does not exist in the Gamma API).

        Returns:
            List of dicts with keys: market_id, question, slug,
            resolved_yes, closed_time, volume, categories, clob_token_id.
        """
        cache_key = f"polymarket_resolved:{limit}:{min_volume}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        params = {
            "active": "false",
            "closed": "true",
            "order": "volume",
            "ascending": "false",
            "limit": limit,
        }

        try:
            response = await retry_with_backoff(
                lambda: self._client.get("/markets", params=params),
                max_retries=2,
                base_delay=1.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Polymarket resolved markets API failed: %s", exc)
            return []

        try:
            markets_raw = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Polymarket resolved response parse error: %s", exc)
            return []

        results: list[dict] = []
        for market in markets_raw:
            # Parse volume, filter below threshold
            try:
                volume = float(market.get("volume") or 0)
            except (ValueError, TypeError):
                volume = 0.0
            if volume < min_volume:
                continue

            # Determine resolution from outcomePrices
            # outcomePrices[0]=="1" → YES; outcomePrices[1]=="1" → NO
            try:
                prices = json.loads(market.get("outcomePrices", "[]"))
                resolved_yes = len(prices) >= 1 and float(prices[0]) == 1.0
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                continue  # Skip unresolvable markets

            # Extract CLOB token ID
            try:
                clob_ids = json.loads(market.get("clobTokenIds", "[]"))
                clob_token_id = clob_ids[0] if clob_ids else ""
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                clob_token_id = ""

            categories = [t.get("label", "") for t in market.get("tags", [])]

            results.append(
                {
                    "market_id": market.get("id", ""),
                    "question": market.get("question", ""),
                    "slug": market.get("slug", ""),
                    "resolved_yes": resolved_yes,
                    "closed_time": market.get("closedTime", ""),
                    "volume": volume,
                    "categories": categories,
                    "clob_token_id": clob_token_id,
                }
            )

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def fetch_historical_price(
        self,
        token_id: str,
        target_timestamp: int,
        *,
        window_seconds: int = 3600,
    ) -> float | None:
        """Get market price at a specific historical moment.

        Uses chunked startTs/endTs instead of interval=max, which returns
        empty for resolved markets with fidelity < 720 (known CLOB bug).

        Args:
            token_id: CLOB token ID.
            target_timestamp: Unix timestamp to get price at.
            window_seconds: Search window around target (default 1 hour).

        Returns:
            Price closest to target_timestamp, or None if no data.
        """
        if not token_id:
            return None

        params = {
            "market": token_id,
            "startTs": target_timestamp - window_seconds,
            "endTs": target_timestamp + window_seconds,
            "fidelity": 60,
        }
        try:
            async with self._semaphore:
                response = await retry_with_backoff(
                    lambda: self._clob_client.get("/prices-history", params=params),
                    max_retries=2,
                    base_delay=1.0,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("CLOB historical price failed for %s: %s", token_id, exc)
            return None

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            return None

        history = data.get("history", [])
        if not history:
            return None

        # Find point closest to target_timestamp
        best_point = min(history, key=lambda pt: abs(int(pt.get("t", 0)) - target_timestamp))
        try:
            return float(best_point["p"])
        except (KeyError, ValueError, TypeError):
            return None

    async def fetch_enriched_markets(
        self,
        query: str = "",
        *,
        limit: int = 100,
        min_liquidity: float = 5000.0,
        end_date_days_ahead: int = 30,
    ) -> list[dict]:
        """Fetch markets from Gamma then enrich with CLOB price history.

        For each market, fetches price history in parallel via the CLOB API.
        Adds ``price_history`` (list[float]) to each market dict. On partial
        CLOB failure, affected markets get ``price_history=[]``.
        """
        markets = await self.fetch_markets(
            query,
            limit=limit,
            min_liquidity=min_liquidity,
            end_date_days_ahead=end_date_days_ahead,
        )
        if not markets:
            return markets

        # Pre-set default so every market has price_history even on error
        for m in markets:
            m["price_history"] = []

        async def _enrich(market: dict) -> None:
            token_id = market.get("clob_token_id", "")
            market["price_history"] = await self.fetch_price_history(token_id)

        await asyncio.gather(*[_enrich(m) for m in markets], return_exceptions=True)
        return markets

    async def close(self) -> None:
        """Close the underlying HTTP clients."""
        await self._client.aclose()
        await self._clob_client.aclose()


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
        self._rate_lock = asyncio.Lock()

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

        # Rate limit: wait at least 1 sec between requests (lock prevents concurrent bypass)
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_request_time = time.monotonic()

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
            return []

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
