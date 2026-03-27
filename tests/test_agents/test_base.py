"""Tests for src.agents.base — BaseAgent ABC."""

from __future__ import annotations

import pytest

from src.schemas.agent import AgentResult

# ── Instantiation / structure ────────────────────────────────────────


def test_base_agent_is_abstract():
    from src.agents.base import BaseAgent

    with pytest.raises(TypeError):
        BaseAgent(None)  # type: ignore[abstract]


def test_subclass_without_execute_is_abstract():
    from src.agents.base import BaseAgent

    class Incomplete(BaseAgent):
        name = "incomplete"

    with pytest.raises(TypeError):
        Incomplete(None)  # type: ignore[abstract]


def test_subclass_with_execute_instantiates(DummyAgent, mock_router):
    agent = DummyAgent(mock_router)
    assert agent.name == "dummy"


def test_agent_stores_llm_client(DummyAgent, mock_router):
    agent = DummyAgent(mock_router)
    assert agent.llm is mock_router


def test_agent_logger_name(DummyAgent, mock_router):
    agent = DummyAgent(mock_router)
    assert agent.logger.name == "agent.dummy"


def test_agent_default_timeout(DummyAgent, mock_router):
    agent = DummyAgent(mock_router)
    assert agent.get_timeout_seconds() == 300


# ── run() happy path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_returns_agent_result(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    result = await agent.run(make_context())
    assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_run_success_true_on_normal_execute(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    result = await agent.run(make_context())
    assert result.success is True


@pytest.mark.asyncio
async def test_run_returns_data_from_execute(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    result = await agent.run(make_context())
    assert result.data == {"result": "ok"}


@pytest.mark.asyncio
async def test_run_sets_agent_name(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    result = await agent.run(make_context())
    assert result.agent_name == "dummy"


@pytest.mark.asyncio
async def test_run_records_duration_ms(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    result = await agent.run(make_context())
    assert result.duration_ms >= 0


# ── run() with LLM tracking ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_accumulates_llm_usage(TrackingAgent, mock_router, make_context):
    agent = TrackingAgent(mock_router)
    result = await agent.run(make_context())
    assert result.tokens_in == 300  # 100 + 200
    assert result.tokens_out == 130  # 50 + 80
    assert result.cost_usd == pytest.approx(0.03)  # 0.01 + 0.02


@pytest.mark.asyncio
async def test_run_records_last_llm_model(TrackingAgent, mock_router, make_context):
    agent = TrackingAgent(mock_router)
    result = await agent.run(make_context())
    assert result.llm_model == "model-b"  # last tracked


@pytest.mark.asyncio
async def test_run_resets_tracking_between_calls(TrackingAgent, mock_router, make_context):
    agent = TrackingAgent(mock_router)
    await agent.run(make_context())
    result2 = await agent.run(make_context())
    assert result2.tokens_in == 300  # not 600
    assert result2.cost_usd == pytest.approx(0.03)  # not 0.06


# ── run() error handling ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_returns_false_on_execute_exception(FailingAgent, mock_router, make_context):
    agent = FailingAgent(mock_router)
    result = await agent.run(make_context())
    assert result.success is False


@pytest.mark.asyncio
async def test_run_error_contains_exception_info(FailingAgent, mock_router, make_context):
    agent = FailingAgent(mock_router)
    result = await agent.run(make_context())
    assert "RuntimeError" in result.error
    assert "boom" in result.error


@pytest.mark.asyncio
async def test_run_never_raises(FailingAgent, mock_router, make_context):
    agent = FailingAgent(mock_router)
    result = await agent.run(make_context())
    assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_run_preserves_partial_metrics_on_error(
    PartialTrackingFailAgent, mock_router, make_context
):
    agent = PartialTrackingFailAgent(mock_router)
    result = await agent.run(make_context())
    assert result.success is False
    assert result.tokens_in == 100
    assert result.cost_usd == pytest.approx(0.01)


# ── run() timeout ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_timeout_returns_false(SlowAgent, mock_router, make_context):
    agent = SlowAgent(mock_router)
    result = await agent.run(make_context())
    assert result.success is False


@pytest.mark.asyncio
async def test_run_timeout_error_message(SlowAgent, mock_router, make_context):
    agent = SlowAgent(mock_router)
    result = await agent.run(make_context())
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_run_timeout_records_duration(SlowAgent, mock_router, make_context):
    agent = SlowAgent(mock_router)
    result = await agent.run(make_context())
    assert result.duration_ms >= 900  # ~1 second timeout


# ── validate_context() ───────────────────────────────────────────────


def test_validate_context_default_returns_none(DummyAgent, mock_router, make_context):
    agent = DummyAgent(mock_router)
    assert agent.validate_context(make_context()) is None


@pytest.mark.asyncio
async def test_run_with_validation_error_returns_false(ValidationAgent, mock_router, make_context):
    agent = ValidationAgent(mock_router)
    result = await agent.run(make_context())
    assert result.success is False


@pytest.mark.asyncio
async def test_run_with_validation_error_message(ValidationAgent, mock_router, make_context):
    agent = ValidationAgent(mock_router)
    result = await agent.run(make_context())
    assert "Context validation failed" in result.error
    assert "signals" in result.error


@pytest.mark.asyncio
async def test_run_with_validation_error_skips_execute(ValidationAgent, mock_router, make_context):
    agent = ValidationAgent(mock_router)
    result = await agent.run(make_context())
    assert result.data is None
    assert result.duration_ms == 0
