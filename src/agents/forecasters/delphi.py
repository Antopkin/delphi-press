"""Stage 4-6: DELPHI utilities — dataclasses and exceptions.

Спека: docs/05-delphi-pipeline.md (§3).

Контракт:
    DelphiRoundResult хранит результаты одного раунда Дельфи.
    DelphiQuorumError поднимается при недостаточном числе агентов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelphiRoundResult:
    """Результат одного раунда Дельфи."""

    round_number: int
    assessments: dict[str, Any]
    failed_agents: list[str] = field(default_factory=list)
    duration_ms: int = 0


class DelphiQuorumError(Exception):
    """Недостаточно агентов для валидной Дельфи-симуляции."""

    def __init__(self, required: int, actual: int) -> None:
        self.required = required
        self.actual = actual
        super().__init__(f"Delphi quorum not met: {actual}/{required} agents completed")
