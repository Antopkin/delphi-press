"""LLM-провайдеры: OpenRouter, Claude Code SDK, retry-логика.

Спека: docs-site/docs/architecture/llm.md (§2).
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
from src.schemas.llm import LLMMessage, LLMRequest, LLMResponse, MessageRole

# Claude Code SDK — lazy import to avoid hard dependency for OpenRouter-only setups
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKError,
        ResultMessage,
        query,
    )

    _HAS_CLAUDE_SDK = True
except ImportError:
    _HAS_CLAUDE_SDK = False

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


# OpenRouter reserves credits based on max_tokens; omitting it reserves the
# model's full output capacity (e.g. 64000 for Opus), which can exhaust
# low-balance accounts unnecessarily.  16384 covers every pipeline task.
_DEFAULT_MAX_TOKENS = 16_384


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
                    "top_p": request.top_p,
                }
                kwargs["max_tokens"] = request.max_tokens or _DEFAULT_MAX_TOKENS
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


class ClaudeCodeProvider(LLMProvider):
    """Claude Code SDK provider — биллинг через Max подписку.

    Использует claude-agent-sdk для маршрутизации LLM-вызовов через
    Claude Code CLI. Каждый вызов complete() порождает subprocess.
    """

    _MODEL_MAP: dict[str, str] = {
        "anthropic/claude-opus-4.6": "claude-opus-4-6",
        "anthropic/claude-sonnet-4.6": "claude-sonnet-4-6",
        "anthropic/claude-sonnet-4.5": "claude-sonnet-4-5",
    }

    def __init__(self, *, max_concurrency: int = 1) -> None:
        if not _HAS_CLAUDE_SDK:
            msg = "claude-agent-sdk required. Install: uv add claude-agent-sdk"
            raise ImportError(msg)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_retries = 2
        self._retry_delay = 5.0

    def _map_model(self, openrouter_id: str) -> str:
        """Маппит OpenRouter model ID на Claude Code формат."""
        try:
            return self._MODEL_MAP[openrouter_id]
        except KeyError:
            raise LLMProviderError(
                f"Unsupported model '{openrouter_id}' for Claude Code. "
                f"Supported: {list(self._MODEL_MAP)}",
                provider="claude_code",
            ) from None

    @staticmethod
    def _extract_messages(
        messages: list[LLMMessage],
    ) -> tuple[str | None, str]:
        """Извлекает system_prompt и user prompt из списка сообщений."""
        system_parts: list[str] = []
        user_parts: list[str] = []
        for m in messages:
            if m.role == MessageRole.SYSTEM:
                system_parts.append(m.content)
            else:
                user_parts.append(m.content)
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        prompt = "\n\n".join(user_parts)
        return system_prompt, prompt

    @staticmethod
    def _stderr_handler(line: str) -> None:
        """Логирует stderr от Claude Code CLI."""
        if line.strip():
            logger.debug("claude-cli stderr: %s", line.rstrip())

    # Instruction appended to every system prompt to suppress tool-use attempts.
    # Claude Code CLI always injects tool definitions into the model context even
    # with `--tools ""`.  The model may generate tool_use blocks (especially for
    # web-search on forecasting prompts), consuming turns and sometimes causing
    # exit code 1.  A deterministic SDK-level disable doesn't exist (see
    # _build_options), so we reinforce with a prompt-level constraint.
    _NO_TOOLS_INSTRUCTION: str = (
        "\n\n<constraints>\n"
        "CRITICAL: You do NOT have access to any tools, web search, file operations, "
        "or external resources in this session. Tool definitions visible in the system "
        "context are disabled and will fail if invoked. Respond with text only. "
        "Never emit tool_use blocks.\n"
        "</constraints>"
    )

    def _build_options(self, request: LLMRequest, system_prompt: str | None) -> ClaudeAgentOptions:
        """Строит ClaudeAgentOptions из LLMRequest.

        Цель — pure LLM completion без agent loop.  Три уровня защиты:
        1. `tools=[]` → CLI получает `--tools ""` → built-in tools отключены.
        2. `disallowed_tools=["*"]` → wildcard deny для всех tools (built-in + MCP).
        3. `_NO_TOOLS_INSTRUCTION` в system prompt → модель не генерирует tool_use.
        4. `max_turns=1` → даже если модель попытается tool_use, CLI не пойдёт
           во второй turn.  Extended thinking НЕ считается отдельным turn.

        `setting_sources=["user"]` сохранён для OAuth auth (Max подписка).
        `mcp_servers={}` не подгружает MCP из SDK, но user settings могут
        добавить свои серверы — их блокирует disallowed_tools wildcard.
        """
        hardened_system = (system_prompt or "") + self._NO_TOOLS_INSTRUCTION
        if request.json_mode:
            hardened_system += "\nRespond in valid JSON only. No markdown, no preamble."

        return ClaudeAgentOptions(
            system_prompt=hardened_system,
            model=self._map_model(request.model),
            setting_sources=["user"],
            tools=[],
            disallowed_tools=["*"],
            mcp_servers={},
            max_turns=1,
            permission_mode="plan",
            stderr=self._stderr_handler,
            extra_args={
                "strict-mcp-config": None,
                "no-session-persistence": None,
            },
            env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Выполнить LLM-вызов через Claude Code SDK с retry."""
        system_prompt, prompt = self._extract_messages(request.messages)
        options = self._build_options(request, system_prompt)

        result_msg: ResultMessage | None = None

        for attempt in range(self._max_retries + 1):
            result_msg = None
            sdk_error: Exception | None = None

            async with self._semaphore:
                try:
                    async for msg in query(prompt=prompt, options=options):
                        if isinstance(msg, ResultMessage):
                            result_msg = msg
                except ClaudeSDKError as e:
                    sdk_error = e
                except Exception as e:
                    sdk_error = e

            # Retry logic — sleep OUTSIDE semaphore to not block other tasks
            if sdk_error is not None:
                if attempt < self._max_retries:
                    delay = self._retry_delay * (2**attempt)
                    logger.warning(
                        "Claude Code call failed (attempt %d/%d), retrying in %.0fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        sdk_error,
                    )
                    await asyncio.sleep(delay)
                    continue
                if isinstance(sdk_error, ClaudeSDKError):
                    raise LLMProviderError(str(sdk_error), provider="claude_code") from sdk_error
                raise LLMProviderError(
                    f"Unexpected error from Claude Code: {sdk_error}",
                    provider="claude_code",
                ) from sdk_error

            if result_msg is None:
                if attempt < self._max_retries:
                    logger.warning(
                        "No ResultMessage (attempt %d/%d), retrying...",
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise LLMProviderError(
                    "No ResultMessage received from Claude Code", provider="claude_code"
                )

            # tool_use detection — model tried to call a tool despite constraints
            if result_msg.stop_reason == "tool_use" or (
                not result_msg.result and result_msg.is_error
            ):
                if attempt < self._max_retries:
                    logger.warning(
                        "Claude Code returned tool_use/empty (attempt %d/%d), retrying...",
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    await asyncio.sleep(self._retry_delay)
                    continue
                if result_msg.is_error:
                    error_text = "; ".join(result_msg.errors or ["tool_use with empty result"])
                    raise LLMProviderError(error_text, provider="claude_code")

            if result_msg.is_error:
                error_text = "; ".join(result_msg.errors or ["Unknown error"])
                if attempt < self._max_retries:
                    logger.warning(
                        "Claude Code error (attempt %d/%d): %s",
                        attempt + 1,
                        self._max_retries + 1,
                        error_text,
                    )
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise LLMProviderError(error_text, provider="claude_code")

            break  # success

        usage = result_msg.usage or {}
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        cost = calculate_cost(request.model, tokens_in=tokens_in, tokens_out=tokens_out)

        return LLMResponse(
            content=result_msg.result or "",
            model=request.model,
            provider="claude_code",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            duration_ms=result_msg.duration_ms,
            finish_reason=(
                "stop"
                if result_msg.stop_reason in ("end_turn", None)
                else result_msg.stop_reason or "stop"
            ),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # noqa: RET503

    @property
    def provider_name(self) -> str:
        return "claude_code"
