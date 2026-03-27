"""Агентная инфраструктура Delphi Press.

Спека: docs/02-agents-core.md.
"""

from src.agents.base import BaseAgent
from src.agents.orchestrator import Orchestrator, StageDefinition
from src.agents.registry import AgentRegistry, build_default_registry

__all__ = [
    "AgentRegistry",
    "BaseAgent",
    "Orchestrator",
    "StageDefinition",
    "build_default_registry",
]
