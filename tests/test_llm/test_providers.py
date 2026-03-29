"""Tests for src.llm.providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.exceptions import LLMProviderError, LLMRateLimitError
from src.llm.providers import OpenRouterClient, retry_with_backoff
from src.schemas.llm import LLMMessage, LLMRequest, LLMResponse, MessageRole


def _make_request(model: str = "openai/gpt-4o-mini") -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="Hello")],
        model=model,
    )


def _mock_openai_response(
    content: str = "test response",
    model: str = "openai/gpt-4o-mini",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
):
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = model
    return response


class TestOpenRouterClient:
    @pytest.mark.asyncio
    async def test_complete_success(self):
        mock_response = _mock_openai_response()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            client = OpenRouterClient(api_key="test-key")
            result = await client.complete(_make_request())

        assert isinstance(result, LLMResponse)
        assert result.content == "test response"
        assert result.model == "openai/gpt-4o-mini"
        assert result.provider == "openrouter"
        assert result.tokens_in == 10
        assert result.tokens_out == 20
        assert result.cost_usd >= 0

    @pytest.mark.asyncio
    async def test_complete_json_mode(self):
        mock_response = _mock_openai_response(content='{"key": "value"}')
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            client = OpenRouterClient(api_key="test-key")
            request = _make_request()
            request.json_mode = True
            await client.complete(request)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_provider_name(self):
        mock_client = AsyncMock()
        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            client = OpenRouterClient(api_key="test-key")
        assert client.provider_name == "openrouter"


class TestTruncatedResponse:
    @pytest.mark.asyncio
    async def test_truncated_response_warns(self, caplog):
        """When finish_reason='length', provider must emit a WARNING log.

        A truncated response means the model hit max_tokens and the output
        is incomplete. Downstream JSON parsing will likely fail — the warning
        helps diagnose the root cause quickly.
        """
        mock_response = _mock_openai_response()
        mock_response.choices[0].finish_reason = "length"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            client = OpenRouterClient(api_key="test-key")

            import logging

            with caplog.at_level(logging.WARNING, logger="src.llm.providers"):
                result = await client.complete(_make_request())

        assert result.finish_reason == "length"
        # Проверяем, что warning был залогирован
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(
            "length" in msg.lower() or "truncat" in msg.lower() for msg in warning_messages
        ), (
            f"Expected a WARNING log about truncated response (finish_reason='length'), "
            f"but got: {warning_messages}"
        )

    @pytest.mark.asyncio
    async def test_normal_response_no_truncation_warning(self, caplog):
        """When finish_reason='stop', no truncation warning should appear."""
        mock_response = _mock_openai_response()
        mock_response.choices[0].finish_reason = "stop"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            client = OpenRouterClient(api_key="test-key")

            import logging

            with caplog.at_level(logging.WARNING, logger="src.llm.providers"):
                result = await client.complete(_make_request())

        assert result.finish_reason == "stop"
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        truncation_warnings = [
            m for m in warning_messages if "length" in m.lower() or "truncat" in m.lower()
        ]
        assert not truncation_warnings, (
            f"No truncation warning expected for finish_reason='stop', got: {truncation_warnings}"
        )


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        factory = AsyncMock(return_value="ok")
        result = await retry_with_backoff(factory, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_503(self):
        factory = AsyncMock(
            side_effect=[
                LLMProviderError("err", provider="test", status_code=503),
                "ok",
            ]
        )
        result = await retry_with_backoff(factory, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        factory = AsyncMock(
            side_effect=LLMProviderError("unauth", provider="test", status_code=401)
        )
        with pytest.raises(LLMProviderError):
            await retry_with_backoff(factory, max_retries=3, base_delay=0.01)
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        factory = AsyncMock(
            side_effect=[
                LLMRateLimitError("limited", provider="test", retry_after=0.01),
                "ok",
            ]
        )
        result = await retry_with_backoff(factory, max_retries=3, base_delay=0.01)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        factory = AsyncMock(side_effect=LLMProviderError("err", provider="test", status_code=503))
        with pytest.raises(LLMProviderError):
            await retry_with_backoff(factory, max_retries=2, base_delay=0.01)
        assert factory.await_count == 3  # initial + 2 retries
