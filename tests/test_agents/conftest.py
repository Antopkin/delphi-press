"""Shared fixtures for agents-core tests."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.llm.router import ModelRouter
from src.schemas.pipeline import PipelineContext

# ── Mock LLM router ─────────────────────────────────────────────────


@pytest.fixture
def mock_router():
    router = AsyncMock(spec=ModelRouter)
    return router


# ── Pipeline context factory ─────────────────────────────────────────


@pytest.fixture
def make_context():
    def _factory(**kwargs):
        defaults = {"outlet": "TASS", "target_date": date(2026, 4, 1)}
        defaults.update(kwargs)
        return PipelineContext(**defaults)

    return _factory


# ── Concrete BaseAgent subclasses for testing ────────────────────────

# Imported lazily to allow test_base.py tests that check ABC behavior
# before the module fully loads.


@pytest.fixture
def DummyAgent():
    from src.agents.base import BaseAgent

    class _DummyAgent(BaseAgent):
        name = "dummy"

        async def execute(self, context):
            return {"result": "ok"}

    return _DummyAgent


@pytest.fixture
def FailingAgent():
    from src.agents.base import BaseAgent

    class _FailingAgent(BaseAgent):
        name = "failing"

        async def execute(self, context):
            raise RuntimeError("boom")

    return _FailingAgent


@pytest.fixture
def SlowAgent():
    from src.agents.base import BaseAgent

    class _SlowAgent(BaseAgent):
        name = "slow"

        def get_timeout_seconds(self) -> int:
            return 1

        async def execute(self, context):
            await asyncio.sleep(5)
            return {"result": "late"}

    return _SlowAgent


@pytest.fixture
def ValidationAgent():
    from src.agents.base import BaseAgent

    class _ValidationAgent(BaseAgent):
        name = "validator"

        def validate_context(self, context) -> str | None:
            return "Missing required slot: signals"

        async def execute(self, context):
            return {"result": "should not reach"}

    return _ValidationAgent


@pytest.fixture
def TrackingAgent():
    """Agent that makes two LLM tracking calls during execute."""

    from src.agents.base import BaseAgent

    class _TrackingAgent(BaseAgent):
        name = "tracker"

        async def execute(self, context):
            self.track_llm_usage("model-a", 100, 50, 0.01)
            self.track_llm_usage("model-b", 200, 80, 0.02)
            return {"tracked": True}

    return _TrackingAgent


@pytest.fixture
def PartialTrackingFailAgent():
    """Agent that tracks some usage then raises."""

    from src.agents.base import BaseAgent

    class _PartialTrackingFailAgent(BaseAgent):
        name = "partial_tracker"

        async def execute(self, context):
            self.track_llm_usage("model-a", 100, 50, 0.01)
            raise RuntimeError("mid-execution failure")

    return _PartialTrackingFailAgent


# ── Stub agent factory (for orchestrator tests) ─────────────────────


def make_stub_agent_class(agent_name: str, data: dict | None = None, succeed: bool = True):
    """Dynamically create a BaseAgent subclass with given name and behavior."""
    from src.agents.base import BaseAgent

    cls_data = data if data is not None else {}
    cls_succeed = succeed

    cls = type(
        f"Stub_{agent_name}",
        (BaseAgent,),
        {
            "name": agent_name,
            "execute": _make_execute(cls_data, cls_succeed),
        },
    )
    return cls


def _make_execute(data: dict, succeed: bool):
    async def execute(self, context):
        if not succeed:
            raise RuntimeError(f"Stub {self.name} configured to fail")
        return data

    return execute
