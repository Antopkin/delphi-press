"""Tests for src.data_sources.foresight -- Metaculus, Polymarket, GDELT clients."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.data_sources.foresight import GdeltDocClient, MetaculusClient, PolymarketClient

# ---------------------------------------------------------------------------
# Metaculus fixtures (new /api/posts/ format)
# ---------------------------------------------------------------------------


def _make_metaculus_post(
    post_id: int = 10003,
    title: str = "Will X happen?",
    url: str = "https://www.metaculus.com/questions/10003/",
    q2: float = 0.25,
    q1: float = 0.12,
    q3: float = 0.42,
    nr_forecasters: int = 87,
    categories: list[dict] | None = None,
    resolve_time: str = "2026-04-15T00:00:00Z",
    aggregations: dict | None = None,
) -> dict:
    """Build a Metaculus /api/posts/ response item."""
    if categories is None:
        categories = [{"id": 5, "name": "Geopolitics"}]

    if aggregations is None:
        aggregations = {
            "recency_weighted": {
                "latest": {
                    "centers": [q2],
                    "interval_lower_bounds": [q1],
                    "interval_upper_bounds": [q3],
                    "means": [q2 + 0.01],
                    "forecaster_count": nr_forecasters,
                },
                "history": [],
            },
        }

    return {
        "id": post_id,
        "title": title,
        "url": url,
        "nr_forecasters": nr_forecasters,
        "forecasts_count": nr_forecasters * 3,
        "projects": {"category": categories},
        "question": {
            "id": post_id + 1000,
            "type": "binary",
            "status": "open",
            "scheduled_resolve_time": resolve_time,
            "aggregations": aggregations,
        },
    }


METACULUS_RESPONSE = {
    "count": 2,
    "next": None,
    "results": [
        _make_metaculus_post(
            post_id=10003,
            title="Will X happen?",
            url="https://www.metaculus.com/questions/10003/",
            q2=0.25,
            q1=0.12,
            q3=0.42,
            nr_forecasters=87,
            categories=[{"id": 5, "name": "Geopolitics"}],
            resolve_time="2026-04-15T00:00:00Z",
        ),
        _make_metaculus_post(
            post_id=10004,
            title="Will Y happen?",
            url="https://www.metaculus.com/questions/10004/",
            q2=0.65,
            q1=0.50,
            q3=0.80,
            nr_forecasters=42,
            categories=[{"id": 3, "name": "Science"}],
            resolve_time="2026-04-10T00:00:00Z",
        ),
    ],
}

METACULUS_LOW_FORECASTERS = {
    "count": 1,
    "next": None,
    "results": [
        _make_metaculus_post(
            post_id=10005,
            title="Low interest question",
            url="https://www.metaculus.com/questions/10005/",
            q2=0.2,
            q1=0.1,
            q3=0.3,
            nr_forecasters=3,
            categories=[],
        ),
    ],
}

METACULUS_NULL_PREDICTION = {
    "count": 1,
    "next": None,
    "results": [
        _make_metaculus_post(
            post_id=10006,
            title="No prediction yet",
            url="https://www.metaculus.com/questions/10006/",
            nr_forecasters=0,
            categories=[],
            aggregations=None,  # no aggregations at all
        ),
    ],
}

# ---------------------------------------------------------------------------
# Polymarket fixtures
# ---------------------------------------------------------------------------

POLYMARKET_RESPONSE = [
    {
        "id": "abc123",
        "conditionId": "0xabc123def456789000000000000000000000000000000000000000000000dead",
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
        assert results[0]["nr_forecasters"] == 87
        assert results[1]["q2"] == 0.65

    async def test_fetch_questions_filters_low_forecasters(self) -> None:
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_LOW_FORECASTERS)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions(min_forecasters=10)

        assert results == []

    async def test_fetch_questions_handles_null_aggregations(self) -> None:
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

    # --- New migration tests ---

    async def test_fetch_questions_uses_new_api_endpoint(self) -> None:
        """Verify requests go to /api/posts/, not /api2/questions/."""
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions()

        url = mock_get.call_args[0][0]
        assert "/api/posts/" in url
        assert "/api2/questions/" not in url

    async def test_fetch_questions_sends_auth_header(self) -> None:
        """When token is provided, Authorization header must be set."""
        client = MetaculusClient(token="test-token-123")
        assert client._client.headers["Authorization"] == "Token test-token-123"

    async def test_fetch_questions_works_without_token(self) -> None:
        """Client works without token (graceful degradation)."""
        client = MetaculusClient()
        assert "Authorization" not in client._client.headers
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions()
        assert len(results) == 2

    async def test_fetch_questions_sends_with_cp_param(self) -> None:
        """with_cp=true must be in params to get aggregations."""
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions()

        params = mock_get.call_args.kwargs.get("params", {})
        assert params.get("with_cp") == "true"

    async def test_fetch_questions_sends_tournaments_param(self) -> None:
        """When tournaments are set, they must appear in API params."""
        client = MetaculusClient(tournaments=[32977, 32979])
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions()

        params = mock_get.call_args.kwargs.get("params", {})
        assert params.get("tournaments") == "32977,32979"

    async def test_fetch_questions_no_tournaments_by_default(self) -> None:
        """Without tournaments, param should not be sent."""
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions()

        params = mock_get.call_args.kwargs.get("params", {})
        assert "tournaments" not in params

    async def test_fetch_questions_uses_new_param_names(self) -> None:
        """Verify scheduled_resolve_time__gt/lt and statuses params."""
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions()

        params = mock_get.call_args.kwargs.get("params", {})
        assert "scheduled_resolve_time__gt" in params
        assert "scheduled_resolve_time__lt" in params
        assert "statuses" in params
        # Old param names must NOT be present
        assert "resolve_time__gt" not in params
        assert "resolve_time__lt" not in params
        assert "status" not in params

    async def test_fetch_questions_parses_new_response_format(self) -> None:
        """Parse question.aggregations.recency_weighted.latest.centers[0]."""
        post = _make_metaculus_post(q2=0.73, q1=0.55, q3=0.88, nr_forecasters=50)
        data = {"count": 1, "next": None, "results": [post]}
        client = MetaculusClient()
        mock_resp = _make_response(200, data)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions()

        assert len(results) == 1
        assert results[0]["q2"] == pytest.approx(0.73)
        assert results[0]["q1"] == pytest.approx(0.55)
        assert results[0]["q3"] == pytest.approx(0.88)
        assert results[0]["nr_forecasters"] == 50

    async def test_fetch_questions_passes_query_as_search(self) -> None:
        """query param must be sent as 'search' to the API."""
        client = MetaculusClient()
        mock_resp = _make_response(200, {"count": 0, "next": None, "results": []})
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions("ukraine conflict")

        params = mock_get.call_args.kwargs.get("params", {})
        assert params.get("search") == "ukraine conflict"

    async def test_fetch_questions_omits_search_when_empty(self) -> None:
        """Empty query should not add search param."""
        client = MetaculusClient()
        mock_resp = _make_response(200, {"count": 0, "next": None, "results": []})
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions("")

        params = mock_get.call_args.kwargs.get("params", {})
        assert "search" not in params

    async def test_fetch_questions_uses_status_parameter(self) -> None:
        """status param should be forwarded, not hardcoded."""
        client = MetaculusClient()
        mock_resp = _make_response(200, {"count": 0, "next": None, "results": []})
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions(status="resolved")

        params = mock_get.call_args.kwargs.get("params", {})
        assert params.get("statuses") == "resolved"

    async def test_fetch_questions_fallback_to_unweighted(self) -> None:
        """If recency_weighted is None, fallback to unweighted."""
        post = _make_metaculus_post(
            nr_forecasters=20,
            aggregations={
                "recency_weighted": None,
                "unweighted": {
                    "latest": {
                        "centers": [0.40],
                        "interval_lower_bounds": [0.30],
                        "interval_upper_bounds": [0.55],
                    },
                },
            },
        )
        data = {"count": 1, "next": None, "results": [post]}
        client = MetaculusClient()
        mock_resp = _make_response(200, data)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_questions()

        assert len(results) == 1
        assert results[0]["q2"] == pytest.approx(0.40)

    async def test_fetch_questions_different_query_different_cache(self) -> None:
        """Different query strings must produce different cache entries."""
        client = MetaculusClient()
        mock_resp = _make_response(200, METACULUS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_questions("ukraine")
            await client.fetch_questions("economics")

        # Two different queries → two HTTP calls (not cached)
        assert mock_get.await_count == 2


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
        assert (
            market["condition_id"]
            == "0xabc123def456789000000000000000000000000000000000000000000000dead"
        )
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

    async def test_fetch_markets_different_query_different_cache(self) -> None:
        """Different query strings must produce different cache entries."""
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_markets("bitcoin")
            await client.fetch_markets("ethereum")

        # Two different queries → two HTTP calls (not cached)
        assert mock_get.await_count == 2


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

    async def test_fetch_price_history_sends_market_param(self) -> None:
        """CLOB API must receive 'market' param (asset id)."""
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_PRICE_HISTORY_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._clob_client, "get", mock_get):
            await client.fetch_price_history("token_abc")

        params = mock_get.call_args.kwargs.get("params", {})
        assert "market" in params
        assert params["market"] == "token_abc"

    async def test_fetch_enriched_markets_always_has_price_history_key(self) -> None:
        """Every market must have price_history key even when _enrich raises."""
        two_markets = [
            {**POLYMARKET_RESPONSE[0], "id": "m1", "clobTokenIds": '["t1"]'},
            {**POLYMARKET_RESPONSE[0], "id": "m2", "clobTokenIds": '["t2"]'},
        ]
        client = PolymarketClient()
        gamma_resp = _make_response(200, two_markets)

        # All CLOB calls raise
        with (
            patch.object(client._client, "get", new_callable=AsyncMock, return_value=gamma_resp),
            patch.object(
                client._clob_client,
                "get",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("down"),
            ),
        ):
            markets = await client.fetch_enriched_markets()

        for m in markets:
            assert "price_history" in m
            assert isinstance(m["price_history"], list)


# ===========================================================================
# PolymarketClient — Resolved markets
# ===========================================================================

POLYMARKET_RESOLVED_YES = [
    {
        "id": "resolved_yes_1",
        "question": "Will X happen by March?",
        "slug": "will-x-happen-march",
        "description": "Resolves YES if...",
        "endDate": "2026-03-15T00:00:00Z",
        "closedTime": "2026-03-15T12:00:00+00:00",
        "active": False,
        "closed": True,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["1", "0"]',
        "volume": "250000.00",
        "liquidity": "0.00",
        "clobTokenIds": '["token_res_yes", "token_res_no"]',
        "tags": [{"id": 1, "label": "Politics"}],
    },
]

POLYMARKET_RESOLVED_NO = [
    {
        "id": "resolved_no_1",
        "question": "Will Y pass by April?",
        "slug": "will-y-pass-april",
        "description": "Resolves YES if...",
        "endDate": "2026-04-01T00:00:00Z",
        "closedTime": "2026-04-01T18:00:00+00:00",
        "active": False,
        "closed": True,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0", "1"]',
        "volume": "180000.00",
        "liquidity": "0.00",
        "clobTokenIds": '["token_n_yes", "token_n_no"]',
        "tags": [{"id": 2, "label": "Economics"}],
    },
]

POLYMARKET_RESOLVED_LOW_VOL = [
    {
        "id": "low_vol_resolved",
        "question": "Tiny resolved market",
        "slug": "tiny-resolved",
        "description": "",
        "endDate": "2026-03-10T00:00:00Z",
        "closedTime": "2026-03-10T10:00:00+00:00",
        "active": False,
        "closed": True,
        "outcomePrices": '["1", "0"]',
        "volume": "500.00",
        "liquidity": "0.00",
        "tags": [],
    },
]


class TestPolymarketResolvedMarkets:
    async def test_fetch_resolved_markets_success(self) -> None:
        """Resolved YES market parsed correctly from outcomePrices."""
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESOLVED_YES)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_resolved_markets()

        assert len(results) == 1
        m = results[0]
        assert m["market_id"] == "resolved_yes_1"
        assert m["question"] == "Will X happen by March?"
        assert m["resolved_yes"] is True
        assert m["closed_time"] == "2026-03-15T12:00:00+00:00"
        assert m["volume"] == pytest.approx(250000.0)
        assert m["clob_token_id"] == "token_res_yes"
        assert m["categories"] == ["Politics"]

    async def test_fetch_resolved_markets_resolved_no(self) -> None:
        """outcomePrices=["0","1"] means resolved NO."""
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESOLVED_NO)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_resolved_markets()

        assert len(results) == 1
        assert results[0]["resolved_yes"] is False

    async def test_fetch_resolved_markets_filters_low_volume(self) -> None:
        """Markets with volume below threshold are excluded."""
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESOLVED_LOW_VOL)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.fetch_resolved_markets(min_volume=10_000.0)

        assert results == []

    async def test_fetch_resolved_markets_http_error_returns_empty(self) -> None:
        client = PolymarketClient()
        with patch.object(
            client._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            results = await client.fetch_resolved_markets()

        assert results == []

    async def test_fetch_resolved_markets_caches(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, POLYMARKET_RESOLVED_YES)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            first = await client.fetch_resolved_markets()
            second = await client.fetch_resolved_markets()

        assert mock_get.await_count == 1
        assert first == second

    async def test_fetch_resolved_markets_sends_closed_params(self) -> None:
        """API must be called with active=false&closed=true."""
        client = PolymarketClient()
        mock_resp = _make_response(200, [])
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._client, "get", mock_get):
            await client.fetch_resolved_markets()

        params = mock_get.call_args.kwargs.get("params", {})
        assert params.get("active") == "false"
        assert params.get("closed") == "true"


# ===========================================================================
# PolymarketClient — Historical price at timestamp
# ===========================================================================

CLOB_HISTORICAL_RESPONSE = {
    "history": [
        {"t": 1710500000, "p": "0.48"},
        {"t": 1710503600, "p": "0.51"},
        {"t": 1710507200, "p": "0.53"},
    ]
}


class TestPolymarketHistoricalPrice:
    async def test_fetch_historical_price_success(self) -> None:
        """Returns price closest to target timestamp."""
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_HISTORICAL_RESPONSE)
        with patch.object(
            client._clob_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            # Target closest to middle point (1710503600)
            price = await client.fetch_historical_price("token_abc", 1710503500)

        assert price is not None
        assert price == pytest.approx(0.51)

    async def test_fetch_historical_price_no_data_returns_none(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_EMPTY_HISTORY)
        with patch.object(
            client._clob_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            price = await client.fetch_historical_price("token_xyz", 1710500000)

        assert price is None

    async def test_fetch_historical_price_uses_market_and_startTs_endTs(self) -> None:
        """Must use 'market' param + startTs/endTs, NOT interval=max."""
        client = PolymarketClient()
        mock_resp = _make_response(200, CLOB_EMPTY_HISTORY)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._clob_client, "get", mock_get):
            await client.fetch_historical_price("token_check", 1710500000)

        params = mock_get.call_args.kwargs.get("params", {})
        assert "market" in params
        assert params["market"] == "token_check"
        assert "startTs" in params
        assert "endTs" in params
        assert "interval" not in params

    async def test_fetch_historical_price_empty_token(self) -> None:
        client = PolymarketClient()
        price = await client.fetch_historical_price("", 1710500000)
        assert price is None


# ===========================================================================
# PolymarketClient — Data API (trades)
# ===========================================================================

DATA_API_TRADES_RESPONSE = [
    {
        "proxyWallet": "0xWallet1",
        "side": "BUY",
        "conditionId": "0xabc123",
        "size": "150.00",
        "price": "0.65",
        "timestamp": "2026-03-29T10:00:00Z",
        "outcome": "Yes",
        "outcomeIndex": "0",
    },
    {
        "proxyWallet": "0xWallet2",
        "side": "SELL",
        "conditionId": "0xabc123",
        "size": "80.00",
        "price": "0.70",
        "timestamp": "2026-03-29T11:00:00Z",
        "outcome": "Yes",
        "outcomeIndex": "0",
    },
]


class TestPolymarketDataAPI:
    async def test_fetch_market_trades_success(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, DATA_API_TRADES_RESPONSE)
        with patch.object(
            client._data_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            trades = await client.fetch_market_trades("0xabc123")

        assert len(trades) == 2
        assert trades[0]["proxyWallet"] == "0xWallet1"

    async def test_fetch_market_trades_empty_condition_id(self) -> None:
        client = PolymarketClient()
        trades = await client.fetch_market_trades("")
        assert trades == []

    async def test_fetch_market_trades_http_error(self) -> None:
        client = PolymarketClient()
        with patch.object(
            client._data_client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("timeout"),
        ):
            trades = await client.fetch_market_trades("0xfail")

        assert trades == []

    async def test_fetch_market_trades_caching(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, DATA_API_TRADES_RESPONSE)
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._data_client, "get", mock_get):
            first = await client.fetch_market_trades("0xcache")
            second = await client.fetch_market_trades("0xcache")

        assert mock_get.await_count == 1
        assert first == second

    async def test_fetch_market_trades_sends_correct_params(self) -> None:
        client = PolymarketClient()
        mock_resp = _make_response(200, [])
        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(client._data_client, "get", mock_get):
            await client.fetch_market_trades("0xcheck")

        params = mock_get.call_args.kwargs.get("params", {})
        assert params["market"] == "0xcheck"
        assert params["limit"] == 10_000

    async def test_fetch_trades_batch_success(self) -> None:
        client = PolymarketClient()
        mock_resp_a = _make_response(200, [DATA_API_TRADES_RESPONSE[0]])
        mock_resp_b = _make_response(200, [DATA_API_TRADES_RESPONSE[1]])

        call_count = 0

        async def _side_effect(url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            if params.get("market") == "0xid_a":
                return mock_resp_a
            return mock_resp_b

        with patch.object(client._data_client, "get", side_effect=_side_effect):
            result = await client.fetch_trades_batch(["0xid_a", "0xid_b"])

        assert len(result) == 2
        assert len(result["0xid_a"]) == 1
        assert len(result["0xid_b"]) == 1

    async def test_fetch_trades_batch_partial_failure(self) -> None:
        client = PolymarketClient()
        mock_resp_ok = _make_response(200, DATA_API_TRADES_RESPONSE)

        async def _side_effect(url: str, **kwargs: object) -> httpx.Response:
            params = kwargs.get("params", {})
            if params.get("market") == "0xfail":
                raise httpx.ConnectError("boom")
            return mock_resp_ok

        with patch.object(client._data_client, "get", side_effect=_side_effect):
            result = await client.fetch_trades_batch(["0xok", "0xfail"])

        assert len(result["0xok"]) == 2
        assert result["0xfail"] == []

    async def test_fetch_market_trades_non_list_response(self) -> None:
        """Data API returning a JSON object (e.g. error) instead of list → empty."""
        client = PolymarketClient()
        mock_resp = _make_response(200, {"error": "rate limited"})
        with patch.object(
            client._data_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            trades = await client.fetch_market_trades("0xbad_response")

        assert trades == []

    async def test_close_closes_data_client(self) -> None:
        client = PolymarketClient()
        with (
            patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_gamma,
            patch.object(client._clob_client, "aclose", new_callable=AsyncMock) as mock_clob,
            patch.object(client._data_client, "aclose", new_callable=AsyncMock) as mock_data,
        ):
            await client.close()

        mock_gamma.assert_awaited_once()
        mock_clob.assert_awaited_once()
        mock_data.assert_awaited_once()


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
