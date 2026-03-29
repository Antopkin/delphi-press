"""Tests for src.data_sources.wikidata_client."""

from unittest.mock import AsyncMock, patch

import httpx

from src.data_sources.wikidata_client import WikidataResult, wikidata_lookup

_SPARQL_URL = "https://query.wikidata.org/sparql"
_PATCH_TARGET = "src.data_sources.wikidata_client.httpx.AsyncClient"


def _make_mock_client(*, response: httpx.Response | None = None, side_effect=None):
    """Create a mock httpx.AsyncClient with context manager support."""
    client = AsyncMock()
    if side_effect:
        client.get.side_effect = side_effect
    else:
        client.get.return_value = response
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _sparql_response(bindings: list[dict], status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        request=httpx.Request("GET", _SPARQL_URL),
        json={"results": {"bindings": bindings}},
    )


class TestWikidataLookup:
    async def test_known_outlet_returns_result(self):
        """Wikidata SPARQL returns structured result for a known outlet."""
        resp = _sparql_response(
            [
                {
                    "itemLabel": {"value": "ТАСС"},
                    "website": {"value": "https://tass.ru"},
                    "langLabel": {"value": "русский"},
                    "countryLabel": {"value": "Россия"},
                }
            ]
        )
        mock = _make_mock_client(response=resp)

        with patch(_PATCH_TARGET, return_value=mock):
            result = await wikidata_lookup("ТАСС")

        assert result is not None
        assert isinstance(result, WikidataResult)
        assert result.name == "ТАСС"
        assert result.website_url == "https://tass.ru"

    async def test_unknown_name_returns_none(self):
        """Unknown outlet name returns None (empty bindings)."""
        mock = _make_mock_client(response=_sparql_response([]))

        with patch(_PATCH_TARGET, return_value=mock):
            result = await wikidata_lookup("ывапрол")

        assert result is None

    async def test_timeout_returns_none(self):
        """HTTP timeout is handled gracefully."""
        mock = _make_mock_client(side_effect=httpx.ConnectTimeout("timeout"))

        with patch(_PATCH_TARGET, return_value=mock):
            result = await wikidata_lookup("ТАСС")

        assert result is None

    async def test_malformed_response_returns_none(self):
        """Non-JSON or missing 'results' key is handled."""
        resp = httpx.Response(
            200,
            request=httpx.Request("GET", _SPARQL_URL),
            json={"unexpected": "structure"},
        )
        mock = _make_mock_client(response=resp)

        with patch(_PATCH_TARGET, return_value=mock):
            result = await wikidata_lookup("ТАСС")

        assert result is None
