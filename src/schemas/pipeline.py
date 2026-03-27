"""Контекст пайплайна — разделяемое мутабельное состояние.

Стадия пайплайна: все (передаётся через все 9 стадий).
Спека: docs/02-agents-core.md (§2).
Контракт: Orchestrator создаёт PipelineContext → агенты читают/пишут слоты →
          Orchestrator формирует PredictionResponse.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from src.schemas.agent import AgentResult, StageResult


class PipelineContext(BaseModel):
    """Разделяемое состояние мультиагентного пайплайна прогнозирования.

    Создаётся оркестратором в начале прогноза. Передаётся во все агенты
    по ссылке (Pydantic model — mutable по умолчанию). Каждая стадия
    заполняет свои слоты; последующие стадии читают предыдущие.

    Слоты заполняются последовательно по стадиям:
    1. Collection: signals, scheduled_events, outlet_profile
    2. Event Identification: event_threads
    3. Trajectory: trajectories, cross_impact_matrix
    4. Delphi R1: round1_assessments
    5. Delphi R2: mediator_synthesis, round2_assessments
    6. Consensus: ranked_predictions
    7. Framing: framing_briefs
    8. Generation: generated_headlines
    9. Quality Gate: final_predictions
    """

    model_config = {"arbitrary_types_allowed": True}

    # === Метаданные запроса ===

    prediction_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Уникальный идентификатор прогноза (UUIDv4).",
    )

    outlet: str = Field(
        ...,
        description="Название целевого СМИ. Например: 'ТАСС', 'BBC Russian'.",
    )

    target_date: date = Field(
        ...,
        description="Дата, на которую делается прогноз (YYYY-MM-DD).",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp создания контекста.",
    )

    # === Stage 1: Collection ===

    signals: list[Any] = Field(
        default_factory=list,
        description="List[SignalRecord]. Сырые сигналы из NewsScout.",
    )

    scheduled_events: list[Any] = Field(
        default_factory=list,
        description="List[ScheduledEvent]. Запланированные события на target_date.",
    )

    outlet_profile: Any | None = Field(
        default=None,
        description="OutletProfile. Стилевой и редакционный профиль издания.",
    )

    # === Stage 2: Event Identification ===

    event_threads: list[Any] = Field(
        default_factory=list,
        description="List[EventThread]. Top-20 кластеризованных событийных нитей.",
    )

    # === Stage 3: Trajectory Analysis ===

    trajectories: list[Any] = Field(
        default_factory=list,
        description="List[EventTrajectory]. Сценарные траектории для каждого EventThread.",
    )

    cross_impact_matrix: Any | None = Field(
        default=None,
        description="CrossImpactMatrix. Матрица перекрёстных влияний между событиями.",
    )

    # === Stage 4: Delphi Round 1 ===

    round1_assessments: list[Any] = Field(
        default_factory=list,
        description="List[PersonaAssessment]. Независимые оценки от 5 экспертных персон.",
    )

    # === Stage 5: Delphi Round 2 ===

    mediator_synthesis: Any | None = Field(
        default=None,
        description="MediatorSynthesis. Обобщение Раунда 1: консенсус, расхождения.",
    )

    round2_assessments: list[Any] = Field(
        default_factory=list,
        description="List[PersonaAssessment]. Пересмотренные оценки после медиации.",
    )

    # === Stage 6: Consensus & Selection ===

    ranked_predictions: list[Any] = Field(
        default_factory=list,
        description="List[RankedPrediction]. Top-7 прогнозов + wild cards.",
    )

    # === Stage 7: Framing ===

    framing_briefs: list[Any] = Field(
        default_factory=list,
        description="List[FramingBrief]. Анализ фрейминга для каждого RankedPrediction.",
    )

    # === Stage 8: Generation ===

    generated_headlines: list[Any] = Field(
        default_factory=list,
        description="List[GeneratedHeadline]. Заголовки (2-3 варианта на прогноз).",
    )

    # === Stage 9: Quality Gate ===

    final_predictions: list[Any] = Field(
        default_factory=list,
        description="List[FinalPrediction]. Финальные прогнозы, прошедшие все проверки.",
    )

    # === Трекинг ===

    stage_results: list[StageResult] = Field(
        default_factory=list,
        description="Результаты всех завершённых стадий.",
    )

    # === Progress callback (private, not serialized) ===

    _progress_callback: Callable[[str, str, float], Awaitable[None]] | None = PrivateAttr(
        default=None
    )

    # === Методы ===

    def set_progress_callback(
        self,
        callback: Callable[[str, str, float], Awaitable[None]],
    ) -> None:
        """Установить callback для SSE-эмиссии.

        Args:
            callback: Async функция (stage_name, message, progress_pct) -> None.
        """
        self._progress_callback = callback

    async def emit_progress(
        self,
        stage_name: str,
        message: str,
        progress_pct: float,
    ) -> None:
        """Отправить SSE-событие о прогрессе.

        Безопасно вызывать даже если callback не установлен (no-op).
        """
        if self._progress_callback is not None:
            await self._progress_callback(stage_name, message, progress_pct)

    def merge_agent_result(self, result: AgentResult) -> None:
        """Записать данные из AgentResult в соответствующий слот контекста.

        Маппинг agent_name -> slot:
          - 'news_scout'           -> signals
          - 'event_calendar'       -> scheduled_events
          - 'outlet_historian'     -> outlet_profile
          - 'event_trend_analyzer' -> event_threads
          - 'delphi_*'             -> round1_assessments / round2_assessments
          - 'mediator'             -> mediator_synthesis
          - 'judge'                -> ranked_predictions
          - 'framing'              -> framing_briefs
          - 'style_replicator'     -> generated_headlines
          - 'quality_gate'         -> final_predictions
          - analysts               -> enrich event_threads.assessments

        Args:
            result: AgentResult от конкретного агента.

        Raises:
            ValueError: Если agent_name не распознан.
        """
        if not result.success or result.data is None:
            return

        slot_mapping: dict[str, str] = {
            "news_scout": "signals",
            "event_calendar": "scheduled_events",
            "outlet_historian": "outlet_profile",
            "event_trend_analyzer": "event_threads",
            "judge": "ranked_predictions",
            "framing": "framing_briefs",
            "style_replicator": "generated_headlines",
            "quality_gate": "final_predictions",
        }

        # Прямой маппинг для агентов с единственным слотом
        if result.agent_name in slot_mapping:
            slot = slot_mapping[result.agent_name]
            value = result.data.get(slot) or result.data
            current = getattr(self, slot)
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            else:
                setattr(self, slot, value)
            return

        # Delphi-агенты (round1/round2 определяется по наличию ключа)
        if result.agent_name.startswith("delphi_"):
            if "revised_assessment" in result.data:
                self.round2_assessments.append(result.data["revised_assessment"])
            elif "assessment" in result.data:
                self.round1_assessments.append(result.data["assessment"])
            return

        if result.agent_name == "mediator":
            self.mediator_synthesis = result.data.get("synthesis")
            return

        # Аналитики добавляют свои оценки в event_threads
        analyst_names = {
            "geopolitical_analyst",
            "economic_analyst",
            "media_analyst",
        }
        if result.agent_name in analyst_names:
            if "assessments" in result.data:
                for assessment in result.data["assessments"]:
                    thread_id = assessment.get("thread_id")
                    for thread in self.event_threads:
                        if getattr(thread, "id", None) == thread_id:
                            if not hasattr(thread, "assessments"):
                                thread.assessments = {}
                            thread.assessments[result.agent_name] = assessment
            return

    def get_total_cost_usd(self) -> float:
        """Суммарная стоимость всех LLM-вызовов по всем стадиям."""
        return sum(sr.total_cost_usd for sr in self.stage_results)

    def get_total_duration_ms(self) -> int:
        """Суммарное wall-clock время всех стадий."""
        return sum(sr.duration_ms for sr in self.stage_results)
