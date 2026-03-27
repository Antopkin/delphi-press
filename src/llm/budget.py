"""Трекер бюджета LLM-вызовов.

Спека: docs/07-llm-layer.md (§3.6).
Контракт: record(CostRecord) → накопление; check_budget(est) → raise если нет бюджета.
"""

from __future__ import annotations

import asyncio

from src.llm.exceptions import LLMBudgetExceededError
from src.schemas.llm import CostRecord


class BudgetTracker:
    """Трекер расходов на LLM-вызовы в рамках одного прогноза."""

    def __init__(self, budget_usd: float) -> None:
        self._budget = budget_usd
        self._records: list[CostRecord] = []
        self._lock = asyncio.Lock()

    @property
    def spent(self) -> float:
        """Потрачено USD."""
        return sum(r.cost_usd for r in self._records)

    @property
    def remaining(self) -> float:
        """Осталось USD."""
        return max(0.0, self._budget - self.spent)

    async def record(self, cost_record: CostRecord) -> None:
        """Записать расход. Thread-safe через asyncio.Lock."""
        async with self._lock:
            self._records.append(cost_record)

    async def check_budget(self, estimated_cost: float) -> None:
        """Проверить бюджет. Raises LLMBudgetExceededError если не хватает."""
        if estimated_cost > self.remaining:
            raise LLMBudgetExceededError(self._budget, self.spent)

    def summary_by_stage(self) -> dict[str, float]:
        """Группировка расходов по стадиям."""
        result: dict[str, float] = {}
        for r in self._records:
            result[r.stage] = result.get(r.stage, 0.0) + r.cost_usd
        return result

    def summary_by_model(self) -> dict[str, float]:
        """Группировка расходов по моделям."""
        result: dict[str, float] = {}
        for r in self._records:
            result[r.model] = result.get(r.model, 0.0) + r.cost_usd
        return result

    def to_records(self) -> list[CostRecord]:
        """Все записи расходов."""
        return list(self._records)

    def reset(self) -> None:
        """Сбросить для нового прогноза."""
        self._records.clear()
