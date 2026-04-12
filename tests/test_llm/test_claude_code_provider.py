"""Tests for ClaudeCodeProvider — Claude Code SDK LLM provider.

TDD: каж��ый тест добавляется по одному, Red → Green → Refactor.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.llm.exceptions import LLMProviderError
from src.llm.providers import ClaudeCodeProvider
from src.schemas.llm import LLMMessage, LLMRequest, MessageRole


class TestModelMapping:
    """Cycle 1: Provider маппит OpenRouter model IDs на Claude Code формат."""

    def test_maps_opus_46(self) -> None:
        provider = ClaudeCodeProvider()
        assert provider._map_model("anthropic/claude-opus-4.6") == "claude-opus-4-6"

    def test_maps_sonnet_46(self) -> None:
        provider = ClaudeCodeProvider()
        assert provider._map_model("anthropic/claude-sonnet-4.6") == "claude-sonnet-4-6"

    def test_maps_sonnet_45(self) -> None:
        provider = ClaudeCodeProvider()
        assert provider._map_model("anthropic/claude-sonnet-4.5") == "claude-sonnet-4-5"

    def test_unknown_model_raises(self) -> None:
        provider = ClaudeCodeProvider()
        with pytest.raises(KeyError):
            provider._map_model("google/gemini-2.5-flash")


class TestMessageExtraction:
    """Cycle 2: Provider извлекает system_prompt и user_prompt из messages."""

    def test_extracts_system_and_user(self) -> None:
        provider = ClaudeCodeProvider()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are a forecaster."),
            LLMMessage(role=MessageRole.USER, content="Analyze events."),
        ]
        system_prompt, prompt = provider._extract_messages(messages)
        assert system_prompt == "You are a forecaster."
        assert prompt == "Analyze events."

    def test_multiple_system_messages_concatenated(self) -> None:
        provider = ClaudeCodeProvider()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="Role: analyst."),
            LLMMessage(role=MessageRole.SYSTEM, content="Focus: geopolitics."),
            LLMMessage(role=MessageRole.USER, content="Go."),
        ]
        system_prompt, prompt = provider._extract_messages(messages)
        assert "Role: analyst." in system_prompt
        assert "Focus: geopolitics." in system_prompt
        assert prompt == "Go."

    def test_no_system_message(self) -> None:
        provider = ClaudeCodeProvider()
        messages = [
            LLMMessage(role=MessageRole.USER, content="Hello."),
        ]
        system_prompt, prompt = provider._extract_messages(messages)
        assert system_prompt is None
        assert prompt == "Hello."


class TestComplete:
    """Cycle 3: Provider вызывает query() �� парсит ResultMessage в LLMResponse."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a forecaster."),
                LLMMessage(role=MessageRole.USER, content="Analyze."),
            ],
            model="anthropic/claude-opus-4.6",
            temperature=0.7,
            json_mode=True,
        )

    @pytest.fixture()
    def mock_result_message(self) -> object:
        """Fake ResultMessage dataclass."""
        from claude_agent_sdk import ResultMessage

        return ResultMessage(
            subtype="result",
            duration_ms=5000,
            duration_api_ms=4500,
            is_error=False,
            num_turns=1,
            session_id="sess-123",
            total_cost_usd=0.0,
            usage={"input_tokens": 800, "output_tokens": 200},
            result='{"headlines": ["test headline"]}',
        )

    @pytest.mark.asyncio()
    async def test_complete_returns_llm_response(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
        mock_result_message: object,
    ) -> None:
        async def mock_query(**kwargs):  # noqa: ARG001
            yield mock_result_message

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.content == '{"headlines": ["test headline"]}'
        assert response.model == "anthropic/claude-opus-4.6"
        assert response.provider == "claude_code"
        assert response.tokens_in == 800
        assert response.tokens_out == 200
        assert response.duration_ms == 5000
        assert response.cost_usd >= 0.0

    @pytest.mark.asyncio()
    async def test_sdk_error_maps_to_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        from claude_agent_sdk import ProcessError

        async def mock_query(**kwargs):  # noqa: ARG001
            raise ProcessError("CLI crashed")
            yield  # noqa: RET503 — make it an async generator

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="CLI crashed"):
                await provider.complete(request_opus)

    @pytest.mark.asyncio()
    async def test_error_result_raises_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        from claude_agent_sdk import ResultMessage

        error_msg = ResultMessage(
            subtype="result",
            duration_ms=100,
            duration_api_ms=80,
            is_error=True,
            num_turns=1,
            session_id="sess-err",
            errors=["Budget exceeded"],
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield error_msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="Budget exceeded"):
                await provider.complete(request_opus)
