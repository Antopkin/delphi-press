"""API-схемы запроса и ответа прогнозирования.

Спека: docs/02-agents-core.md (§7).
Контракт: PredictionRequest → Orchestrator → PredictionResponse.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    """Входной запрос на прогнозирование."""

    outlet: str = Field(
        ...,
        description="Название СМИ. Примеры: 'ТАСС', 'BBC Russian', 'Незыгарь'.",
        min_length=1,
        max_length=200,
    )

    target_date: date = Field(
        ...,
        description="Дата, на которую делается прогноз (YYYY-MM-DD).",
    )

    preset: str = Field(
        default="full",
        description="Pipeline preset: light, standard, full.",
    )


class HeadlineOutput(BaseModel):
    """Один прогнозированный заголовок в финальном ответе."""

    rank: int = Field(..., ge=1, le=10)
    headline: str
    first_paragraph: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str
    category: str
    reasoning: str
    evidence_chain: list[dict[str, str]] = Field(default_factory=list)
    agent_agreement: str
    dissenting_views: list[dict[str, Any]] = Field(default_factory=list)


class PredictionResponse(BaseModel):
    """Финальный ответ пайплайна прогнозирования."""

    id: str
    outlet: str
    target_date: date
    status: str
    duration_ms: int = 0
    total_cost_usd: float = 0.0
    headlines: list[HeadlineOutput] = Field(default_factory=list)
    error: str | None = None
    failed_stage: str | None = None
    predicted_timeline: dict[str, Any] | None = None
    delphi_summary: dict[str, Any] | None = None
    stage_results: list[dict[str, Any]] = Field(default_factory=list)
