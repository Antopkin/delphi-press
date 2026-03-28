"""Tests for src.data_sources.foresight -- Metaculus, Polymarket, GDELT clients."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.data_sources.foresight import GdeltDocClient, MetaculusClient, PolymarketClient

# ---------------------------------------------------------------------------
# Metaculus fixtures
# ---------------------------------------------------------------------------

METACULUS_RESPONSE = {
    "count": 2,
    "next": None,
    "results": [
        {
            "id": 10003,
            "title": "Will X happen?",
            "url": "https://www.metaculus.com/questions/10003/",
            "status": "open",
            "type": "binary",
            "resolve_time": "2026-04-15T00:00:00Z",
            "community_prediction": {"full": {"q1": 0.12, "q2": 0.25, "q3": 0.42}},
            "number_of_forecasters": 87,
            "categories": [{"id": 5, "name": "Geopolitics"}],
        },
        {
            "id": 10004,
            "title": "Will Y happen?",
            "url": "https://www.metaculus.com/questions/10004/",
            "status": "open",
            "type": "binary",
            "resolve_time": "2026-04-10T00:00:00Z",
            "community_prediction": {"full": {"q1": 0.50, "q2": 0.65, "q3": 0.80}},
            "number_of_forecasters": 42,
            "categories": [{"id": 3, "name": "Science"}],
        },
    ],
}

METACULUS_LOW_FORECASTERS = {
    "count": 1,
    "next": None,
    "results": [
        {
            "id": 10005,
            "title": "Low interest question",
            "url": "https://www.metaculus.com/questions/10005/",
            "community_prediction": {"full": {"q1": 0.1, "q2": 0.2, "q3": 0.3}},
            "number_of_forecasters": 3,
            "categories": [],
        },
    ],
}

METACULUS_NULL_PREDICTION = {
    "count": 1,
    "next": None,
    "results": [
        {
            "id": 10006,
            "title": "No prediction yet",
            "url": "https://www.metaculus.com/questions/10006/",
            "community_prediction": None,
            "number_of_forecasters": 0,
            "categories": [],
        },
    ],
}

# ---------------------------------------------------------------------------
# Polymarket fixtures
# ---------------------------------------------------------------------------

POLYMARKET_RESPONSE = [
    {
        "id": "abc123",
        "question": "Will X happen?",
        "slug": "will-x-happen",
        "description": "Resolves YES if...",
        "endDate": "2026-04-15T00:00:00Z",
        "active": True,
        "closed": False,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.65", "0.35"]',
        "volume": "450000.00",
        "liquidity": "85000.00",
        "clobTokenIds": '["token_yes_abc", "token_no_abc"]',
        "tags": [{"id": 1, "label": "Politics"}],
    },
]

POLYMARKET_LOW_LIQUIDITY = [
    {
        "id": "low_liq",
        "question": "Tiny market?",
        "slug": "tiny-market",
        "description": "Almost no liquidity",
        "endDate": "2026-04-10T00:00:00Z",
        "active": True,
        "closed": False,
        "outcomePrices": '["0.50", "0.50"]',
        "volume": "500.00",
        "liquidity": "100.00",
        "tags": [],
    },
]

# ---------------------------------------------------------------------------
# GDELT fixtures
# ---------------------------------------------------------------------------

GDELT_RESPONSE = {
    "articles": [
        {
            "url": "https://example.com/article",
            "title": "Breaking news headline",
            "seendate": "20260328T143000Z",
            "domain": "example.com",
            "language": "English",
            "sourcecountry": "US",
        },
        {
            "url": "https://example.org/story",
            "title": "Another headline",
            "seendate": "20260328T120000Z",
            "domain": "example.org",
            "language": "Russian",
            "sourcecountry": "RS",
        },
    ]
}


def _make_response(
    status_code: int,
    json_data: dict | list,
    method: str = "GET",
    url: str = "https://test",
) -> httpx.Response:
    """Helper to build httpx.Response with a proper request object."""
    return httpx.Response(
        status_code,
        json=json_data,
        request=httpx.Request(method, url),
    )


# ===========================================================================
# MetaculusClient
# ===========================================================================


class TestMetaculusClient:
    async def test_fetch_questions_success(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions()

        assert len(results) == 2
        assert results[0]["id"] == 10003
        assert results[0]["title"] == "Will X happen?"
        assert results[0]["q2"] == 0.25
        assert results[0]["q1"] == 0.12
        assert results[0]["q3"] == 0.42
        assert results[0]["categories"] == ["Geopolitics"]
        assert results[0]["number_of_forecasters"] == 87
        assert results[1]["q2"] == 0.65

    async def test_fetch_questions_filters_low_forecasters(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_LOW_FORECASTERS)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions(min_forecasters=10)

        assert results == []

    async def test_fetch_questions_handles_null_community_prediction(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_NULL_PREDICTION)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions()

        assert results == []

    async def test_fetch_questions_caches_results(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            first = await client.fetch_questions()
            second = await client.fetch_questions()

        assert mock_get.await_count == 1
        assert first == second

    async def test_fetch_questions_http_error(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(500, {"error": "server error"})
        with patch.object(
            client._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "https://test"), response=mock_resp
            ),
        ):
            results = await client.fetch_questions()

        assert results == []


# ===========================================================================
# PolymarketClient
# ===========================================================================


class TestPolymarketClient:
    async def test_fetch_markets_success(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESPONSE)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_markets()

        assert len(results) == 1
        market = results[0]
        assert market["id"] == "abc123"
        assert market["question"] == "Will X happen?"
        assert market["yes_probability"] == pytest.approx(0.65)
        assert market["liquidity"] == pytest.approx(85000.0)
        assert market["volume"] == pytest.approx(450000.0)
        assert market["categories"] == ["Politics"]

    async def test_fetch_markets_parses_stringified_json(self) -> None:
        """outcomePrices is a JSON string, not a native array."""
        data = [
            {
                "id": "str_test",
                "question": "String test",
                "slug": "str-test",
                "description": "",
                "endDate": "2026-04-15T00:00:00Z",
                "outcomePrices": '["0.78", "0.22"]',
                "volume": "1000.00",
                "liquidity": "10000.00",
                "tags": [],
            },
        ]
        client = PolymarketClient()
        mock_resp = _make_response(200, data)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_markets()

        assert len(results) == 1
        assert results[0]["yes_probability"] == pytest.approx(0.78)

    async def test_fetch_markets_filters_low_liquidity(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_LOW_LIQUIDITY)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_markets(min_liquidity=5000.0)

        assert results == []

    async def test_fetch_markets_http_error(self) -> None:
        client = PolymarketClient()
        with patch.object(
            client._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            results = await client.fetch_markets()

        assert results == []


# ---------------------------------------------------------------------------
# CLOB / enriched markets
# ---------------------------------------------------------------------------

CLOB_PRICE_HISTORY_RESPONSE = {
    "history": [
        {"t": 1709000000, "p": "0.52"},
        {"t": 1709003600, "p": "0.54"},
        {"t": 1709007200, "p": "0.55"},
        {"t": 1709010800, "p": "0.53"},
        {"t": 1709014400, "p": "0.56"},
    ]
}

CLOB_EMPTY_HISTORY = {"history": []}


class TestPolymarketClientCLOB:
    async def test_fetch_price_history_success(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_PRICE_HISTORY_RESPONSE)
        with patch.object(
            client._clob_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            prices = await client.fetch_price_history("token_yes_abc")

        assert prices == [0.52, 0.54, 0.55, 0.53, 0.56]

    async def test_fetch_price_history_empty(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_EMPTY_HISTORY)
        with patch.object(
            client._clob_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            prices = await client.fetch_price_history("token_xyz")

        assert prices == []

    async def test_fetch_price_history_empty_token_id(self) -> None:
        client = PolymarketClient()
        prices = await client.fetch_price_history("")
        assert prices == []

    async def test_fetch_price_history_http_error(self) -> None:
        client = PolymarketClient()
        with patch.object(
            client._clob_client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("timeout"),
        ):
            prices = await client.fetch_price_history("token_fail")

        assert prices == []

    async def test_fetch_price_history_caching(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_PRICE_HISTORY_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._clob_client, "get", mock_get):
            first = await client.fetch_price_history("token_cache")
            second = await client.fetch_price_history("token_cache")

        assert mock_get.await_count == 1
        assert first == second

    async def test_fetch_enriched_markets_success(self) -> None:
        client = PolymarketClient()
        gamma_resp = _make_response(200, POLYMARKET_RESPONSE)
        clob_resp = _make_response(200, CLOB_PRICE_HISTORY_RESPONSE)
        with (
            patch.object(client._client, "get", new_callable=AsyncMock, return_value=gamma_resp),
            patch.object(
                client._clob_client, "get", new_callable=AsyncMock, return_value=clob_resp
            ),
        ):
            markets = await client.fetch_enriched_markets()

        assert len(markets) == 1
        assert markets[0]["clob_token_id"] == "token_yes_abc"
        assert markets[0]["price_history"] == [0.52, 0.54, 0.55, 0.53, 0.56]

    async def test_fetch_enriched_markets_partial_clob_failure(self) -> None:
        """CLOB failure for one market should not affect others."""
        two_markets = [
            {
                **POLYMARKET_RESPONSE[0],
                "id": "m1",
                "clobTokenIds": '["token_m1"]',
            },
            {
                **POLYMARKET_RESPONSE[0],
                "id": "m2",
                "clobTokenIds": '["token_m2"]',
            },
        ]
        client = PolymarketClient()
        gamma_resp = _make_response(200, two_markets)

        call_count = 0

        async def _clob_get(url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            if params.get("market") == "token_m1":
                return _make_response(200, CLOB_PRICE_HISTORY_RESPONSE)
            raise httpx.ConnectError("timeout")

        with (
            patch.object(client._client, "get", new_callable=AsyncMock, return_value=gamma_resp),
            patch.object(client._clob_client, "get", side_effect=_clob_get),
        ):
            markets = await client.fetch_enriched_markets()

        assert len(markets) == 2
        # m1 succeeded
        m1 = next(m for m in markets if m["id"] == "m1")
        assert len(m1["price_history"]) == 5
        # m2 failed gracefully
        m2 = next(m for m in markets if m["id"] == "m2")
        assert m2["price_history"] == []

    async def test_fetch_markets_includes_clob_token_id(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESPONSE)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_markets()

        assert results[0]["clob_token_id"] == "token_yes_abc"

    async def test_fetch_markets_missing_clob_token_ids(self) -> None:
        """Markets without clobTokenIds should get empty string."""
        data = [{**POLYMARKET_RESPONSE[0]}]
        del data[0]["clobTokenIds"]
        client = PolymarketClient()
        mock_resp = _make_response(200, data)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_markets()

        assert results[0]["clob_token_id"] == ""


# ===========================================================================
# GdeltDocClient
# ===========================================================================


class TestGdeltDocClient:
    async def test_search_articles_success(self) -> None:
        client = GdeltDocClient()
        # Ensure no rate-limit delay
        client._last_request_time = 0.0
        mock_resp = _make_response(200, GDELT_RESPONSE)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.search_articles("test query")

        assert len(results) == 2
        assert results[0]["title"] == "Breaking news headline"
        assert results[0]["domain"] == "example.com"
        assert results[0]["sourcecountry"] == "US"
        # Verify seendate parsed to datetime
        assert isinstance(results[0]["seendate"], datetime)
        assert results[0]["seendate"] == datetime(2026, 3, 28, 14, 30, 0, tzinfo=UTC)

    async def test_search_articles_with_themes(self) -> None:
        """Verify theme: operators are added to query string."""
        client = GdeltDocClient()
        client._last_request_time = 0.0
        mock_resp = _make_response(200, {"articles": []})
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.search_articles("economy", themes=["ECON_CENTRAL_BANK", "ECON_INFLATION"])

        # Inspect the query parameter passed to httpx
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        query_sent = params["query"]
        assert "theme:ECON_CENTRAL_BANK" in query_sent
        assert "theme:ECON_INFLATION" in query_sent
        assert "(economy)" in query_sent

    async def test_search_articles_rate_limiting(self) -> None:
        """Verify rate limiter enforces ~1 sec between requests."""
        client = GdeltDocClient()
        mock_resp = _make_response(200, {"articles": []})

        # Set last request time to "just now" to trigger rate limit
        client._last_request_time = time.monotonic()

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            with patch(
                "src.data_sources.foresight.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep:
                # Use a unique query to avoid cache hit
                await client.search_articles("rate_limit_test_query")

        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert 0 < sleep_duration <= 1.0

    async def test_search_articles_caches_results(self) -> None:
        client = GdeltDocClient()
        client._last_request_time = 0.0
        mock_resp = _make_response(200, GDELT_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            first = await client.search_articles("cached_query")
            second = await client.search_articles("cached_query")

        assert mock_get.await_count == 1
        assert first == second

    async def test_search_articles_http_error(self) -> None:
        client = GdeltDocClient()
        client._last_request_time = 0.0
        with patch.object(
            client._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("timeout"),
        ):
            results = await client.search_articles("failing query")

        assert results == []
