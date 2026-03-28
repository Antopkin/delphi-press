"""Tests for src.data_sources.web_search."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.data_sources.web_search import ExaSearchProvider, JinaSearchProvider, WebSearchService

EXA_RESPONSE = {
    "results": [
        {
            "title": "Test Article",
            "url": "https://example.com/1",
            "text": "Some content here.",
            "publishedDate": "2025-03-24T12:00:00Z",
        },
        {
            "title": "Another Article",
            "url": "https://example.com/2",
            "text": "More content.",
        },
    ]
}

JINA_RESPONSE = {
    "data": [
        {
            "title": "Jina Result",
            "url": "https://example.com/3",
            "description": "Found via Jina.",
        },
    ]
}


class TestExaSearchProvider:
    @pytest.mark.asyncio
    async def test_search(self):
        provider = ExaSearchProvider("test-key")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            provider._client, "post", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("test query")

        assert len(results) == 2
        assert results[0].title == "Test Article"
        assert results[0].url == "https://example.com/1"
        assert results[0].published_at is not None

    @pytest.mark.asyncio
    async def test_search_error(self):
        provider = ExaSearchProvider("test-key")
        with patch.object(
            provider._client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            results = await provider.search("test query")
        assert results == []


class TestJinaSearchProvider:
    @pytest.mark.asyncio
    async def test_search(self):
        provider = JinaSearchProvider("test-key")
        mock_response = httpx.Response(
            200,
            json=JINA_RESPONSE,
            request=httpx.Request("GET", "https://s.jina.ai/test"),
        )
        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("test query")

        assert len(results) == 1
        assert results[0].title == "Jina Result"


class TestWebSearchService:
    @pytest.mark.asyncio
    async def test_search_with_exa(self):
        service = WebSearchService(exa_api_key="test-exa")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            results = await service.search("test")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_no_providers(self):
        service = WebSearchService()
        results = await service.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_fallback_to_jina(self):
        service = WebSearchService(exa_api_key="exa", jina_api_key="jina")
        # Exa fails
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("exa down"),
        ):
            mock_jina = httpx.Response(
                200,
                json=JINA_RESPONSE,
                request=httpx.Request("GET", "https://s.jina.ai/test"),
            )
            with patch.object(
                service._providers[1]._client,
                "get",
                new_callable=AsyncMock,
                return_value=mock_jina,
            ):
                results = await service.search("test")

        assert len(results) == 1
        assert results[0].title == "Jina Result"

    @pytest.mark.asyncio
    async def test_multi_search_dedup(self):
        service = WebSearchService(exa_api_key="test")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        with patch.object(
            service._providers[0]._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            results = await service.multi_search(["query1", "query2"])

        # Same results from both queries → should dedup
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        service = WebSearchService(exa_api_key="test")
        mock_response = httpx.Response(
            200,
            json=EXA_RESPONSE,
            request=httpx.Request("POST", "https://api.exa.ai/search"),
        )
        mock_post = AsyncMock(return_value=mock_response)
        with patch.object(service._providers[0]._client, "post", mock_post):
            await service.search("same query")
            await service.search("same query")

        assert mock_post.await_count == 1
