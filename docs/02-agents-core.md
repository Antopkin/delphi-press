# 02 — Агентная инфраструктура

> Реализуемые файлы: `src/agents/base.py`, `src/agents/orchestrator.py`, `src/agents/registry.py`, `src/schemas/agent.py`, `src/schemas/pipeline.py`, `src/schemas/progress.py`

---

## Обзор

Этот модуль определяет фундамент мультиагентного пайплайна: абстрактный базовый агент, контейнер результата, разделяемый контекст пайплайна, оркестратор стадий и реестр агентов (DI-контейнер). Все остальные агенты (коллекторы, аналитики, прогнозисты, генераторы) наследуют от `BaseAgent` и работают внутри `PipelineContext`, управляемого `Orchestrator`.

Ключевые принципы:
- **Async-first**: все агенты -- корутины, оркестратор использует `asyncio.gather` для параллельных стадий
- **Инъекция LLM-клиента**: агенты не создают LLM-клиенты сами, получают их через конструктор
- **Иммутабельные результаты**: `AgentResult` -- frozen dataclass, агенты пишут результаты в слоты `PipelineContext`
- **Fail-soft**: сбой одного агента не останавливает пайплайн (кроме критических стадий)
- **Observability**: каждый агент автоматически замеряет время, логирует вход/выход, трекает токены

---

## 1. AgentResult (`src/schemas/agent.py`)

Иммутабельный контейнер результата выполнения агента. Возвращается из `BaseAgent.run()`.

```python
"""src/schemas/agent.py"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentResult:
    """Иммутабельный результат выполнения одного агента.

    Каждый вызов BaseAgent.run() возвращает ровно один AgentResult.
    При ошибке success=False, data=None, error содержит описание.
    """

    # --- Идентификация ---
    agent_name: str
    """Уникальное имя агента (совпадает с BaseAgent.name)."""

    # --- Статус ---
    success: bool
    """True если агент завершился без критических ошибок."""

    # --- Данные ---
    data: dict[str, Any] | None = None
    """Произвольный payload результата. Структура зависит от агента.
    Каждый конкретный агент документирует свой формат data.
    Примеры:
      - NewsScout:     {"signals": List[SignalRecord]}
      - EventCalendar: {"events": List[ScheduledEvent]}
      - EventTrendAnalyzer: {"threads": List[EventThread]}
    """

    # --- Метрики ---
    duration_ms: int = 0
    """Время выполнения агента в миллисекундах."""

    llm_model: str | None = None
    """Идентификатор использованной LLM-модели (может быть несколько --
    записывается основная). Формат: 'provider/model', например
    'anthropic/claude-sonnet-4'."""

    tokens_in: int = 0
    """Суммарное количество входных токенов за все LLM-вызовы агента."""

    tokens_out: int = 0
    """Суммарное количество выходных токенов за все LLM-вызовы агента."""

    cost_usd: float = 0.0
    """Суммарная стоимость LLM-вызовов в долларах (расчётная)."""

    # --- Ошибка ---
    error: str | None = None
    """Описание ошибки если success=False. Для логирования и UI.
    Не содержит stack trace (он в логах)."""


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
```

### Примечания по реализации

- `data` -- словарь, а не типизированная модель, чтобы `AgentResult` оставался универсальным. Каждый агент документирует структуру своего `data` в собственной спеке.
- `frozen=True` гарантирует, что результат не мутируется после создания. Данные агрегируются в `PipelineContext`.
- `cost_usd` рассчитывается в LLM-клиенте на основе модели и количества токенов. Формула: `(tokens_in * price_per_input_token) + (tokens_out * price_per_output_token)`. Таблица цен -- в `src/llm/pricing.py`.

---

## 2. PipelineContext (`src/schemas/pipeline.py`)

Разделяемое мутабельное состояние, которое передаётся через все стадии пайплайна. Каждый агент читает нужные ему слоты и пишет свои результаты. Оркестратор контролирует порядок заполнения.

```python
"""src/schemas/pipeline.py"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field

from src.schemas.agent import AgentResult, StageResult


# === Типы данных слотов ===
# Импорты ниже -- из соответствующих модулей schemas.
# Здесь для наглядности показаны inline-определения.
# Реальные классы определены в src/schemas/events.py, src/schemas/headline.py, etc.

# Forward references (разрешаются через TYPE_CHECKING):
# SignalRecord, ScheduledEvent, OutletProfile, EventThread,
# EventTrajectory, CrossImpactMatrix, PersonaAssessment,
# MediatorSynthesis, RevisedAssessment, RankedPrediction,
# FramingBrief, GeneratedHeadline, FinalPrediction,
# GeopoliticalAssessment, EconomicAssessment, MediaAssessment


class PipelineContext(BaseModel):
    """Разделяемое состояние мультиагентного пайплайна прогнозирования.

    Создаётся оркестратором в начале прогноза. Передаётся во все агенты
    по ссылке (Pydantic model -- mutable по умолчанию). Каждая стадия
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
        default_factory=datetime.utcnow,
        description="Timestamp создания контекста.",
    )

    # === Stage 1: Collection ===

    signals: list[Any] = Field(
        default_factory=list,
        description="List[SignalRecord]. Сырые сигналы из NewsScout: "
        "новости, посты, RSS-элементы. 100-200 штук.",
    )

    scheduled_events: list[Any] = Field(
        default_factory=list,
        description="List[ScheduledEvent]. Запланированные события на target_date "
        "из EventCalendar.",
    )

    outlet_profile: Any | None = Field(
        default=None,
        description="OutletProfile. Стилевой и редакционный профиль издания "
        "от OutletHistorian.",
    )

    # === Stage 2: Event Identification ===

    event_threads: list[Any] = Field(
        default_factory=list,
        description="List[EventThread]. Top-20 кластеризованных событийных нитей "
        "от EventTrendAnalyzer.",
    )

    # === Stage 3: Trajectory Analysis ===

    trajectories: list[Any] = Field(
        default_factory=list,
        description="List[EventTrajectory]. Сценарные траектории для каждого "
        "EventThread.",
    )

    cross_impact_matrix: Any | None = Field(
        default=None,
        description="CrossImpactMatrix. Матрица перекрёстных влияний "
        "между событиями.",
    )

    # === Stage 4: Delphi Round 1 ===

    round1_assessments: list[Any] = Field(
        default_factory=list,
        description="List[PersonaAssessment]. Независимые оценки от 5 экспертных "
        "персон (Реалист, Геостратег, Экономист, Медиа-эксперт, "
        "Адвокат дьявола).",
    )

    # === Stage 5: Delphi Round 2 ===

    mediator_synthesis: Any | None = Field(
        default=None,
        description="MediatorSynthesis. Обобщение Раунда 1: консенсус, "
        "расхождения, ключевые вопросы.",
    )

    round2_assessments: list[Any] = Field(
        default_factory=list,
        description="List[RevisedAssessment]. Пересмотренные оценки "
        "после медиации.",
    )

    # === Stage 6: Consensus & Selection ===

    ranked_predictions: list[Any] = Field(
        default_factory=list,
        description="List[RankedPrediction]. Top-7 прогнозов + wild cards, "
        "отсортированных по headline_score.",
    )

    # === Stage 7: Framing ===

    framing_briefs: list[Any] = Field(
        default_factory=list,
        description="List[FramingBrief]. Анализ фрейминга для каждого "
        "RankedPrediction: угол подачи, тон, источники.",
    )

    # === Stage 8: Generation ===

    generated_headlines: list[Any] = Field(
        default_factory=list,
        description="List[GeneratedHeadline]. Сгенерированные заголовки и "
        "первые абзацы (2-3 варианта на прогноз).",
    )

    # === Stage 9: Quality Gate ===

    final_predictions: list[Any] = Field(
        default_factory=list,
        description="List[FinalPrediction]. Финальные прогнозы, прошедшие "
        "фактчек, стилистику и дедупликацию.",
    )

    # === Трекинг ===

    stage_results: list[StageResult] = Field(
        default_factory=list,
        description="Результаты всех завершённых стадий -- для логирования, "
        "метрик и UI.",
    )

    # === Progress callback ===

    _progress_callback: Callable[[str, str, float], Awaitable[None]] | None = None
    """Async callback для SSE-эмиссии прогресса.
    Сигнатура: (stage_name: str, message: str, progress_pct: float) -> None.
    Устанавливается оркестратором, вызывается при переходах между стадиями.
    """

    # === Методы ===

    def set_progress_callback(
        self,
        callback: Callable[[str, str, float], Awaitable[None]],
    ) -> None:
        """Установить callback для SSE-эмиссии.

        Args:
            callback: Async функция (stage_name, message, progress_pct) -> None.
                progress_pct -- float от 0.0 до 1.0.
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

        Args:
            stage_name: Имя текущей стадии ('collection', 'delphi_r1', etc.).
            message: Человекочитаемое сообщение на русском.
            progress_pct: Прогресс от 0.0 до 1.0.
        """
        if self._progress_callback is not None:
            await self._progress_callback(stage_name, message, progress_pct)

    def merge_agent_result(self, result: AgentResult) -> None:
        """Записать данные из AgentResult в соответствующий слот контекста.

        Маппинг agent_name -> slot:
          - 'news_scout'          -> signals
          - 'event_calendar'      -> scheduled_events
          - 'outlet_historian'    -> outlet_profile
          - 'event_trend_analyzer'-> event_threads
          - 'geopolitical_analyst', 'economic_analyst', 'media_analyst'
                                  -> (аналитики пишут в trajectories)
          - 'delphi_*'            -> round1_assessments / round2_assessments
          - 'mediator'            -> mediator_synthesis
          - 'judge'               -> ranked_predictions
          - 'framing'             -> framing_briefs
          - 'style_replicator'    -> generated_headlines
          - 'quality_gate'        -> final_predictions

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

        # Аналитики добавляют свои оценки в trajectories / event_threads
        analyst_names = {
            "geopolitical_analyst",
            "economic_analyst",
            "media_analyst",
        }
        if result.agent_name in analyst_names:
            # Аналитики обогащают event_threads assessment-ами
            if "assessments" in result.data:
                # Сохраняем в data каждого thread
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
```

### Примечания по реализации

1. **Type hints `Any`**: Слоты типизированы как `Any` чтобы избежать циклических импортов. В рантайме они содержат конкретные Pydantic-модели (`SignalRecord`, `EventThread`, etc.), определённые в `src/schemas/events.py` и `src/schemas/headline.py`. При реализации использовать `TYPE_CHECKING` для аннотаций.

2. **Потокобезопасность**: `PipelineContext` -- НЕ потокобезопасный. Все параллельные агенты в пределах одной стадии работают в одном event loop. Запись в разные слоты из разных корутин безопасна (GIL + разные атрибуты). Запись в один list из параллельных корутин НЕ безопасна -- `merge_agent_result` должен вызываться из оркестратора последовательно после `gather`.

3. **Progress callback**: Не сериализуется (private field). При сохранении контекста в БД -- игнорируется.

---

## 3. BaseAgent (`src/agents/base.py`)

Абстрактный базовый класс для всех агентов системы. Обеспечивает единообразный интерфейс, автоматический замер времени, обработку ошибок и логирование.

```python
"""src/agents/base.py"""

from __future__ import annotations

import abc
import logging
import time
from typing import TYPE_CHECKING

from src.schemas.agent import AgentResult

if TYPE_CHECKING:
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class BaseAgent(abc.ABC):
    """Абстрактный базовый класс для всех агентов пайплайна.

    Каждый агент:
    - Имеет уникальное имя (name), по которому регистрируется в реестре
    - Получает LLM-клиент через конструктор (dependency injection)
    - Реализует execute() -- основную логику
    - Вызывается через run(), который добавляет timing, error handling, logging
    - Возвращает AgentResult

    Наследники ОБЯЗАНЫ реализовать:
    - name (class attribute или property)
    - execute() -- async метод с основной логикой

    Наследники МОГУТ переопределить:
    - validate_context() -- проверка наличия необходимых данных в контексте
    - get_timeout_seconds() -- таймаут выполнения (default: 300)

    Пример использования:
        class NewsScout(BaseAgent):
            name = "news_scout"

            async def execute(self, context: PipelineContext) -> dict:
                signals = await self._fetch_rss(context)
                return {"signals": signals}
    """

    name: str = ""
    """Уникальный идентификатор агента. Должен совпадать с ключом в реестре."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Инициализация агента.

        Args:
            llm_client: LLM-клиент для вызовов моделей. Предоставляет
                методы chat(), embed(), structured_output(). Агент
                использует клиент для всех LLM-взаимодействий.
        """
        self.llm = llm_client
        self.logger = logging.getLogger(f"agents.{self.name}")

        # Аккумуляторы метрик за один вызов run()
        self._tokens_in: int = 0
        self._tokens_out: int = 0
        self._cost_usd: float = 0.0
        self._llm_model: str | None = None

    @abc.abstractmethod
    async def execute(self, context: PipelineContext) -> dict:
        """Основная логика агента. Реализуется в наследниках.

        Args:
            context: Разделяемый контекст пайплайна. Агент читает нужные
                слоты и возвращает словарь данных для записи в контекст.

        Returns:
            dict с данными результата. Ключи зависят от конкретного агента.
            Этот словарь станет полем AgentResult.data.

        Raises:
            Любое исключение -- будет перехвачено в run() и преобразовано
            в AgentResult(success=False).
        """
        ...

    def validate_context(self, context: PipelineContext) -> str | None:
        """Проверка контекста перед выполнением.

        Наследники могут переопределить для проверки наличия необходимых
        данных. Вызывается в run() до execute().

        Args:
            context: Контекст пайплайна.

        Returns:
            None если контекст валиден, строка с описанием ошибки если нет.
        """
        return None

    def get_timeout_seconds(self) -> int:
        """Таймаут выполнения агента в секундах.

        Переопределить для агентов с длительными операциями.
        Default: 300 секунд (5 минут).
        """
        return 300

    async def run(self, context: PipelineContext) -> AgentResult:
        """Запуск агента с обёрткой timing/error handling/logging.

        НЕ переопределять в наследниках. Вся кастомная логика -- в execute().

        Порядок:
        1. Валидация контекста (validate_context)
        2. Запуск execute() с asyncio.timeout
        3. Сбор метрик (duration, tokens, cost)
        4. Формирование AgentResult

        Args:
            context: Разделяемый контекст пайплайна.

        Returns:
            AgentResult -- всегда, даже при ошибке.
        """
        import asyncio

        self.logger.info("Starting agent '%s' for prediction %s",
                         self.name, context.prediction_id)

        # Сброс аккумуляторов
        self._tokens_in = 0
        self._tokens_out = 0
        self._cost_usd = 0.0
        self._llm_model = None

        # Валидация
        validation_error = self.validate_context(context)
        if validation_error is not None:
            self.logger.warning("Context validation failed for '%s': %s",
                                self.name, validation_error)
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"Context validation failed: {validation_error}",
            )

        start_ms = time.monotonic_ns() // 1_000_000

        try:
            timeout = self.get_timeout_seconds()
            async with asyncio.timeout(timeout):
                data = await self.execute(context)

            duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

            self.logger.info(
                "Agent '%s' completed in %d ms (tokens: %d in, %d out, $%.4f)",
                self.name, duration_ms,
                self._tokens_in, self._tokens_out, self._cost_usd,
            )

            return AgentResult(
                agent_name=self.name,
                success=True,
                data=data,
                duration_ms=duration_ms,
                llm_model=self._llm_model,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
            error_msg = (
                f"Agent '{self.name}' timed out after {self.get_timeout_seconds()}s"
            )
            self.logger.error(error_msg)
            return AgentResult(
                agent_name=self.name,
                success=False,
                duration_ms=duration_ms,
                error=error_msg,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
            )

        except Exception as exc:
            duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
            error_msg = f"Agent '{self.name}' failed: {type(exc).__name__}: {exc}"
            self.logger.exception(error_msg)
            return AgentResult(
                agent_name=self.name,
                success=False,
                duration_ms=duration_ms,
                error=error_msg,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
            )

    def track_llm_usage(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Учёт использования LLM. Вызывается из execute() после каждого
        LLM-вызова.

        Args:
            model: Идентификатор модели ('anthropic/claude-sonnet-4').
            tokens_in: Входные токены этого вызова.
            tokens_out: Выходные токены этого вызова.
            cost_usd: Стоимость этого вызова.
        """
        self._llm_model = model  # Последняя используемая модель
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self._cost_usd += cost_usd
```

### Примечания по реализации

1. **`run()` -- финальный**: Наследники НЕ переопределяют `run()`. Если нужна кастомная обработка ошибок -- делать внутри `execute()`.

2. **Учёт LLM-метрик**: LLM-клиент (`src/llm/providers.py`) после каждого вызова возвращает `LLMResponse` с полями `tokens_in`, `tokens_out`, `cost_usd`, `model`. Агент обязан вызывать `self.track_llm_usage()` после каждого LLM-вызова. Рекомендуется обернуть это в хелпер:

    ```python
    async def _llm_chat(self, messages, **kwargs):
        response = await self.llm.chat(messages, **kwargs)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )
        return response
    ```

3. **Логирование**: Используется стандартный `logging` с иерархическим именем `agents.<agent_name>`. Конфигурация уровней -- в `src/config.py`.

4. **Таймаут**: `asyncio.timeout` (Python 3.11+) -- context manager, отменяет корутину по таймауту. Для агентов-коллекторов (сеть) рекомендуется увеличить до 600 секунд.

---

## 4. SSE Progress Events (`src/schemas/progress.py`)

Схемы событий, отправляемых клиенту через Server-Sent Events во время выполнения пайплайна.

```python
"""src/schemas/progress.py"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ProgressStage(str, Enum):
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


# Маппинг стадий на проценты для прогресс-бара
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

# Человекочитаемые названия стадий (для UI)
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
    """Человекочитаемое описание на русском. Например:
    'Сбор новостей: загружено 150 из 200 сигналов'."""

    progress: float = Field(ge=0.0, le=1.0)
    """Общий прогресс от 0.0 до 1.0."""

    detail: str | None = None
    """Детализация (опционально). Например: 'NewsScout: RSS done, Web Search running'."""

    elapsed_ms: int = 0
    """Миллисекунд с начала прогноза."""

    cost_usd: float = 0.0
    """Накопленная стоимость LLM-вызовов на данный момент."""
```

---

## 5. Orchestrator (`src/agents/orchestrator.py`)

Главный координатор пайплайна. Запускает стадии последовательно, внутри каждой стадии -- агентов параллельно (где возможно). Управляет PipelineContext, эмиттит SSE-прогресс, обрабатывает ошибки.

```python
"""src/agents/orchestrator.py"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from src.schemas.agent import AgentResult, StageResult
from src.schemas.pipeline import PipelineContext
from src.schemas.progress import (
    ProgressStage,
    SSEProgressEvent,
    STAGE_PROGRESS_MAP,
    STAGE_LABELS,
)

if TYPE_CHECKING:
    from src.agents.base import BaseAgent
    from src.agents.registry import AgentRegistry
    from src.schemas.prediction import PredictionRequest, PredictionResponse


logger = logging.getLogger("orchestrator")


class StageDefinition:
    """Описание одной стадии пайплайна.

    Attributes:
        name: Имя стадии (ProgressStage enum value).
        agent_names: Имена агентов для запуска на этой стадии.
        parallel: True если агенты запускаются параллельно.
        required: True если стадия критична (провал -> остановка пайплайна).
        timeout_seconds: Таймаут всей стадии (не отдельного агента).
        min_successful: Минимальное число успешных агентов для продолжения
            (актуально для параллельных стадий). None = все обязательны.
    """

    def __init__(
        self,
        name: ProgressStage,
        agent_names: list[str],
        parallel: bool = False,
        required: bool = True,
        timeout_seconds: int = 600,
        min_successful: int | None = None,
    ) -> None:
        self.name = name
        self.agent_names = agent_names
        self.parallel = parallel
        self.required = required
        self.timeout_seconds = timeout_seconds
        self.min_successful = min_successful


class Orchestrator:
    """Координатор мультиагентного пайплайна прогнозирования.

    Ответственности:
    - Создание PipelineContext из PredictionRequest
    - Последовательный запуск 9 стадий
    - Параллельный запуск агентов внутри стадии (где безопасно)
    - SSE-эмиссия прогресса при каждом переходе между стадиями
    - Error handling: fail-soft для коллекторов, fail-fast для критических
    - Аккумуляция метрик (время, стоимость, токены)
    - Формирование PredictionResponse из финального контекста
    """

    # === Определение стадий пайплайна ===

    STAGES: list[StageDefinition] = [
        # Stage 1: Data Collection -- 3 коллектора параллельно
        # Допускается провал 1 из 3 (min_successful=2)
        StageDefinition(
            name=ProgressStage.COLLECTION,
            agent_names=["news_scout", "event_calendar", "outlet_historian"],
            parallel=True,
            required=True,
            timeout_seconds=600,
            min_successful=2,
        ),
        # Stage 2: Event Identification -- 1 агент
        StageDefinition(
            name=ProgressStage.EVENT_IDENTIFICATION,
            agent_names=["event_trend_analyzer"],
            parallel=False,
            required=True,
            timeout_seconds=300,
        ),
        # Stage 3: Trajectory Analysis -- 3 аналитика параллельно
        # Все три нужны для полноты картины, но допускается 2 из 3
        StageDefinition(
            name=ProgressStage.TRAJECTORY,
            agent_names=[
                "geopolitical_analyst",
                "economic_analyst",
                "media_analyst",
            ],
            parallel=True,
            required=True,
            timeout_seconds=600,
            min_successful=2,
        ),
        # Stage 4: Delphi Round 1 -- 5 персон параллельно
        # Допускается провал 1 персоны (min_successful=4)
        StageDefinition(
            name=ProgressStage.DELPHI_R1,
            agent_names=[
                "delphi_realist",
                "delphi_geostrategist",
                "delphi_economist",
                "delphi_media_expert",
                "delphi_devils_advocate",
            ],
            parallel=True,
            required=True,
            timeout_seconds=600,
            min_successful=4,
        ),
        # Stage 5a: Mediator -- 1 агент, последовательно
        # Stage 5b: Delphi Round 2 -- 5 персон параллельно
        # Реализовано как 2 подстадии в одной стадии (см. _run_delphi_r2)
        StageDefinition(
            name=ProgressStage.DELPHI_R2,
            agent_names=["mediator"],  # + delphi_* (динамически)
            parallel=False,  # Внутренняя логика управляет параллельностью
            required=True,
            timeout_seconds=900,
        ),
        # Stage 6: Consensus & Selection
        StageDefinition(
            name=ProgressStage.CONSENSUS,
            agent_names=["judge"],
            parallel=False,
            required=True,
            timeout_seconds=300,
        ),
        # Stage 7: Framing Analysis
        StageDefinition(
            name=ProgressStage.FRAMING,
            agent_names=["framing"],
            parallel=False,
            required=True,
            timeout_seconds=300,
        ),
        # Stage 8: Style-Conditioned Generation
        StageDefinition(
            name=ProgressStage.GENERATION,
            agent_names=["style_replicator"],
            parallel=False,
            required=True,
            timeout_seconds=300,
        ),
        # Stage 9: Quality Gate
        StageDefinition(
            name=ProgressStage.QUALITY_GATE,
            agent_names=["quality_gate"],
            parallel=False,
            required=True,
            timeout_seconds=300,
        ),
    ]

    def __init__(self, registry: AgentRegistry) -> None:
        """Инициализация оркестратора.

        Args:
            registry: Реестр агентов с уже зарегистрированными и
                сконфигурированными экземплярами.
        """
        self.registry = registry

    async def run_prediction(
        self,
        request: PredictionRequest,
        progress_callback: (
            asyncio.Future
            | None
        ) = None,
    ) -> PredictionResponse:
        """Главная точка входа: запуск полного пайплайна прогнозирования.

        Создаёт PipelineContext, последовательно проходит все 9 стадий,
        формирует PredictionResponse.

        Args:
            request: Входной запрос (outlet + target_date).
            progress_callback: Опциональный async callback для SSE.

        Returns:
            PredictionResponse с заголовками, уверенностями и обоснованиями.

        Raises:
            PipelineError: Если критическая стадия провалилась.
        """
        from src.schemas.prediction import PredictionResponse

        # --- 1. Создание контекста ---
        context = PipelineContext(
            outlet=request.outlet,
            target_date=request.target_date,
        )

        if progress_callback is not None:
            context.set_progress_callback(progress_callback)

        pipeline_start_ms = time.monotonic_ns() // 1_000_000

        logger.info(
            "Starting prediction pipeline: outlet='%s', date=%s, id=%s",
            request.outlet, request.target_date, context.prediction_id,
        )

        await context.emit_progress(
            ProgressStage.QUEUED.value,
            "Пайплайн запущен",
            0.0,
        )

        # --- 2. Последовательный проход по стадиям ---
        for stage_def in self.STAGES:
            stage_result = await self._run_stage(stage_def, context)
            context.stage_results.append(stage_result)

            if not stage_result.success and stage_def.required:
                logger.error(
                    "Critical stage '%s' failed: %s",
                    stage_def.name.value, stage_result.error,
                )
                await context.emit_progress(
                    ProgressStage.FAILED.value,
                    f"Ошибка на стадии: {STAGE_LABELS[stage_def.name]}",
                    STAGE_PROGRESS_MAP[stage_def.name],
                )
                return self._build_error_response(context, stage_result)

        # --- 3. Формирование ответа ---
        pipeline_duration_ms = (
            (time.monotonic_ns() // 1_000_000) - pipeline_start_ms
        )

        await context.emit_progress(
            ProgressStage.COMPLETED.value,
            "Прогноз завершён",
            1.0,
        )

        logger.info(
            "Pipeline completed: id=%s, duration=%d ms, cost=$%.2f",
            context.prediction_id, pipeline_duration_ms,
            context.get_total_cost_usd(),
        )

        return self._build_response(context, pipeline_duration_ms)

    async def _run_stage(
        self,
        stage_def: StageDefinition,
        context: PipelineContext,
    ) -> StageResult:
        """Запуск одной стадии пайплайна.

        Для параллельных стадий запускает агентов через asyncio.gather.
        Для последовательных -- один за другим.

        Специальная обработка для DELPHI_R2 (двухфазная стадия).

        Args:
            stage_def: Определение стадии.
            context: Контекст пайплайна.

        Returns:
            StageResult с агрегированными результатами агентов.
        """
        stage_name = stage_def.name.value
        logger.info("Starting stage: %s", stage_name)

        await context.emit_progress(
            stage_name,
            STAGE_LABELS[stage_def.name],
            STAGE_PROGRESS_MAP[stage_def.name],
        )

        start_ms = time.monotonic_ns() // 1_000_000

        # Специальная логика для Delphi R2 (mediator -> параллельные R2)
        if stage_def.name == ProgressStage.DELPHI_R2:
            return await self._run_delphi_r2(stage_def, context, start_ms)

        # Получение агентов из реестра
        agents: list[BaseAgent] = []
        for agent_name in stage_def.agent_names:
            agent = self.registry.get(agent_name)
            if agent is None:
                logger.warning("Agent '%s' not found in registry", agent_name)
                continue
            agents.append(agent)

        if not agents:
            return StageResult(
                stage_name=stage_name,
                success=False,
                error=f"No agents available for stage '{stage_name}'",
                duration_ms=0,
            )

        # Запуск агентов
        if stage_def.parallel:
            results = await self._run_parallel(
                agents, context, stage_def.timeout_seconds,
            )
        else:
            results = await self._run_sequential(agents, context)

        # Мерж результатов в контекст
        for result in results:
            context.merge_agent_result(result)

        # Проверка минимального числа успешных
        successful_count = sum(1 for r in results if r.success)
        min_required = stage_def.min_successful or len(agents)

        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        if successful_count < min_required:
            failed_names = [r.agent_name for r in results if not r.success]
            return StageResult(
                stage_name=stage_name,
                success=False,
                agent_results=results,
                duration_ms=duration_ms,
                error=(
                    f"Insufficient successful agents: {successful_count}/{min_required}. "
                    f"Failed: {failed_names}"
                ),
            )

        return StageResult(
            stage_name=stage_name,
            success=True,
            agent_results=results,
            duration_ms=duration_ms,
        )

    async def _run_delphi_r2(
        self,
        stage_def: StageDefinition,
        context: PipelineContext,
        start_ms: int,
    ) -> StageResult:
        """Специальная обработка стадии Delphi Round 2.

        Двухфазная стадия:
        1. Запуск Mediator (последовательно) -- синтез Round 1
        2. Запуск всех Delphi-персон параллельно (Round 2, с медиацией)

        Args:
            stage_def: Определение стадии.
            context: Контекст пайплайна.
            start_ms: Timestamp начала стадии.

        Returns:
            StageResult с результатами медиатора и R2-агентов.
        """
        all_results: list[AgentResult] = []

        # Phase 1: Mediator
        mediator = self.registry.get("mediator")
        if mediator is None:
            return StageResult(
                stage_name=stage_def.name.value,
                success=False,
                error="Mediator agent not found in registry",
                duration_ms=0,
            )

        mediator_result = await mediator.run(context)
        all_results.append(mediator_result)
        context.merge_agent_result(mediator_result)

        if not mediator_result.success:
            duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
            return StageResult(
                stage_name=stage_def.name.value,
                success=False,
                agent_results=all_results,
                duration_ms=duration_ms,
                error="Mediator failed, cannot proceed to Round 2",
            )

        await context.emit_progress(
            stage_def.name.value,
            "Медиация завершена, запуск раунда 2",
            0.60,
        )

        # Phase 2: Delphi Round 2 (параллельно)
        delphi_agents: list[BaseAgent] = []
        delphi_names = [
            "delphi_realist",
            "delphi_geostrategist",
            "delphi_economist",
            "delphi_media_expert",
            "delphi_devils_advocate",
        ]
        for name in delphi_names:
            agent = self.registry.get(name)
            if agent is not None:
                delphi_agents.append(agent)

        r2_results = await self._run_parallel(
            delphi_agents, context, stage_def.timeout_seconds,
        )
        all_results.extend(r2_results)

        for result in r2_results:
            context.merge_agent_result(result)

        # Минимум 4 из 5 R2-оценок
        successful_count = sum(1 for r in r2_results if r.success)
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        if successful_count < 4:
            return StageResult(
                stage_name=stage_def.name.value,
                success=False,
                agent_results=all_results,
                duration_ms=duration_ms,
                error=f"Insufficient Delphi R2 agents: {successful_count}/4",
            )

        return StageResult(
            stage_name=stage_def.name.value,
            success=True,
            agent_results=all_results,
            duration_ms=duration_ms,
        )

    async def _run_parallel(
        self,
        agents: list[BaseAgent],
        context: PipelineContext,
        timeout_seconds: int,
    ) -> list[AgentResult]:
        """Параллельный запуск нескольких агентов.

        Использует asyncio.gather с return_exceptions=False.
        Каждый агент обрабатывает свои ошибки внутри run() и всегда
        возвращает AgentResult, поэтому gather не бросает исключений.

        Args:
            agents: Список агентов для параллельного запуска.
            context: Общий контекст (агенты читают разные слоты).
            timeout_seconds: Общий таймаут на всю группу.

        Returns:
            Список AgentResult в порядке agents.
        """
        try:
            async with asyncio.timeout(timeout_seconds):
                results = await asyncio.gather(
                    *(agent.run(context) for agent in agents),
                )
        except asyncio.TimeoutError:
            logger.error(
                "Parallel stage timed out after %ds for agents: %s",
                timeout_seconds,
                [a.name for a in agents],
            )
            results = [
                AgentResult(
                    agent_name=a.name,
                    success=False,
                    error=f"Stage timeout after {timeout_seconds}s",
                )
                for a in agents
            ]

        return list(results)

    async def _run_sequential(
        self,
        agents: list[BaseAgent],
        context: PipelineContext,
    ) -> list[AgentResult]:
        """Последовательный запуск агентов.

        Каждый следующий агент видит результаты предыдущего (через context).

        Args:
            agents: Агенты для последовательного запуска.
            context: Общий контекст.

        Returns:
            Список AgentResult в порядке выполнения.
        """
        results: list[AgentResult] = []
        for agent in agents:
            result = await agent.run(context)
            context.merge_agent_result(result)
            results.append(result)
        return results

    def _build_response(
        self,
        context: PipelineContext,
        duration_ms: int,
    ) -> PredictionResponse:
        """Формирование финального PredictionResponse из контекста.

        Трансформирует List[FinalPrediction] из context.final_predictions
        в формат PredictionResponse, описанный в 00-overview.md.

        Args:
            context: Завершённый контекст с заполненными слотами.
            duration_ms: Общее время пайплайна.

        Returns:
            PredictionResponse для API / сохранения в БД.
        """
        from src.schemas.prediction import PredictionResponse, HeadlineOutput

        headlines = []
        for i, pred in enumerate(context.final_predictions, start=1):
            headlines.append(
                HeadlineOutput(
                    rank=i,
                    headline=pred.headline,
                    first_paragraph=pred.first_paragraph,
                    confidence=pred.confidence,
                    confidence_label=pred.confidence_label,
                    category=pred.category,
                    reasoning=pred.reasoning,
                    evidence_chain=pred.evidence_chain,
                    agent_agreement=pred.agent_agreement,
                    dissenting_views=pred.dissenting_views,
                )
            )

        return PredictionResponse(
            id=context.prediction_id,
            outlet=context.outlet,
            target_date=context.target_date,
            status="completed",
            duration_ms=duration_ms,
            total_cost_usd=context.get_total_cost_usd(),
            headlines=headlines,
            stage_results=[
                {
                    "stage": sr.stage_name,
                    "success": sr.success,
                    "duration_ms": sr.duration_ms,
                    "cost_usd": sr.total_cost_usd,
                }
                for sr in context.stage_results
            ],
        )

    def _build_error_response(
        self,
        context: PipelineContext,
        failed_stage: StageResult,
    ) -> PredictionResponse:
        """Формирование ответа при ошибке пайплайна.

        Args:
            context: Контекст на момент ошибки.
            failed_stage: Стадия, на которой произошла ошибка.

        Returns:
            PredictionResponse со статусом 'failed'.
        """
        from src.schemas.prediction import PredictionResponse

        return PredictionResponse(
            id=context.prediction_id,
            outlet=context.outlet,
            target_date=context.target_date,
            status="failed",
            duration_ms=context.get_total_duration_ms(),
            total_cost_usd=context.get_total_cost_usd(),
            headlines=[],
            error=failed_stage.error,
            failed_stage=failed_stage.stage_name,
            stage_results=[
                {
                    "stage": sr.stage_name,
                    "success": sr.success,
                    "duration_ms": sr.duration_ms,
                    "cost_usd": sr.total_cost_usd,
                }
                for sr in context.stage_results
            ],
        )
```

### Примечания по реализации

1. **Порядок стадий фиксирован**: `STAGES` -- class-level list. Порядок определяет зависимости данных. Нельзя менять порядок без изменения логики `PipelineContext`.

2. **DELPHI_R2 -- особый случай**: Эта стадия состоит из двух фаз (медиатор + повторный раунд). Выделена в отдельный метод `_run_delphi_r2`, потому что стандартная логика parallel/sequential не покрывает этот паттерн.

3. **Таймауты двойные**: Каждый агент имеет свой таймаут (`get_timeout_seconds()`), и стадия имеет общий таймаут. Агент может завершиться по своему таймауту раньше стадийного.

4. **`merge_agent_result` вызывается из оркестратора**: Не из агентов. Это гарантирует последовательную запись в контекст (после `gather`, в главном потоке).

5. **SSE-эмиссия**: Progress callback вызывается на каждом переходе между стадиями. Внутристадийный прогресс (например, "загружено 50 из 200 RSS-фидов") реализуется через дополнительные вызовы `context.emit_progress` из агентов, если нужен гранулярный прогресс.

6. **Обработка ошибок**:
   - Коллекторы (Stage 1): `min_successful=2` из 3. Если NewsScout упал, пайплайн продолжает с EventCalendar + OutletHistorian.
   - Аналитики (Stage 3): `min_successful=2` из 3. Геополитик упал -- экономист и медиа-аналитик продолжают.
   - Delphi (Stage 4): `min_successful=4` из 5. Один эксперт может выпасть.
   - Все остальные стадии: `required=True`, провал == остановка.

---

## 6. AgentRegistry (`src/agents/registry.py`)

Простой DI-контейнер для регистрации и получения агентов. Отвечает за инъекцию зависимостей (LLM-клиент) и lifecycle.

```python
"""src/agents/registry.py"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.base import BaseAgent
    from src.llm.providers import LLMClient


logger = logging.getLogger("agent_registry")


class AgentRegistry:
    """Реестр агентов пайплайна (DI-контейнер).

    Ответственности:
    - Хранение зарегистрированных агентов по имени
    - Инъекция LLM-клиента при регистрации
    - Предоставление агентов оркестратору по имени
    - Валидация уникальности имён

    Lifecycle:
    1. Создание registry с LLM-клиентом
    2. Регистрация всех агентов (register / register_class)
    3. Оркестратор запрашивает агентов через get()

    Пример использования:

        llm_client = LLMClient(config)
        registry = AgentRegistry(llm_client)

        registry.register_class(NewsScout)
        registry.register_class(EventCalendar)
        registry.register_class(OutletHistorian)
        # ... остальные агенты

        orchestrator = Orchestrator(registry)
        response = await orchestrator.run_prediction(request)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Инициализация реестра.

        Args:
            llm_client: LLM-клиент, который будет инъектирован во все агенты.
        """
        self._llm_client = llm_client
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Регистрация готового экземпляра агента.

        Args:
            agent: Экземпляр BaseAgent с уже инъектированным LLM-клиентом.

        Raises:
            ValueError: Если агент с таким именем уже зарегистрирован.
        """
        if agent.name in self._agents:
            raise ValueError(
                f"Agent '{agent.name}' is already registered. "
                f"Existing: {type(self._agents[agent.name]).__name__}, "
                f"New: {type(agent).__name__}"
            )
        self._agents[agent.name] = agent
        logger.debug("Registered agent: '%s' (%s)", agent.name,
                      type(agent).__name__)

    def register_class(self, agent_class: type[BaseAgent]) -> None:
        """Создание и регистрация агента из класса.

        Создаёт экземпляр агента, инъектируя LLM-клиент из реестра.

        Args:
            agent_class: Класс агента (наследник BaseAgent).

        Raises:
            ValueError: Если агент с таким именем уже зарегистрирован.
            TypeError: Если agent_class не является подклассом BaseAgent.
        """
        from src.agents.base import BaseAgent

        if not issubclass(agent_class, BaseAgent):
            raise TypeError(
                f"{agent_class.__name__} is not a subclass of BaseAgent"
            )

        agent = agent_class(llm_client=self._llm_client)
        self.register(agent)

    def get(self, name: str) -> BaseAgent | None:
        """Получение агента по имени.

        Args:
            name: Уникальное имя агента (BaseAgent.name).

        Returns:
            Экземпляр агента или None если не найден.
        """
        agent = self._agents.get(name)
        if agent is None:
            logger.warning("Agent '%s' not found in registry", name)
        return agent

    def get_required(self, name: str) -> BaseAgent:
        """Получение агента по имени с обязательной проверкой.

        Args:
            name: Уникальное имя агента.

        Returns:
            Экземпляр агента.

        Raises:
            KeyError: Если агент не найден.
        """
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(
                f"Required agent '{name}' not found in registry. "
                f"Available: {list(self._agents.keys())}"
            )
        return agent

    def list_agents(self) -> list[str]:
        """Список имён всех зарегистрированных агентов.

        Returns:
            Отсортированный список имён.
        """
        return sorted(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents


def build_default_registry(llm_client: LLMClient) -> AgentRegistry:
    """Фабрика: создание реестра со всеми агентами системы.

    Регистрирует все агенты в правильном порядке. Используется при
    старте приложения и воркера.

    Args:
        llm_client: Сконфигурированный LLM-клиент.

    Returns:
        AgentRegistry с полным набором агентов.
    """
    # Импорты агентов (lazy, чтобы не грузить всё при импорте registry.py)
    from src.agents.collectors.news_scout import NewsScout
    from src.agents.collectors.event_calendar import EventCalendar
    from src.agents.collectors.outlet_historian import OutletHistorian

    from src.agents.analysts.event_trend import EventTrendAnalyzer
    from src.agents.analysts.geopolitical import GeopoliticalAnalyst
    from src.agents.analysts.economic import EconomicAnalyst
    from src.agents.analysts.media import MediaAnalyst

    from src.agents.forecasters.delphi import (
        RealistAgent,
        GeostrategistAgent,
        EconomistAgent,
        MediaExpertAgent,
        DevilsAdvocateAgent,
    )
    from src.agents.forecasters.mediator import MediatorAgent
    from src.agents.forecasters.judge import JudgeAgent

    from src.agents.generators.framing import FramingAgent
    from src.agents.generators.style_replicator import StyleReplicatorAgent
    from src.agents.generators.quality_gate import QualityGateAgent

    registry = AgentRegistry(llm_client)

    # Collectors
    registry.register_class(NewsScout)
    registry.register_class(EventCalendar)
    registry.register_class(OutletHistorian)

    # Analysts
    registry.register_class(EventTrendAnalyzer)
    registry.register_class(GeopoliticalAnalyst)
    registry.register_class(EconomicAnalyst)
    registry.register_class(MediaAnalyst)

    # Forecasters (Delphi)
    registry.register_class(RealistAgent)
    registry.register_class(GeostrategistAgent)
    registry.register_class(EconomistAgent)
    registry.register_class(MediaExpertAgent)
    registry.register_class(DevilsAdvocateAgent)
    registry.register_class(MediatorAgent)
    registry.register_class(JudgeAgent)

    # Generators
    registry.register_class(FramingAgent)
    registry.register_class(StyleReplicatorAgent)
    registry.register_class(QualityGateAgent)

    logger.info(
        "Registry initialized with %d agents: %s",
        len(registry), registry.list_agents(),
    )

    return registry
```

### Примечания по реализации

1. **Один LLM-клиент на все агенты**: `LLMClient` -- обёртка над OpenRouter. Каждый агент использует его для вызовов, указывая модель в параметрах. Клиент мультиплексирует запросы к разным моделям через один HTTP-пул.

2. **Lazy imports в `build_default_registry`**: Импорт конкретных агентов происходит при вызове фабрики, а не при импорте модуля `registry.py`. Это предотвращает циклические импорты и ускоряет загрузку.

3. **Расширяемость**: Для добавления нового агента достаточно: (a) создать класс-наследник BaseAgent, (b) добавить в `build_default_registry`, (c) добавить в `Orchestrator.STAGES`.

4. **Тестирование**: В тестах можно создать registry с mock LLM-клиентом и зарегистрировать только нужные агенты.

---

## 7. Схемы запроса и ответа (`src/schemas/prediction.py`)

Для полноты -- минимальные схемы, на которые ссылается оркестратор.

```python
"""src/schemas/prediction.py"""

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


class HeadlineOutput(BaseModel):
    """Один прогнозированный заголовок в финальном ответе."""

    rank: int = Field(..., ge=1, le=10)
    headline: str
    first_paragraph: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str  # "высокая", "средняя", "низкая"
    category: str  # "экономика", "политика", "общество", etc.
    reasoning: str
    evidence_chain: list[dict[str, str]] = Field(default_factory=list)
    agent_agreement: str  # "consensus", "majority", "split"
    dissenting_views: list[dict[str, str]] = Field(default_factory=list)


class PredictionResponse(BaseModel):
    """Финальный ответ пайплайна прогнозирования."""

    id: str
    outlet: str
    target_date: date
    status: str  # "completed", "failed", "in_progress"
    duration_ms: int = 0
    total_cost_usd: float = 0.0
    headlines: list[HeadlineOutput] = Field(default_factory=list)
    error: str | None = None
    failed_stage: str | None = None
    stage_results: list[dict[str, Any]] = Field(default_factory=list)
```

---

## 8. Диаграмма взаимодействия

```
PredictionRequest
       │
       ▼
 ┌─────────────┐      ┌───────────────┐      ┌────────────┐
 │ Orchestrator │─────►│ AgentRegistry │─────►│ LLMClient  │
 │              │      │               │      │            │
 │ STAGES[]     │      │ _agents{}     │      │ OpenRouter  │
 │              │      │               │      │             │
 └──────┬───────┘      └───────────────┘      └────────────┘
        │
        │  for stage in STAGES:
        │
        ▼
 ┌─────────────────────────────────────┐
 │           _run_stage()              │
 │                                     │
 │  parallel:  gather(a1, a2, a3)      │
 │  sequential: a1 -> a2 -> a3         │
 │                                     │
 │  Каждый агент:                      │
 │    BaseAgent.run(context)           │
 │      ├── validate_context()         │
 │      ├── execute()   <── бизнес     │
 │      │     └── llm.chat()           │
 │      │     └── track_llm_usage()    │
 │      └── return AgentResult         │
 │                                     │
 │  context.merge_agent_result(r)      │
 │  context.emit_progress(...)         │
 └──────┬──────────────────────────────┘
        │
        ▼
 PipelineContext.final_predictions
        │
        ▼
 PredictionResponse
```

---

## 9. Реестр имён агентов

Таблица всех агентов системы с их именами (для `AgentRegistry`) и стадиями:

| Имя агента | Класс | Стадия | Модуль |
|---|---|---|---|
| `news_scout` | `NewsScout` | Collection | `collectors/news_scout.py` |
| `event_calendar` | `EventCalendar` | Collection | `collectors/event_calendar.py` |
| `outlet_historian` | `OutletHistorian` | Collection | `collectors/outlet_historian.py` |
| `event_trend_analyzer` | `EventTrendAnalyzer` | Event Identification | `analysts/event_trend.py` |
| `geopolitical_analyst` | `GeopoliticalAnalyst` | Trajectory | `analysts/geopolitical.py` |
| `economic_analyst` | `EconomicAnalyst` | Trajectory | `analysts/economic.py` |
| `media_analyst` | `MediaAnalyst` | Trajectory | `analysts/media.py` |
| `delphi_realist` | `RealistAgent` | Delphi R1 / R2 | `forecasters/delphi.py` |
| `delphi_geostrategist` | `GeostrategistAgent` | Delphi R1 / R2 | `forecasters/delphi.py` |
| `delphi_economist` | `EconomistAgent` | Delphi R1 / R2 | `forecasters/delphi.py` |
| `delphi_media_expert` | `MediaExpertAgent` | Delphi R1 / R2 | `forecasters/delphi.py` |
| `delphi_devils_advocate` | `DevilsAdvocateAgent` | Delphi R1 / R2 | `forecasters/delphi.py` |
| `mediator` | `MediatorAgent` | Delphi R2 | `forecasters/mediator.py` |
| `judge` | `JudgeAgent` | Consensus | `forecasters/judge.py` |
| `framing` | `FramingAgent` | Framing | `generators/framing.py` |
| `style_replicator` | `StyleReplicatorAgent` | Generation | `generators/style_replicator.py` |
| `quality_gate` | `QualityGateAgent` | Quality Gate | `generators/quality_gate.py` |

**Итого: 17 агентов.**

---

## 10. Стратегия обработки ошибок

| Тип ошибки | Стратегия | Пример |
|---|---|---|
| Таймаут агента | `AgentResult(success=False)`, продолжение если `min_successful` позволяет | RSS-фид не ответил за 5 минут |
| Таймаут стадии | Все агенты стадии получают `success=False` | Все 3 коллектора зависли |
| LLM API ошибка | Retry с backoff (3 попытки) внутри `LLMClient`, затем `success=False` | OpenRouter 429 |
| Невалидный LLM output | Retry 1 раз с уточнённым промптом, затем `success=False` | JSON не парсится |
| Недостаток данных | `validate_context()` возвращает ошибку, агент не запускается | Нет signals для кластеризации |
| Критическая стадия провалилась | `PredictionResponse(status="failed")`, SSE event "failed" | Judge не смог проранжировать |
| Некритическая деградация | Продолжение с меньшим количеством данных | 1 из 3 коллекторов упал |
