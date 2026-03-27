"""Схемы заголовков: ранжирование, фрейминг, генерация, качество.

Стадии пайплайна: 6 (Judge → RankedPrediction), 7 (Framing → FramingBrief),
                  8 (Generation → GeneratedHeadline), 9 (QualityGate → FinalPrediction).
Спеки: docs/05-delphi-pipeline.md (§5.5), docs/06-generators.md (§1.4, §2.5, §3.5).
Контракт: RankedPrediction[] → FramingBrief[] → GeneratedHeadline[] → FinalPrediction[].
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field

# =====================================================================
# Enums
# =====================================================================


class ConfidenceLabel(StrEnum):
    """Пользовательские метки уверенности."""

    VERY_HIGH = "очень высокая"
    HIGH = "высокая"
    MODERATE = "умеренная"
    LOW = "низкая"
    SPECULATIVE = "спекулятивная"


class AgreementLevel(StrEnum):
    """Уровень согласия между агентами."""

    CONSENSUS = "consensus"
    MAJORITY_WITH_DISSENT = "majority_dissent"
    CONTESTED = "contested"


class FramingStrategy(StrEnum):
    """Стратегия фрейминга, выбранная редакцией."""

    THREAT = "threat"
    OPPORTUNITY = "opportunity"
    CRISIS = "crisis"
    ROUTINE = "routine"
    SENSATION = "sensation"
    ANALYTICAL = "analytical"
    HUMAN_INTEREST = "human_interest"
    NEUTRAL_REPORT = "neutral_report"
    CONFLICT = "conflict"


class GateDecision(StrEnum):
    """Решение QualityGate по заголовку."""

    PASS = "pass"
    REJECT = "reject"
    REVISE = "revise"
    DEPRIORITIZE = "deprioritize"
    MERGE = "merge"


# =====================================================================
# Stage 6: Judge output
# =====================================================================


class DissentingView(BaseModel):
    """Несогласная позиция одного агента."""

    agent_label: str = Field(description="Анонимная метка или роль агента")
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Краткое обоснование несогласия")


class RankedPrediction(BaseModel):
    """Единичный ранжированный прогноз — выход Judge, вход для генераторов."""

    event_thread_id: str
    prediction: str = Field(description="Текст прогноза (что произойдёт)")
    calibrated_probability: float = Field(
        ge=0.0, le=1.0, description="Калиброванная вероятность после Platt scaling"
    )
    raw_probability: float = Field(
        ge=0.0, le=1.0, description="Исходная взвешенная медиана до калибровки"
    )
    headline_score: float = Field(
        ge=0.0,
        description="Итоговый скоринг: prob * newsworthiness * (1-saturation) * relevance",
    )
    newsworthiness: float = Field(ge=0.0, le=1.0, description="Средняя оценка новостной ценности")
    confidence_label: ConfidenceLabel = Field(description="Пользовательская метка уверенности")
    agreement_level: AgreementLevel = Field(description="Уровень согласия между агентами")
    spread: float = Field(ge=0.0, le=1.0, description="Разброс вероятностей между агентами")
    reasoning: str = Field(description="Объединённая цепочка рассуждений")
    evidence_chain: list[dict[str, str]] = Field(
        description="Цепочка доказательств [{source, summary}]"
    )
    dissenting_views: list[DissentingView] = Field(
        default_factory=list, description="Несогласные позиции (пустой при консенсусе)"
    )
    is_wild_card: bool = Field(
        default=False,
        description="True если прогноз добавлен как wild card от Адвоката дьявола",
    )
    rank: int = Field(default=0, description="Позиция в итоговом ранжировании (1-based)")


# =====================================================================
# Stage 7: FramingAnalyzer output
# =====================================================================


class FramingBrief(BaseModel):
    """Редакционный бриф: как конкретное издание подаст событие.

    Генерируется FramingAnalyzer, используется StyleReplicator.
    """

    event_thread_id: str = Field(description="ID события из RankedPrediction")
    outlet_name: str = Field(description="Название издания")
    framing_strategy: FramingStrategy = Field(description="Основная стратегия фрейминга")
    angle: str = Field(
        description="Конкретный угол подачи: что в фокусе заголовка (1-2 предложения)"
    )
    emphasis_points: list[str] = Field(
        min_length=1, max_length=5, description="Что издание подчеркнёт (2-5 пунктов)"
    )
    omission_points: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Что издание приглушит или опустит (0-5 пунктов)",
    )
    headline_tone: str = Field(
        description="Тон заголовка: тревожный / нейтральный / оптимистичный / ироничный / ..."
    )
    likely_sources: list[str] = Field(
        min_length=1, max_length=5, description="На какие источники сошлётся издание"
    )
    section: str = Field(description="Раздел издания, в который попадёт публикация")
    news_cycle_hook: str = Field(
        default="", description="Привязка к текущему новостному циклу или серии"
    )
    editorial_alignment_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Насколько событие соответствует редакционной линии издания (0-1)",
    )


# =====================================================================
# Stage 8: StyleReplicator output
# =====================================================================


class GeneratedHeadline(BaseModel):
    """Один вариант заголовка + первый абзац.

    Генерируется StyleReplicator, проверяется QualityGate.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Уникальный ID варианта"
    )
    event_thread_id: str = Field(description="ID события из RankedPrediction")
    variant_number: int = Field(ge=1, le=4, description="Номер варианта (1-3)")
    headline: str = Field(description="Текст заголовка на языке издания")
    first_paragraph: str = Field(description="Первый абзац (лид) на языке издания")
    headline_language: str = Field(description="Язык заголовка (ru / en / ...)")
    length_deviation: float = Field(
        default=0.0,
        description="Отклонение длины от среднего издания (0=норма, >0=длиннее, <0=короче)",
    )
    is_revision: bool = Field(
        default=False, description="True если заголовок был исправлен после QualityGate"
    )
    revision_of_id: str | None = Field(
        default=None, description="ID исходного заголовка, если это ревизия"
    )


# =====================================================================
# Stage 9: QualityGate schemas
# =====================================================================


class CheckResult(BaseModel):
    """Результат одной проверки (factual или style)."""

    score: int = Field(ge=1, le=5, description="Оценка 1-5")
    feedback: str = Field(description="Текстовая обратная связь: что не так и как исправить")


class QualityScore(BaseModel):
    """Полная оценка качества одного заголовка."""

    headline_id: str = Field(description="ID GeneratedHeadline")
    factual_score: int = Field(ge=1, le=5, description="Оценка фактической правдоподобности (1-5)")
    factual_feedback: str = Field(description="Обратная связь от фактчекера")
    style_score: int = Field(ge=1, le=5, description="Оценка стилистической аутентичности (1-5)")
    style_feedback: str = Field(description="Обратная связь от стилистического ревьюера")
    is_internal_duplicate: bool = Field(
        default=False, description="Дубликат другого прогноза в этом же списке"
    )
    is_external_duplicate: bool = Field(
        default=False, description="Дубликат реального уже опубликованного заголовка"
    )
    duplicate_of_id: str | None = Field(
        default=None, description="ID заголовка-оригинала (при внутренней дедупликации)"
    )


# =====================================================================
# Stage 9: Final output
# =====================================================================


class FinalPrediction(BaseModel):
    """Финальный прогноз — то, что видит пользователь.

    Прошёл все проверки QualityGate. Содержит заголовок, абзац,
    уверенность, обоснование, несогласные мнения.
    """

    rank: int = Field(ge=1, description="Позиция в ранжировании")
    event_thread_id: str
    headline: str = Field(description="Основной заголовок на языке издания")
    first_paragraph: str = Field(description="Первый абзац (лид) на языке издания")
    alternative_headlines: list[str] = Field(
        default_factory=list, max_length=3, description="Альтернативные варианты заголовка (0-2)"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Калиброванная вероятность")
    confidence_label: ConfidenceLabel = Field(description="Пользовательская метка уверенности")
    category: str = Field(description="Раздел издания: 'Политика', 'Экономика', 'Общество'...")
    reasoning: str = Field(description="Цепочка рассуждений (для блока 'Почему мы так считаем')")
    evidence_chain: list[dict[str, str]] = Field(
        description="Цепочка доказательств [{source, summary}]"
    )
    agent_agreement: AgreementLevel = Field(description="Уровень согласия экспертов")
    dissenting_views: list[DissentingView] = Field(
        default_factory=list, description="Несогласные мнения"
    )
    is_wild_card: bool = Field(
        default=False, description="True = прогноз от Адвоката дьявола (wild card)"
    )
    framing_strategy: str = Field(description="Стратегия фрейминга, использованная при генерации")
    headline_language: str = Field(description="Язык заголовка")
