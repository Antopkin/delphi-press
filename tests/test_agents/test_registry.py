"""Tests for src.agents.registry — AgentRegistry DI container."""

from __future__ import annotations

import pytest

from src.agents.registry import AgentRegistry, build_default_registry

# ── Instantiation ────────────────────────────────────────────────────


def test_registry_empty_on_creation(mock_router):
    registry = AgentRegistry(mock_router)
    assert len(registry) == 0


# ── register() ───────────────────────────────────────────────────────


def test_register_adds_agent(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    agent = DummyAgent(mock_router)
    registry.register(agent)
    assert "dummy" in registry


def test_register_increments_len(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    agent = DummyAgent(mock_router)
    registry.register(agent)
    assert len(registry) == 1


def test_register_duplicate_raises_value_error(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    agent1 = DummyAgent(mock_router)
    agent2 = DummyAgent(mock_router)
    registry.register(agent1)
    with pytest.raises(ValueError, match="dummy"):
        registry.register(agent2)


# ── register_class() ────────────────────────────────────────────────


def test_register_class_creates_instance(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    registry.register_class(DummyAgent)
    agent = registry.get("dummy")
    assert agent is not None
    assert agent.name == "dummy"


def test_register_class_injects_llm_client(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    registry.register_class(DummyAgent)
    agent = registry.get("dummy")
    assert agent.llm is mock_router


def test_register_class_non_subclass_raises_type_error(mock_router):
    registry = AgentRegistry(mock_router)

    class NotAnAgent:
        name = "fake"

    with pytest.raises(TypeError, match="BaseAgent"):
        registry.register_class(NotAnAgent)  # type: ignore[arg-type]


# ── get() ────────────────────────────────────────────────────────────


def test_get_returns_agent(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    agent = DummyAgent(mock_router)
    registry.register(agent)
    assert registry.get("dummy") is agent


def test_get_returns_none_for_unknown(mock_router):
    registry = AgentRegistry(mock_router)
    assert registry.get("nonexistent") is None


# ── get_required() ───────────────────────────────────────────────────


def test_get_required_returns_agent(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    agent = DummyAgent(mock_router)
    registry.register(agent)
    assert registry.get_required("dummy") is agent


def test_get_required_raises_key_error_for_unknown(mock_router):
    registry = AgentRegistry(mock_router)
    with pytest.raises(KeyError, match="nonexistent"):
        registry.get_required("nonexistent")


def test_get_required_error_lists_available(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    registry.register(DummyAgent(mock_router))
    with pytest.raises(KeyError, match="dummy"):
        registry.get_required("ghost")


# ── list_agents() ───────────────────────────────────────────────────


def test_list_agents_sorted(DummyAgent, FailingAgent, mock_router):
    registry = AgentRegistry(mock_router)
    registry.register(FailingAgent(mock_router))
    registry.register(DummyAgent(mock_router))
    assert registry.list_agents() == ["dummy", "failing"]


def test_list_agents_empty(mock_router):
    registry = AgentRegistry(mock_router)
    assert registry.list_agents() == []


# ── __contains__ ────────────────────────────────────────────────────


def test_contains_true_for_registered(DummyAgent, mock_router):
    registry = AgentRegistry(mock_router)
    registry.register(DummyAgent(mock_router))
    assert "dummy" in registry


def test_contains_false_for_unregistered(mock_router):
    registry = AgentRegistry(mock_router)
    assert "ghost" not in registry


# ── build_default_registry() ────────────────────────────────────────


def test_build_default_registry_returns_registry(mock_router):
    result = build_default_registry(mock_router)
    assert isinstance(result, AgentRegistry)


def test_build_default_registry_has_analysts(mock_router):
    """Without collector_deps, analysts + forecasters + generators are registered."""
    result = build_default_registry(mock_router)
    # 4 analysts + 5 persona agents + mediator + judge + 3 generators = 14
    assert len(result) == 14
    assert "event_trend_analyzer" in result
    assert "geopolitical_analyst" in result
    assert "economic_analyst" in result
    assert "media_analyst" in result


def test_build_default_registry_has_forecasters(mock_router):
    """Registry includes all 7 forecaster agents."""
    result = build_default_registry(mock_router)
    # 5 personas
    assert "delphi_realist" in result
    assert "delphi_geostrategist" in result
    assert "delphi_economist" in result
    assert "delphi_media_expert" in result
    assert "delphi_devils_advocate" in result
    # mediator + judge
    assert "mediator" in result
    assert "judge" in result


def test_build_default_registry_has_generators(mock_router):
    """Registry includes all 3 generator agents."""
    result = build_default_registry(mock_router)
    assert "framing" in result
    assert "style_replicator" in result
    assert "quality_gate" in result
