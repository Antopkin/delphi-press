"""Generators module — Delphi pipeline agents (Stages 7-9).

Спека: docs-site/docs/generation/stages-6-9.md
"""

from src.agents.generators.framing import FramingAnalyzer
from src.agents.generators.quality_gate import QualityGate
from src.agents.generators.style_replicator import StyleReplicator

__all__ = [
    "FramingAnalyzer",
    "QualityGate",
    "StyleReplicator",
]
