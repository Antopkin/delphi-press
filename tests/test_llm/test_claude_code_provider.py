"""Tests for ClaudeCodeProvider — Claude Code SDK LLM provider.

TDD: каждый тест добавляется по одному, Red → Green → Refactor.
"""

from __future__ import annotations

from unittest.mock import patch

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

    def test_unknown_model_raises_provider_error(self) -> None:
        provider = ClaudeCodeProvider()
        with pytest.raises(LLMProviderError, match="Unsupported model"):
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


class TestNoResultMessage:
    """Cycle 4: query() yields only AssistantMessage, no ResultMessage → LLMProviderError."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.USER, content="Analyze."),
            ],
            model="anthropic/claude-opus-4.6",
            temperature=0.7,
        )

    @pytest.mark.asyncio()
    async def test_no_result_message_raises_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """query() returns only AssistantMessage → should raise LLMProviderError."""
        from claude_agent_sdk import AssistantMessage, TextBlock

        assistant_msg = AssistantMessage(
            content=[TextBlock(text="thinking...")],
            model="claude-opus-4-6",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield assistant_msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="No ResultMessage"):
                await provider.complete(request_opus)

    @pytest.mark.asyncio()
    async def test_empty_stream_raises_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """query() yields nothing at all → should raise LLMProviderError."""

        async def mock_query(**kwargs):  # noqa: ARG001
            return
            yield  # noqa: RET503 — make it an async generator

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="No ResultMessage"):
                await provider.complete(request_opus)


class TestUsageNone:
    """Cycle 5: ResultMessage with usage=None → tokens default to 0."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.USER, content="Analyze."),
            ],
            model="anthropic/claude-opus-4.6",
            temperature=0.7,
        )

    @pytest.mark.asyncio()
    async def test_usage_none_defaults_tokens_to_zero(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """ResultMessage with usage=None → tokens_in=0, tokens_out=0, cost_usd=0.0."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=3000,
            duration_api_ms=2500,
            is_error=False,
            num_turns=1,
            session_id="sess-no-usage",
            usage=None,
            result="Some output",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.tokens_in == 0
        assert response.tokens_out == 0
        assert response.cost_usd == 0.0

    @pytest.mark.asyncio()
    async def test_usage_partial_keys_default_missing_to_zero(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """usage dict missing output_tokens → tokens_out should be 0."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=3000,
            duration_api_ms=2500,
            is_error=False,
            num_turns=1,
            session_id="sess-partial",
            usage={"input_tokens": 500},
            result="Partial usage",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.tokens_in == 500
        assert response.tokens_out == 0


class TestTotalCostNone:
    """Cycle 6: ResultMessage with total_cost_usd=None (Max subscription) → cost calculated."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.USER, content="Analyze."),
            ],
            model="anthropic/claude-opus-4.6",
            temperature=0.7,
        )

    @pytest.mark.asyncio()
    async def test_total_cost_none_uses_calculated_cost(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """Max subscription: total_cost_usd=None → cost_usd from calculate_cost()."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=4000,
            duration_api_ms=3500,
            is_error=False,
            num_turns=1,
            session_id="sess-max",
            total_cost_usd=None,
            usage={"input_tokens": 1000, "output_tokens": 500},
            result="Result with Max subscription",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        # Opus 4.6: $5/1M in, $25/1M out
        expected_cost = (1000 / 1_000_000 * 5.0) + (500 / 1_000_000 * 25.0)
        assert response.cost_usd == pytest.approx(expected_cost, abs=1e-9)


class TestStreamNotImplemented:
    """Cycle 7: stream() should raise NotImplementedError."""

    @pytest.mark.asyncio()
    async def test_stream_raises_not_implemented(self) -> None:
        provider = ClaudeCodeProvider()
        request = LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.USER, content="Hello."),
            ],
            model="anthropic/claude-opus-4.6",
        )
        with pytest.raises(NotImplementedError):
            async for _ in provider.stream(request):
                pass


class TestProviderName:
    """Cycle 8: provider_name returns 'claude_code'."""

    def test_provider_name_returns_claude_code(self) -> None:
        provider = ClaudeCodeProvider()
        assert provider.provider_name == "claude_code"


class TestBuildOptions:
    """Cycle 9: _build_options() sets isolation options for subagent."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    def test_build_options_setting_sources_user_only(self, provider: ClaudeCodeProvider) -> None:
        """setting_sources=["user"] for OAuth auth, without project/local configs."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt="System prompt")
        assert options.setting_sources == ["user"]

    def test_build_options_tools_empty(self, provider: ClaudeCodeProvider) -> None:
        """tools must be [] — subagent is a pure LLM, no tool use."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt=None)
        assert options.tools == []

    def test_build_options_max_turns_one(self, provider: ClaudeCodeProvider) -> None:
        """max_turns must be 1 — single-shot, no agentic loops."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt=None)
        assert options.max_turns == 1

    def test_build_options_permission_mode_plan(self, provider: ClaudeCodeProvider) -> None:
        """permission_mode must be 'plan' — read-only, no destructive actions."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt=None)
        assert options.permission_mode == "plan"

    def test_build_options_model_mapped(self, provider: ClaudeCodeProvider) -> None:
        """Model should be mapped from OpenRouter ID to Claude Code format."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-sonnet-4.5",
        )
        options = provider._build_options(request, system_prompt=None)
        assert options.model == "claude-sonnet-4-5"

    def test_build_options_system_prompt_passed(self, provider: ClaudeCodeProvider) -> None:
        """System prompt should be forwarded with _NO_TOOLS_INSTRUCTION appended."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt="Be a forecaster.")
        assert options.system_prompt.startswith("Be a forecaster.")
        assert "<constraints>" in options.system_prompt
        assert "Never emit tool_use blocks" in options.system_prompt

    def test_build_options_system_prompt_none(self, provider: ClaudeCodeProvider) -> None:
        """system_prompt=None still gets _NO_TOOLS_INSTRUCTION."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt=None)
        assert options.system_prompt is not None
        assert "<constraints>" in options.system_prompt

    def test_build_options_extra_args_strict_mcp(self, provider: ClaudeCodeProvider) -> None:
        """strict-mcp-config prevents user MCP servers from loading."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )
        options = provider._build_options(request, system_prompt=None)
        assert "strict-mcp-config" in options.extra_args
        assert "no-session-persistence" in options.extra_args

    def test_build_options_json_mode_instruction(self, provider: ClaudeCodeProvider) -> None:
        """json_mode=True adds JSON-only instruction to system prompt."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
            json_mode=True,
        )
        options = provider._build_options(request, system_prompt="Analyst.")
        assert "valid JSON only" in options.system_prompt


class TestEmptyMessages:
    """Cycle 10: Empty messages list → should handle gracefully."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    def test_extract_messages_empty_list(self, provider: ClaudeCodeProvider) -> None:
        """Empty messages → system_prompt=None, prompt=''."""
        system_prompt, prompt = provider._extract_messages([])
        assert system_prompt is None
        assert prompt == ""

    @pytest.mark.asyncio()
    async def test_complete_empty_messages_sends_empty_prompt(
        self,
        provider: ClaudeCodeProvider,
    ) -> None:
        """complete() with empty messages should still call query with empty prompt."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=1000,
            duration_api_ms=900,
            is_error=False,
            num_turns=1,
            session_id="sess-empty",
            usage={"input_tokens": 10, "output_tokens": 5},
            result="OK",
        )

        captured_kwargs: dict = {}

        async def mock_query(**kwargs):
            captured_kwargs.update(kwargs)
            yield msg

        request = LLMRequest(
            messages=[],
            model="anthropic/claude-opus-4.6",
        )

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request)

        assert response.content == "OK"
        assert captured_kwargs["prompt"] == ""


class TestImportGuard:
    """Cycle 11: ClaudeCodeProvider() without SDK installed → ImportError."""

    def test_no_sdk_raises_import_error(self) -> None:
        """When _HAS_CLAUDE_SDK is False, __init__ should raise ImportError."""
        with patch("src.llm.providers._HAS_CLAUDE_SDK", False):
            with pytest.raises(ImportError, match="claude-agent-sdk required"):
                ClaudeCodeProvider()


class TestStopReasonMapping:
    """Cycle 12: finish_reason mapping from SDK stop_reason."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Analyze.")],
            model="anthropic/claude-opus-4.6",
        )

    @pytest.mark.asyncio()
    async def test_stop_reason_end_turn_maps_to_stop(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """stop_reason='end_turn' → finish_reason='stop'."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=1,
            session_id="sess-end-turn",
            stop_reason="end_turn",
            usage={"input_tokens": 100, "output_tokens": 50},
            result="Done",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.finish_reason == "stop"

    @pytest.mark.asyncio()
    async def test_stop_reason_none_maps_to_stop(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """stop_reason=None → finish_reason='stop'."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=1,
            session_id="sess-none-stop",
            stop_reason=None,
            usage={"input_tokens": 100, "output_tokens": 50},
            result="Done",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.finish_reason == "stop"

    @pytest.mark.asyncio()
    async def test_stop_reason_max_tokens_preserved(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """stop_reason='max_tokens' → finish_reason='max_tokens' (not 'stop')."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=1,
            session_id="sess-max-tok",
            stop_reason="max_tokens",
            usage={"input_tokens": 100, "output_tokens": 50},
            result="Truncated output",
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.finish_reason == "max_tokens"

    @pytest.mark.asyncio()
    async def test_result_none_defaults_to_empty_string(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """result=None → content='' (empty string, not None)."""
        from claude_agent_sdk import ResultMessage

        msg = ResultMessage(
            subtype="result",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=1,
            session_id="sess-no-result",
            usage={"input_tokens": 100, "output_tokens": 0},
            result=None,
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield msg

        with patch("src.llm.providers.query", side_effect=mock_query):
            response = await provider.complete(request_opus)

        assert response.content == ""


class TestConcurrencySemaphore:
    """Cycle 13: max_concurrency parameter controls semaphore."""

    def test_default_concurrency_is_one(self) -> None:
        """Sequential by default — avoids Max subscription rate limiting."""
        provider = ClaudeCodeProvider()
        assert provider._semaphore._value == 1

    def test_custom_concurrency(self) -> None:
        provider = ClaudeCodeProvider(max_concurrency=2)
        assert provider._semaphore._value == 2


class TestNonSDKExceptions:
    """Cycle 14: Non-ClaudeSDKError exceptions should be wrapped in LLMProviderError.

    BUG: Current implementation only catches ClaudeSDKError. A RuntimeError,
    ConnectionError, or asyncio.TimeoutError from the SDK subprocess will
    propagate unwrapped — breaking the LLMProvider contract that all errors
    come back as LLMProviderError.

    Expected: FAIL (RED) — requires implementation fix.
    """

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.fixture()
    def request_opus(self) -> LLMRequest:
        return LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Analyze.")],
            model="anthropic/claude-opus-4.6",
        )

    @pytest.mark.asyncio()
    async def test_runtime_error_wrapped_in_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """RuntimeError from query() should be wrapped in LLMProviderError."""

        async def mock_query(**kwargs):  # noqa: ARG001
            raise RuntimeError("subprocess pipe broken")
            yield  # noqa: RET503

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="subprocess pipe broken"):
                await provider.complete(request_opus)

    @pytest.mark.asyncio()
    async def test_connection_error_wrapped_in_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """ConnectionError from query() should be wrapped in LLMProviderError."""

        async def mock_query(**kwargs):  # noqa: ARG001
            raise ConnectionError("CLI not reachable")
            yield  # noqa: RET503

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="CLI not reachable"):
                await provider.complete(request_opus)

    @pytest.mark.asyncio()
    async def test_os_error_wrapped_in_provider_error(
        self,
        provider: ClaudeCodeProvider,
        request_opus: LLMRequest,
    ) -> None:
        """OSError (e.g. CLI binary not found) should be wrapped in LLMProviderError."""

        async def mock_query(**kwargs):  # noqa: ARG001
            raise OSError("claude binary not found")
            yield  # noqa: RET503

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError, match="claude binary not found"):
                await provider.complete(request_opus)


class TestUnmappedModelInComplete:
    """Cycle 15: complete() with unmapped model → should raise LLMProviderError, not KeyError.

    BUG: _build_options() calls _map_model() which raises bare KeyError for
    unknown models. The KeyError is not caught in complete(), so it propagates
    as-is — breaking the LLMProvider contract.

    Expected: FAIL (RED) — requires implementation fix.
    """

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.mark.asyncio()
    async def test_unmapped_model_raises_provider_error(
        self,
        provider: ClaudeCodeProvider,
    ) -> None:
        """complete() with unmapped model should raise LLMProviderError, not KeyError."""
        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="google/gemini-2.5-flash",
        )
        with pytest.raises(LLMProviderError, match="google/gemini-2.5-flash"):
            await provider.complete(request)


class TestErrorResultProviderAttribute:
    """Cycle 16: LLMProviderError from error result has provider='claude_code'."""

    @pytest.fixture()
    def provider(self) -> ClaudeCodeProvider:
        return ClaudeCodeProvider()

    @pytest.mark.asyncio()
    async def test_error_result_has_provider_attribute(
        self,
        provider: ClaudeCodeProvider,
    ) -> None:
        """LLMProviderError raised for is_error=True should have provider='claude_code'."""
        from claude_agent_sdk import ResultMessage

        error_msg = ResultMessage(
            subtype="result",
            duration_ms=100,
            duration_api_ms=80,
            is_error=True,
            num_turns=1,
            session_id="sess-err-attr",
            errors=["Token limit"],
        )

        async def mock_query(**kwargs):  # noqa: ARG001
            yield error_msg

        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(request)

        assert exc_info.value.provider == "claude_code"

    @pytest.mark.asyncio()
    async def test_no_result_error_has_provider_attribute(
        self,
        provider: ClaudeCodeProvider,
    ) -> None:
        """LLMProviderError for missing ResultMessage should have provider='claude_code'."""

        async def mock_query(**kwargs):  # noqa: ARG001
            return
            yield  # noqa: RET503

        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Go.")],
            model="anthropic/claude-opus-4.6",
        )

        with patch("src.llm.providers.query", side_effect=mock_query):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(request)

        assert exc_info.value.provider == "claude_code"
