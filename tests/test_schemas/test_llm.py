"""Tests for src.schemas.llm — LLM request/response schemas."""

import pytest
from pydantic import ValidationError

from src.schemas.llm import (
    CostRecord,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ModelAssignment,
)

# ── MessageRole ──────────────────────────────────────────────────────


def test_message_role_is_str_enum():
    assert isinstance(MessageRole.SYSTEM, str)
    assert MessageRole.SYSTEM == "system"
    assert MessageRole.USER == "user"
    assert MessageRole.ASSISTANT == "assistant"


# ── LLMRequest ───────────────────────────────────────────────────────


def _llm_request_kwargs(**overrides) -> dict:
    defaults = {
        "messages": [LLMMessage(role=MessageRole.USER, content="Hello")],
        "model": "anthropic/claude-sonnet-4",
    }
    defaults.update(overrides)
    return defaults


def test_llm_request_temperature_bounds_valid():
    req = LLMRequest(**_llm_request_kwargs(temperature=1.5))
    assert req.temperature == 1.5


def test_llm_request_temperature_above_2_rejected():
    with pytest.raises(ValidationError):
        LLMRequest(**_llm_request_kwargs(temperature=2.1))


def test_llm_request_temperature_below_0_rejected():
    with pytest.raises(ValidationError):
        LLMRequest(**_llm_request_kwargs(temperature=-0.1))


def test_llm_request_max_tokens_bounds_valid():
    req = LLMRequest(**_llm_request_kwargs(max_tokens=128_000))
    assert req.max_tokens == 128_000


def test_llm_request_max_tokens_above_limit_rejected():
    with pytest.raises(ValidationError):
        LLMRequest(**_llm_request_kwargs(max_tokens=128_001))


def test_llm_request_max_tokens_below_1_rejected():
    with pytest.raises(ValidationError):
        LLMRequest(**_llm_request_kwargs(max_tokens=0))


def test_llm_request_max_tokens_none_allowed():
    """None means 'let the model decide' — no limit sent to API."""
    req = LLMRequest(**_llm_request_kwargs(max_tokens=None))
    assert req.max_tokens is None


# ── LLMResponse ──────────────────────────────────────────────────────


def _llm_response_kwargs(**overrides) -> dict:
    defaults = {
        "content": "Response text",
        "model": "anthropic/claude-sonnet-4",
        "provider": "openrouter",
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.01,
        "duration_ms": 500,
    }
    defaults.update(overrides)
    return defaults


def test_llm_response_total_tokens():
    r = LLMResponse(**_llm_response_kwargs())
    assert r.total_tokens == 150


def test_llm_response_tokens_per_second():
    r = LLMResponse(**_llm_response_kwargs(tokens_out=100, duration_ms=2000))
    assert r.tokens_per_second == pytest.approx(50.0)


def test_llm_response_tokens_per_second_zero_duration():
    r = LLMResponse(**_llm_response_kwargs(duration_ms=0))
    assert r.tokens_per_second == 0.0


# ── CostRecord ───────────────────────────────────────────────────────


def test_cost_record_instantiation():
    cr = CostRecord(
        prediction_id="pred-001",
        stage="delphi_r1",
        model="anthropic/claude-sonnet-4",
        provider="openrouter",
    )
    assert cr.stage == "delphi_r1"
    assert cr.tokens_in == 0


# ── ModelAssignment ──────────────────────────────────────────────────


def test_model_assignment_instantiation():
    ma = ModelAssignment(
        task="delphi_persona",
        primary_model="anthropic/claude-sonnet-4",
    )
    assert ma.provider == "openrouter"
    assert ma.fallback_models == []
