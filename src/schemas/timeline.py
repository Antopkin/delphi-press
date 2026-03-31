"""Промежуточные артефакты event-level timeline.

Стадия пайплайна: 6a (Judge aggregate_timeline).
Спека: docs/05-delphi-pipeline.md, docs/11-roadmap.md (E.1).
Контракт: PersonaAssessment[] → Judge._aggregate_timeline() → PredictedTimeline
          → Judge._select_headlines() → RankedPrediction[].
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_serializer

from src.schemas.headline import AgreementLevel, ConfidenceLabel, DissentingView


class HorizonBand(StrEnum):
    """Горизонтный band для horizon-aware промптов.

    Определяет аналитический режим персон (Tetlock/GJP, AIA Forecaster 2024).
    """

    IMMEDIATE = "immediate"  # 1-2 days: operational mode
    NEAR = "near"  # 3-4 days: mixed mode (max uncertainty)
    MEDIUM = "medium"  # 5-7 days: structural mode


def compute_horizon_band(horizon_days: int) -> HorizonBand:
    """Вычислить HorizonBand из количества дней до target_date."""
    if horizon_days <= 2:
        return HorizonBand.IMMEDIATE
    if horizon_days <= 4:
        return HorizonBand.NEAR
    return HorizonBand.MEDIUM


class TimelineEntry(BaseModel):
    """Одно событие в предсказанном timeline — промежуточный артефакт Judge.

    Содержит все поля, необходимые для последующего маппинга в RankedPrediction,
    плюс temporal fields (predicted_date, uncertainty_days, causal_dependencies).
    """

    event_thread_id: str = Field(description="ID EventThread")
    prediction: str = Field(description="Текст прогноза (best text, closest to median)")
    aggregated_probability: float = Field(
        ge=0.0, le=1.0, description="Калиброванная вероятность (Platt scaling)"
    )
    raw_probability: float = Field(ge=0.0, le=1.0, description="Исходная взвешенная медиана")
    predicted_date: date = Field(description="Прогнозируемая дата события")
    uncertainty_days: float = Field(ge=0.0, description="Неопределённость в днях (±)")
    newsworthiness: float = Field(ge=0.0, le=1.0, description="Средняя новостная ценность")
    agreement_level: AgreementLevel = Field(description="Уровень согласия между персонами")
    spread: float = Field(ge=0.0, le=1.0, description="Разброс вероятностей")
    confidence_label: ConfidenceLabel = Field(description="Метка уверенности")
    reasoning: str = Field(description="Объединённая цепочка рассуждений")
    evidence_chain: list[dict[str, str]] = Field(
        description="Цепочка доказательств [{source, summary}]"
    )
    dissenting_views: list[DissentingView] = Field(
        default_factory=list, description="Несогласные позиции"
    )
    causal_dependencies: list[str] = Field(
        default_factory=list,
        description="event_thread_id событий-предусловий",
    )
    temporal_order: int = Field(
        default=0, description="Порядковый номер во timeline (1-based, по predicted_date)"
    )
    scenario_types: list[str] = Field(
        default_factory=list,
        description="Типы сценариев, встреченные у персон (baseline, black_swan, ...)",
    )
    is_wild_card: bool = Field(default=False, description="Wild card от Адвоката дьявола")
    persona_count: int = Field(ge=1, description="Количество персон, предсказавших событие")

    @field_serializer("predicted_date")
    @classmethod
    def _serialize_date(cls, v: date) -> str:
        return v.isoformat()


class PredictedTimeline(BaseModel):
    """Полный предсказанный timeline — выход Judge step 6a.

    Промежуточный артефакт, сохраняемый в PipelineContext.predicted_timeline.
    Содержит все агрегированные события, упорядоченные по temporal_order.
    """

    entries: list[TimelineEntry] = Field(
        description="Агрегированные события, упорядоченные по temporal_order"
    )
    target_date: date = Field(description="Целевая дата прогноза")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp генерации",
    )
    horizon_band: HorizonBand = Field(description="Горизонтный band")
    horizon_days: int = Field(ge=1, le=30, description="Горизонт прогноза в днях")
    total_events: int = Field(
        default=0, ge=0, description="Общее количество обработанных event threads"
    )

    @field_serializer("target_date")
    @classmethod
    def _serialize_target_date(cls, v: date) -> str:
        return v.isoformat()

    @field_serializer("generated_at")
    @classmethod
    def _serialize_generated_at(cls, v: datetime) -> str:
        return v.isoformat()
