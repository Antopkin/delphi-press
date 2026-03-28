"""Агентная инфраструктура и Delphi-схемы.

Стадия пайплайна: все (AgentResult/StageResult), 4-5 (Delphi).
Спеки: docs/02-agents-core.md (§1-2), docs/05-delphi-pipeline.md (§2.6, §4.3).
Контракт: AgentResult ← BaseAgent.run(); PersonaAssessment ← ExpertPersona.assess();
           MediatorSynthesis ← Mediator.synthesize().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# =====================================================================
# AgentResult — иммутабельный результат выполнения агента
# =====================================================================


@dataclass(frozen=True)
class AgentResult:
    """Иммутабельный результат выполнения одного агента.

    Каждый вызов BaseAgent.run() возвращает ровно один AgentResult.
    При ошибке success=False, data=None, error содержит описание.
    """

    agent_name: str
    """Уникальное имя агента (совпадает с BaseAgent.name)."""

    success: bool
    """True если агент завершился без критических ошибок."""

    data: dict[str, Any] | None = None
    """Произвольный payload результата. Структура зависит от агента."""

    duration_ms: int = 0
    """Время выполнения агента в миллисекундах."""

    llm_model: str | None = None
    """Идентификатор использованной LLM-модели. Формат: 'provider/model'."""

    tokens_in: int = 0
    """Суммарное количество входных токенов за все LLM-вызовы агента."""

    tokens_out: int = 0
    """Суммарное количество выходных токенов за все LLM-вызовы агента."""

    cost_usd: float = 0.0
    """Суммарная стоимость LLM-вызовов в долларах (расчётная)."""

    error: str | None = None
    """Описание ошибки если success=False."""


# =====================================================================
# StageResult — результат целой стадии пайплайна
# =====================================================================


@dataclass(frozen=True)
class StageResult:
    """Результат целой стадии пайплайна (может включать несколько агентов).

    Стадия считается успешной, если хотя бы один агент внутри неё
    завершился успешно (для параллельных стадий), или единственный агент
    завершился успешно (для последовательных).
    """

    stage_name: str
    """Имя стадии: 'collection', 'event_identification', 'trajectory', etc."""

    success: bool
    """True если стадия завершилась и дала достаточно данных для продолжения."""

    agent_results: list[AgentResult] = field(default_factory=list)
    """Результаты всех агентов, запущенных в этой стадии."""

    duration_ms: int = 0
    """Суммарное время стадии (wall clock, не CPU)."""

    error: str | None = None
    """Описание ошибки стадии, если success=False."""

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.agent_results)

    @property
    def total_tokens_in(self) -> int:
        return sum(r.tokens_in for r in self.agent_results)

    @property
    def total_tokens_out(self) -> int:
        return sum(r.tokens_out for r in self.agent_results)


# =====================================================================
# Delphi: ScenarioType, PredictionItem, PersonaAssessment
# =====================================================================


class ScenarioType(StrEnum):
    """Тип сценария в рамках оценки персоны."""

    BASE = "base"
    UPSIDE = "upside"
    DOWNSIDE = "downside"
    BLACK_SWAN = "black_swan"
    WILDCARD = "wildcard"


class PredictionItem(BaseModel):
    """Единичный прогноз внутри оценки персоны."""

    event_thread_id: str = Field(description="ID EventThread, к которому относится прогноз")
    prediction: str = Field(
        description="Что именно произойдёт (конкретное утверждение, не общие слова)"
    )
    probability: float = Field(ge=0.0, le=1.0, description="Оценка вероятности (0.0-1.0)")
    newsworthiness: float = Field(
        ge=0.0, le=1.0, description="Насколько это станет новостью (0.0-1.0)"
    )
    scenario_type: ScenarioType = Field(description="Тип сценария")
    reasoning: str = Field(description="Цепочка рассуждений, приведшая к оценке (3-7 предложений)")
    key_assumptions: list[str] = Field(
        description="Ключевые предпосылки, на которых основан прогноз (2-4 штуки)"
    )
    evidence: list[str] = Field(description="Ссылки на конкретные факты из входных данных")
    conditional_on: list[str] = Field(
        default_factory=list,
        description="ID других PredictionItem, от которых зависит этот прогноз",
    )


class PersonaAssessment(BaseModel):
    """Полная оценка от одной экспертной персоны за один раунд Дельфи."""

    persona_id: str = Field(description="ID персоны (PersonaID)")
    round_number: int = Field(ge=1, le=2, description="Номер раунда Дельфи")
    predictions: list[PredictionItem] = Field(
        min_length=5, max_length=15, description="Список прогнозов (5-15 штук)"
    )
    cross_impacts_noted: list[str] = Field(
        default_factory=list,
        description="Замеченные перекрёстные влияния ('если A, то B вероятнее')",
    )
    blind_spots: list[str] = Field(
        default_factory=list,
        description="Что, по мнению персоны, группа может пропустить",
    )
    confidence_self_assessment: float = Field(
        ge=0.0, le=1.0, description="Самооценка общей уверенности в своём анализе"
    )
    revisions_made: list[str] = Field(
        default_factory=list,
        description="Что было пересмотрено после обратной связи медиатора",
    )
    revision_rationale: str = Field(
        default="",
        description="Почему эти ревизии были сделаны (или почему позиция не изменилась)",
    )


# =====================================================================
# Mediator schemas
# =====================================================================


class AnonymizedPosition(BaseModel):
    """Анонимизированная позиция одного эксперта по одному событию."""

    agent_label: str = Field(description="Анонимная метка: 'Эксперт A', 'Эксперт B'...")
    probability: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(description="Усечённое обоснование (до 200 символов)")
    key_assumptions: list[str] = Field(description="Ключевые предпосылки эксперта")


class ConsensusArea(BaseModel):
    """Область консенсуса: все эксперты примерно согласны."""

    event_thread_id: str
    median_probability: float = Field(ge=0.0, le=1.0)
    spread: float = Field(ge=0.0, lt=0.15, description="Разброс < 0.15")
    num_agents: int = Field(ge=3)


class DisputeArea(BaseModel):
    """Область расхождения: значительный разброс между экспертами."""

    event_thread_id: str
    median_probability: float = Field(ge=0.0, le=1.0)
    spread: float = Field(ge=0.0, le=1.0, description="Разброс между экспертами")
    positions: list[AnonymizedPosition] = Field(description="Анонимизированные позиции экспертов")
    key_question: str = Field(
        default="",
        description="Ключевой фактический вопрос для разрешения спора (LLM-generated)",
    )


class GapArea(BaseModel):
    """Пробел: событие упомянуто слишком малым числом экспертов."""

    event_thread_id: str
    mentioned_by: list[str] = Field(description="Анонимные метки экспертов, упомянувших событие")
    note: str


class CrossImpactFlag(BaseModel):
    """Флаг перекрёстного влияния: прогноз зависит от спорного события."""

    prediction_event_id: str
    depends_on_event_id: str
    note: str


class MediatorSynthesis(BaseModel):
    """Полный синтез медиатора между раундами Дельфи.

    Передаётся каждому агенту в раунде 2 (но без раскрытия persona_id).
    """

    consensus_areas: list[ConsensusArea] = Field(
        description="События с консенсусом (spread < 0.15)"
    )
    disputes: list[DisputeArea] = Field(description="События с расхождениями (spread >= 0.15)")
    gaps: list[GapArea] = Field(description="События, упомянутые < 3 экспертами")
    cross_impact_flags: list[CrossImpactFlag] = Field(
        description="Прогнозы, зависящие от спорных событий"
    )
    overall_summary: str = Field(description="Текстовое резюме для контекста раунда 2")
    supplementary_facts: list[str] = Field(
        default_factory=list,
        description="Дополнительные факты из supervisor search (заполняется позже)",
    )
