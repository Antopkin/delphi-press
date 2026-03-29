"""LLM-провайдеры: OpenRouter, retry-логика.

Спека: docs/07-llm-layer.md (§2).
Контракт: LLMProvider.complete(LLMRequest) → LLMResponse.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from src.llm.exceptions import LLMProviderError, LLMRateLimitError
from src.llm.pricing import calculate_cost
from src.schemas.llm import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Абстрактный LLM-провайдер."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...


async def retry_with_backoff(
    coro_factory: Any,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_status_codes: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
) -> Any:
    """Выполнить корутину с exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except LLMRateLimitError as e:
            if attempt == max_retries:
                raise
            delay = e.retry_after or min(base_delay * (2**attempt), max_delay)
            await asyncio.sleep(delay + random.uniform(0, base_delay / 2))
        except LLMProviderError as e:
            if attempt == max_retries:
                raise
            if e.status_code not in retryable_status_codes:
                raise
            delay = min(base_delay * (2**attempt), max_delay)
            await asyncio.sleep(delay + random.uniform(0, base_delay / 2))


class OpenRouterClient(LLMProvider):
    """Клиент OpenRouter — OpenAI-совместимый API."""

    def __init__(
        self,
        api_key: str,
        *,
        default_headers: dict[str, str] | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://delphi.antopkin.ru",
                "X-Title": "Delphi Press",
                **(default_headers or {}),
            },
            max_retries=0,
            timeout=timeout_seconds,
        )
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming вызов с retry."""
        start = time.monotonic()

        async def _call() -> Any:
            try:
                kwargs: dict[str, Any] = {
                    "model": request.model,
                    "messages": [
                        {"role": m.role.value, "content": m.content} for m in request.messages
                    ],
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "top_p": request.top_p,
                }
                if request.json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                if request.stop_sequences:
                    kwargs["stop"] = request.stop_sequences
                return await self._client.chat.completions.create(**kwargs)
            except Exception as e:
                status = getattr(e, "status_code", None)
                if status == 429:
                    retry_after = getattr(e, "retry_after", None)
                    raise LLMRateLimitError(
                        str(e), provider="openrouter", retry_after=retry_after
                    ) from e
                if isinstance(status, int):
                    raise LLMProviderError(
                        str(e), provider="openrouter", status_code=status
                    ) from e
                raise LLMProviderError(str(e), provider="openrouter") from e

        response = await retry_with_backoff(
            _call,
            max_retries=self._max_retries,
            base_delay=self._retry_base_delay,
            max_delay=self._retry_max_delay,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        cost = calculate_cost(request.model, tokens_in, tokens_out)
        finish_reason = response.choices[0].finish_reason or "stop"

        # Warn about truncated responses — downstream JSON parsing will likely fail
        if finish_reason == "length":
            logger.warning(
                "llm_response_truncated: finish_reason='length' — response hit max_tokens "
                "and may be incomplete",
                extra={
                    "model": request.model,
                    "max_tokens": request.max_tokens,
                    "tokens_out": tokens_out,
                },
            )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=request.model,
            provider="openrouter",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            duration_ms=duration_ms,
            finish_reason=finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Streaming вызов. Yields текстовые чанки."""
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        try:
            response = await self._client.chat.completions.create(**kwargs)
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMProviderError(str(e), provider="openrouter") from e

    @property
    def provider_name(self) -> str:
        return "openrouter"
