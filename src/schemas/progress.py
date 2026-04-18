"""SSE-события прогресса для мониторинга пайплайна.

Стадия пайплайна: все (прогресс-бар UI).
Спека: docs-site/docs/architecture/pipeline.md (§4).
Контракт: SSEProgressEvent → SSE endpoint → клиент (EventSource).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ProgressStage(StrEnum):
    """Стадии пайплайна для отображения прогресса."""

    QUEUED = "queued"
    COLLECTION = "collection"
    EVENT_IDENTIFICATION = "event_identification"
    TRAJECTORY = "trajectory"
    DELPHI_R1 = "delphi_r1"
    DELPHI_R2 = "delphi_r2"
    CONSENSUS = "consensus"
    FRAMING = "framing"
    GENERATION = "generation"
    QUALITY_GATE = "quality_gate"
    COMPLETED = "completed"
    FAILED = "failed"


STAGE_PROGRESS_MAP: dict[ProgressStage, float] = {
    ProgressStage.QUEUED: 0.0,
    ProgressStage.COLLECTION: 0.05,
    ProgressStage.EVENT_IDENTIFICATION: 0.20,
    ProgressStage.TRAJECTORY: 0.30,
    ProgressStage.DELPHI_R1: 0.40,
    ProgressStage.DELPHI_R2: 0.55,
    ProgressStage.CONSENSUS: 0.70,
    ProgressStage.FRAMING: 0.80,
    ProgressStage.GENERATION: 0.88,
    ProgressStage.QUALITY_GATE: 0.95,
    ProgressStage.COMPLETED: 1.0,
    ProgressStage.FAILED: -1.0,
}

STAGE_LABELS: dict[ProgressStage, str] = {
    ProgressStage.QUEUED: "В очереди",
    ProgressStage.COLLECTION: "Сбор данных",
    ProgressStage.EVENT_IDENTIFICATION: "Идентификация событий",
    ProgressStage.TRAJECTORY: "Анализ траекторий",
    ProgressStage.DELPHI_R1: "Экспертный анализ (раунд 1)",
    ProgressStage.DELPHI_R2: "Экспертный анализ (раунд 2)",
    ProgressStage.CONSENSUS: "Формирование консенсуса",
    ProgressStage.FRAMING: "Анализ фрейминга",
    ProgressStage.GENERATION: "Генерация заголовков",
    ProgressStage.QUALITY_GATE: "Контроль качества",
    ProgressStage.COMPLETED: "Готово",
    ProgressStage.FAILED: "Ошибка",
}


class SSEProgressEvent(BaseModel):
    """Событие прогресса для Server-Sent Events.

    Отправляется клиенту в формате:
    event: progress
    data: {"stage": "collection", "message": "...", "progress": 0.15, ...}
    """

    stage: ProgressStage
    """Текущая стадия пайплайна."""

    message: str
    """Человекочитаемое описание на русском."""

    progress: float = Field(ge=0.0, le=1.0)
    """Общий прогресс от 0.0 до 1.0."""

    detail: str | None = None
    """Детализация (опционально)."""

    elapsed_ms: int = 0
    """Миллисекунд с начала прогноза."""

    cost_usd: float = 0.0
    """Накопленная стоимость LLM-вызовов на данный момент."""
