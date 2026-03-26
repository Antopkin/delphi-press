# 04 — Агенты-аналитики

> Реализуемые файлы: `src/agents/analysts/event_trend.py`, `src/agents/analysts/geopolitical.py`, `src/agents/analysts/economic.py`, `src/agents/analysts/media.py`
>
> Зависимости: `src/agents/base.py` (02-agents-core.md), `src/schemas/events.py` (03-collectors.md)

---

## Обзор

Аналитики -- стадии 2 и 3 пайплайна. Они берут сырые данные коллекторов и трансформируют их в структурированную аналитику для Delphi-прогнозирования.

| Стадия | Агент | Что делает | Input | Output |
|---|---|---|---|---|
| **Stage 2** | EventTrendAnalyzer | Кластеризация сигналов в событийные нити | SignalRecord[] + ScheduledEvent[] | EventThread[] (top-20) |
| **Stage 3** | GeopoliticalAnalyst | Геополитический контекст и сценарии | EventThread[] | GeopoliticalAssessment[] |
| **Stage 3** | EconomicAnalyst | Экономический контекст и индикаторы | EventThread[] | EconomicAssessment[] |
| **Stage 3** | MediaAnalyst | Медийная значимость и редакционный fit | EventThread[] + OutletProfile | MediaAssessment[] |

Stage 2 (EventTrendAnalyzer) запускается последовательно после коллекторов. Stage 3 (три аналитика) запускается **параллельно** после Stage 2. Допускается провал 1 из 3 аналитиков Stage 3 (`min_successful=2`).

---

## 1. Общие схемы аналитиков (`src/schemas/events.py`, продолжение)

```python
"""src/schemas/events.py — Часть 2: Схемы аналитиков."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# =====================================================================
# EventThread — результат EventTrendAnalyzer (Stage 2)
# =====================================================================

class EventThread(BaseModel):
    """Событийная нить -- кластер связанных сигналов, объединённых
    общей темой/событием.

    Создаётся EventTrendAnalyzer из 100-200 SignalRecord.
    Одна нить = одна тема/событие, которое может стать заголовком.
    """

    id: str = Field(
        ...,
        description="Уникальный идентификатор нити. Формат: 'thread_{hash}'.",
    )

    title: str = Field(
        ...,
        description="Краткое название нити (1 предложение). "
        "Присваивается LLM на основе кластера. "
        "Пример: 'Эскалация тарифной войны США-Китай'.",
        max_length=200,
    )

    summary: str = Field(
        ...,
        description="Развёрнутое описание нити: что происходит, "
        "ключевые факты, текущий статус. 2-4 предложения.",
        max_length=1000,
    )

    # --- Состав кластера ---

    signal_ids: list[str] = Field(
        default_factory=list,
        description="ID сигналов, входящих в этот кластер.",
    )

    scheduled_event_ids: list[str] = Field(
        default_factory=list,
        description="ID запланированных событий, связанных с нитью.",
    )

    cluster_size: int = Field(
        default=0,
        description="Общее количество сигналов в кластере.",
    )

    # --- Метаданные ---

    category: str = Field(
        default="",
        description="Основная категория: 'politics', 'economy', "
        "'military', 'diplomacy', 'society', 'technology', "
        "'culture', 'sports', 'environment'.",
    )

    entities: list[str] = Field(
        default_factory=list,
        description="Ключевые сущности нити (люди, организации, страны). "
        "Дедуплицированные, отсортированные по частоте.",
    )

    source_diversity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Разнообразие источников (0-1). "
        "1.0 = все сигналы из разных источников. "
        "Рассчитывается: unique_sources / cluster_size.",
    )

    # --- Временные характеристики ---

    earliest_signal: datetime | None = Field(
        default=None,
        description="Timestamp самого раннего сигнала в кластере.",
    )

    latest_signal: datetime | None = Field(
        default=None,
        description="Timestamp самого свежего сигнала.",
    )

    recency_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Свежесть нити (0-1). 1.0 = все сигналы за последние "
        "24 часа. Экспоненциальное затухание по часам.",
    )

    # --- Оценки ---

    significance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Итоговый балл значимости (0-1). "
        "Формула: 0.3*importance + 0.25*cluster_size_norm + "
        "0.2*recency + 0.15*source_diversity + 0.1*entity_prominence.",
    )

    importance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Важность темы (0-1). Оценивается LLM: "
        "'насколько эта тема важна для мировой повестки?'.",
    )

    entity_prominence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Значимость упомянутых сущностей (0-1). "
        "Трамп/Путин > местный чиновник.",
    )

    # --- Аналитические слоты (заполняются на Stage 3) ---

    assessments: dict[str, object] = Field(
        default_factory=dict,
        description="Оценки от аналитиков Stage 3. "
        "Ключи: 'geopolitical_analyst', 'economic_analyst', "
        "'media_analyst'. Значения: соответствующие *Assessment.",
    )


# =====================================================================
# EventTrajectory — анализ траектории события
# =====================================================================

class ScenarioType(str, Enum):
    """Тип сценария развития."""
    BASELINE = "baseline"         # Наиболее вероятный
    OPTIMISTIC = "optimistic"     # Позитивное развитие
    PESSIMISTIC = "pessimistic"   # Негативное развитие
    WILDCARD = "wildcard"         # Неожиданный поворот


class Scenario(BaseModel):
    """Один сценарий развития события."""

    scenario_type: ScenarioType = Field(
        ...,
        description="Тип сценария.",
    )

    description: str = Field(
        ...,
        description="Описание сценария: что произойдёт, какие последствия. "
        "2-3 предложения.",
        max_length=500,
    )

    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Вероятность сценария (0-1). "
        "Сумма по всем сценариям одного события = 1.0.",
    )

    key_indicators: list[str] = Field(
        default_factory=list,
        description="Индикаторы, которые укажут на реализацию этого "
        "сценария. 2-3 штуки.",
    )

    headline_potential: str = Field(
        default="",
        description="Какой заголовок может породить этот сценарий. "
        "Не финальный -- черновик для Delphi.",
    )


class EventTrajectory(BaseModel):
    """Траектория развития событийной нити.

    Для каждого EventThread генерируется одна EventTrajectory,
    описывающая текущее состояние, динамику и 3 сценария.
    """

    thread_id: str = Field(
        ...,
        description="ID связанного EventThread.",
    )

    # --- Текущее состояние ---

    current_state: str = Field(
        ...,
        description="Описание текущего состояния события. "
        "Где мы сейчас? 2-3 предложения.",
        max_length=500,
    )

    momentum: str = Field(
        ...,
        description="Динамика: 'escalating', 'stable', 'de_escalating', "
        "'emerging', 'culminating', 'fading'.",
    )

    momentum_explanation: str = Field(
        default="",
        description="Почему такой моментум. 1-2 предложения.",
    )

    # --- Сценарии ---

    scenarios: list[Scenario] = Field(
        ...,
        description="3 сценария развития: baseline, optimistic/pessimistic, "
        "wildcard. Сумма вероятностей = 1.0.",
        min_length=2,
        max_length=4,
    )

    # --- Ключевые факторы ---

    key_drivers: list[str] = Field(
        default_factory=list,
        description="Ключевые факторы, определяющие развитие. 3-5 штук.",
    )

    uncertainties: list[str] = Field(
        default_factory=list,
        description="Основные неопределённости. 2-3 штуки.",
    )


# =====================================================================
# CrossImpactMatrix — перекрёстные влияния между событиями
# =====================================================================

class CrossImpactEntry(BaseModel):
    """Одна ячейка матрицы перекрёстных влияний."""

    source_thread_id: str = Field(
        ...,
        description="ID события-причины.",
    )

    target_thread_id: str = Field(
        ...,
        description="ID события-следствия.",
    )

    impact_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Сила влияния (-1 до +1). "
        "Положительные: усиливает/ускоряет. "
        "Отрицательные: ослабляет/замедляет. "
        "0: нет влияния.",
    )

    explanation: str = Field(
        default="",
        description="Краткое объяснение механизма влияния.",
        max_length=200,
    )


class CrossImpactMatrix(BaseModel):
    """Матрица перекрёстных влияний между событийными нитями.

    Описывает, как развитие одного события влияет на другие.
    Используется в Delphi для согласования прогнозов.
    """

    entries: list[CrossImpactEntry] = Field(
        default_factory=list,
        description="Ненулевые ячейки матрицы (sparse representation). "
        "Для 20 событий: до 380 пар (20*19), но обычно 30-50 "
        "значимых связей.",
    )

    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
    )

    def get_impact(
        self, source_id: str, target_id: str,
    ) -> float:
        """Получить силу влияния source -> target.

        Returns:
            impact_score или 0.0 если связь не найдена.
        """
        for entry in self.entries:
            if (entry.source_thread_id == source_id
                    and entry.target_thread_id == target_id):
                return entry.impact_score
        return 0.0

    def get_influences_on(self, target_id: str) -> list[CrossImpactEntry]:
        """Все события, влияющие на target."""
        return [e for e in self.entries if e.target_thread_id == target_id]

    def get_influences_from(self, source_id: str) -> list[CrossImpactEntry]:
        """Все события, на которые влияет source."""
        return [e for e in self.entries if e.source_thread_id == source_id]


# =====================================================================
# Assessments — оценки аналитиков Stage 3
# =====================================================================

class GeopoliticalAssessment(BaseModel):
    """Геополитическая оценка событийной нити.

    Создаётся GeopoliticalAnalyst для каждого EventThread.
    """

    thread_id: str = Field(
        ...,
        description="ID оцениваемого EventThread.",
    )

    # --- Акторы ---

    strategic_actors: list[StrategicActor] = Field(
        default_factory=list,
        description="Ключевые геополитические акторы, вовлечённые "
        "в событие. 2-5 акторов.",
    )

    # --- Динамика ---

    power_dynamics: str = Field(
        default="",
        description="Описание расстановки сил: кто усиливается, "
        "кто ослабевает. 2-3 предложения.",
        max_length=500,
    )

    alliance_shifts: list[str] = Field(
        default_factory=list,
        description="Возможные сдвиги в альянсах. "
        "Пример: 'Индия сближается с Россией по энергетике'.",
    )

    escalation_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Вероятность эскалации (0-1). "
        "Для военных конфликтов, санкционных войн, "
        "дипломатических кризисов.",
    )

    # --- Последствия ---

    second_order_effects: list[str] = Field(
        default_factory=list,
        description="Эффекты второго порядка: что произойдёт "
        "как следствие. 3-5 пунктов.",
    )

    sanctions_risk: str = Field(
        default="none",
        description="Санкционный риск: 'none', 'low', 'medium', "
        "'high', 'imminent'.",
    )

    military_implications: str = Field(
        default="",
        description="Военные последствия (если применимо).",
        max_length=300,
    )

    # --- Прогностическая ценность ---

    headline_angles: list[str] = Field(
        default_factory=list,
        description="Возможные углы подачи для заголовков с "
        "геополитическим фреймом. 2-3 варианта.",
    )


class StrategicActor(BaseModel):
    """Геополитический актор и его позиция."""

    name: str = Field(
        ...,
        description="Имя актора (страна, лидер, организация).",
    )

    role: str = Field(
        default="",
        description="Роль в событии: 'initiator', 'target', 'mediator', "
        "'ally', 'observer', 'spoiler'.",
    )

    interests: list[str] = Field(
        default_factory=list,
        description="Ключевые интересы актора в контексте события.",
    )

    likely_actions: list[str] = Field(
        default_factory=list,
        description="Вероятные действия в ближайшие дни.",
    )

    leverage: str = Field(
        default="",
        description="Рычаги влияния: экономические, военные, "
        "дипломатические, информационные.",
    )


class EconomicAssessment(BaseModel):
    """Экономическая оценка событийной нити.

    Создаётся EconomicAnalyst для каждого EventThread.
    """

    thread_id: str = Field(
        ...,
        description="ID оцениваемого EventThread.",
    )

    # --- Индикаторы ---

    affected_indicators: list[EconomicIndicator] = Field(
        default_factory=list,
        description="Экономические индикаторы, на которые событие "
        "влияет. 2-5 индикаторов.",
    )

    # --- Рыночные сигналы ---

    market_impact: str = Field(
        default="neutral",
        description="Ожидаемое влияние на рынки: 'strongly_negative', "
        "'negative', 'neutral', 'positive', 'strongly_positive'.",
    )

    affected_sectors: list[str] = Field(
        default_factory=list,
        description="Затронутые сектора экономики. "
        "Примеры: ['энергетика', 'технологии', 'финансы'].",
    )

    supply_chain_impact: str = Field(
        default="",
        description="Влияние на цепочки поставок (если есть). "
        "1-2 предложения.",
        max_length=300,
    )

    # --- Фискальный контекст ---

    fiscal_calendar_events: list[str] = Field(
        default_factory=list,
        description="Связанные события фискального календаря: "
        "заседания ЦБ, публикация данных, отчётности.",
    )

    central_bank_signals: list[str] = Field(
        default_factory=list,
        description="Релевантные сигналы от центробанков.",
    )

    # --- Торговля ---

    trade_flow_impact: str = Field(
        default="",
        description="Влияние на торговые потоки: тарифы, санкции, "
        "квоты, эмбарго.",
        max_length=300,
    )

    commodity_prices: list[str] = Field(
        default_factory=list,
        description="Затронутые товарные рынки. "
        "Примеры: ['нефть Brent +2-3%', 'золото стабильно'].",
    )

    # --- Занятость ---

    employment_impact: str = Field(
        default="",
        description="Влияние на рынок труда (если значимое).",
        max_length=200,
    )

    # --- Прогностическая ценность ---

    headline_angles: list[str] = Field(
        default_factory=list,
        description="Возможные экономические углы для заголовков. "
        "2-3 варианта.",
    )


class EconomicIndicator(BaseModel):
    """Экономический индикатор, затронутый событием."""

    name: str = Field(
        ...,
        description="Название индикатора. Примеры: 'GDP growth', "
        "'CPI', 'S&P 500', 'USD/RUB', 'Oil Brent'.",
    )

    direction: str = Field(
        default="neutral",
        description="Ожидаемое направление: 'up', 'down', 'neutral', "
        "'volatile'.",
    )

    magnitude: str = Field(
        default="low",
        description="Масштаб изменения: 'low', 'medium', 'high'.",
    )

    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Уверенность в прогнозе направления (0-1).",
    )

    timeframe: str = Field(
        default="days",
        description="Временной горизонт: 'immediate', 'days', "
        "'weeks', 'months'.",
    )


class MediaAssessment(BaseModel):
    """Медийная оценка событийной нити относительно целевого СМИ.

    Создаётся MediaAnalyst для каждого EventThread.
    Этот аналитик отвечает не на вопрос 'что произойдёт',
    а на вопрос 'будет ли ЭТО ИЗДАНИЕ об этом писать'.
    """

    thread_id: str = Field(
        ...,
        description="ID оцениваемого EventThread.",
    )

    # --- Новостная ценность (6 измерений) ---

    newsworthiness: NewsworthinessScore = Field(
        ...,
        description="Оценка новостной ценности по 6 измерениям.",
    )

    # --- Редакционный fit ---

    editorial_fit: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Насколько событие соответствует редакционной "
        "политике издания (0-1). "
        "1.0 = идеально в фокусе, 0.0 = издание не покроет.",
    )

    editorial_fit_explanation: str = Field(
        default="",
        description="Почему событие подходит/не подходит изданию.",
        max_length=300,
    )

    # --- Позиция в новостном цикле ---

    news_cycle_position: str = Field(
        default="emerging",
        description="Где событие находится в новостном цикле: "
        "'breaking' (только что), 'developing' (развивается), "
        "'emerging' (набирает силу), 'peak' (пик внимания), "
        "'declining' (затихает), 'follow_up' (пост-событие).",
    )

    saturation: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Медийная насыщенность (0-1). "
        "Если тема уже вездесуща (saturation=0.9), "
        "издание может предпочесть fresh angle или другую тему.",
    )

    # --- Прогноз покрытия ---

    coverage_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Вероятность, что издание опубликует материал "
        "по этой теме (0-1).",
    )

    predicted_prominence: str = Field(
        default="secondary",
        description="Предполагаемая заметность: "
        "'top_headline' (главная), 'major' (топ-5), "
        "'secondary' (в ленте), 'brief' (кратко), 'ignore' (не покроет).",
    )

    likely_framing: str = Field(
        default="",
        description="Предполагаемый фрейм подачи этим изданием. "
        "Пример: 'Через призму национальной безопасности'.",
        max_length=300,
    )

    # --- Конкуренция ---

    competing_stories: list[str] = Field(
        default_factory=list,
        description="Какие другие истории будут конкурировать за "
        "внимание в этот день.",
    )

    # --- Углы ---

    headline_angles: list[str] = Field(
        default_factory=list,
        description="Возможные углы заголовков, специфичные для "
        "данного издания. 2-4 варианта.",
    )


class NewsworthinessScore(BaseModel):
    """Оценка новостной ценности по 6 измерениям.

    Основана на модифицированной модели Galtung & Ruge.
    """

    timeliness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Актуальность (0-1). Насколько событие привязано "
        "к конкретному моменту.",
    )

    impact: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Масштаб влияния (0-1). Сколько людей затронет.",
    )

    prominence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Известность участников (0-1). Мировые лидеры = 1.0.",
    )

    proximity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Близость к аудитории издания (0-1). "
        "Географическая и культурная.",
    )

    conflict: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Степень конфликтности (0-1). "
        "Конфликт = высокая медийная ценность.",
    )

    novelty: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Необычность, неожиданность (0-1). "
        "'Собака укусила человека' = 0, 'Человек укусил собаку' = 1.",
    )

    @property
    def composite_score(self) -> float:
        """Взвешенный композитный балл.

        Веса: impact(0.25) + timeliness(0.20) + prominence(0.20) +
              conflict(0.15) + proximity(0.10) + novelty(0.10)
        """
        return (
            0.25 * self.impact
            + 0.20 * self.timeliness
            + 0.20 * self.prominence
            + 0.15 * self.conflict
            + 0.10 * self.proximity
            + 0.10 * self.novelty
        )
```

---

## 2. EventTrendAnalyzer (`src/agents/analysts/event_trend.py`)

Агент кластеризации и ранжирования сигналов. Преобразует 100-200 сырых сигналов в 20 структурированных событийных нитей.

### Логика работы

1. **Подготовка текстов**: title + summary для каждого SignalRecord
2. **Эмбеддинг**: batch-эмбеддинг через LLM API (OpenAI embeddings или Voyage AI)
3. **Кластеризация**: HDBSCAN на эмбеддингах (density-based, не требует k)
4. **LLM-лейблинг**: для каждого кластера -- название и summary через LLM
5. **Интеграция ScheduledEvent**: привязка запланированных событий к кластерам
6. **Scoring**: расчёт significance_score по формуле
7. **Ранжирование**: top-20 по significance_score
8. **Trajectory Analysis**: для каждой нити -- текущее состояние, моментум, 3 сценария
9. **Cross-Impact Matrix**: LLM-оценка перекрёстных влияний

### Сигнатуры

```python
"""src/agents/analysts/event_trend.py"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from src.agents.base import BaseAgent
from src.schemas.events import (
    EventThread,
    EventTrajectory,
    CrossImpactMatrix,
    CrossImpactEntry,
    Scenario,
    ScenarioType,
    SignalRecord,
    ScheduledEvent,
)

if TYPE_CHECKING:
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class EventTrendAnalyzer(BaseAgent):
    """Агент кластеризации сигналов в событийные нити.

    Запускается на Stage 2 (Event Identification).
    Единственный агент стадии, запускается последовательно.

    Процесс: embed -> cluster -> label -> score -> rank -> trajectories

    LLM-модели:
    - Эмбеддинг: text-embedding-3-small (OpenAI через OpenRouter)
    - Лейблинг кластеров: openai/gpt-4o-mini
    - Траектории: anthropic/claude-sonnet-4
    - Cross-impact matrix: anthropic/claude-sonnet-4

    Стоимость: ~$1.50-3.00 за прогноз.
    """

    name = "event_trend_analyzer"

    # Параметры кластеризации
    HDBSCAN_MIN_CLUSTER_SIZE = 3
    HDBSCAN_MIN_SAMPLES = 2
    HDBSCAN_METRIC = "cosine"

    # Параметры ранжирования
    MAX_THREADS = 20

    # Веса для significance_score
    W_IMPORTANCE = 0.30
    W_CLUSTER_SIZE = 0.25
    W_RECENCY = 0.20
    W_SOURCE_DIVERSITY = 0.15
    W_ENTITY_PROMINENCE = 0.10

    def get_timeout_seconds(self) -> int:
        return 300  # 5 минут

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.signals and not context.scheduled_events:
            return "No signals or scheduled events to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Основная логика кластеризации и анализа.

        Returns:
            {
                "event_threads": List[EventThread],
                "trajectories": List[EventTrajectory],
                "cross_impact_matrix": CrossImpactMatrix,
            }
        """
        signals = context.signals
        scheduled_events = context.scheduled_events

        # 1. Эмбеддинг сигналов
        texts = [f"{s.title}. {s.summary}" for s in signals]
        embeddings = await self._embed_texts(texts)

        # 2. Кластеризация
        cluster_labels = self._cluster_embeddings(embeddings)

        # 3. Формирование кластеров
        raw_clusters = self._build_clusters(signals, cluster_labels)

        # 4. Интеграция ScheduledEvent
        raw_clusters = self._integrate_scheduled_events(
            raw_clusters, scheduled_events, embeddings, texts,
        )

        # 5. LLM-лейблинг и scoring
        threads = await self._label_and_score_clusters(raw_clusters)

        # 6. Ранжирование
        threads.sort(key=lambda t: t.significance_score, reverse=True)
        threads = threads[:self.MAX_THREADS]

        self.logger.info("Identified %d event threads from %d signals",
                         len(threads), len(signals))

        # 7. Trajectory analysis (параллельно для всех нитей)
        trajectories = await self._analyze_trajectories(threads)

        # 8. Cross-impact matrix
        cross_impact = await self._build_cross_impact_matrix(threads)

        return {
            "event_threads": threads,
            "trajectories": trajectories,
            "cross_impact_matrix": cross_impact,
        }

    async def _embed_texts(
        self,
        texts: list[str],
    ) -> np.ndarray:
        """Batch-эмбеддинг текстов через LLM API.

        Использует text-embedding-3-small (1536 dim, дешёвый).
        Batch size: 100 текстов за раз (лимит API).

        Args:
            texts: Тексты для эмбеддинга.

        Returns:
            np.ndarray shape (len(texts), 1536).
        """
        ...

    def _cluster_embeddings(
        self,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """HDBSCAN-кластеризация на эмбеддингах.

        HDBSCAN vs K-Means:
        - Не требует задания числа кластеров
        - Находит кластеры произвольной формы
        - Помечает шум как -1 (одиночные сигналы)

        Параметры:
        - min_cluster_size=3: минимум 3 сигнала для кластера
        - min_samples=2: плотность ядра
        - metric='cosine': подходит для текстовых эмбеддингов

        Зависимость: `hdbscan` pip package.

        Args:
            embeddings: np.ndarray shape (n, 1536).

        Returns:
            np.ndarray shape (n,) с метками кластеров (-1 = шум).
        """
        ...

    def _build_clusters(
        self,
        signals: list[SignalRecord],
        labels: np.ndarray,
    ) -> list[dict]:
        """Сборка кластеров из сигналов и меток.

        Группирует сигналы по кластерным меткам. Шум (-1) собирается
        в отдельный pseudo-кластер только если > 5 сигналов (может
        содержать "одиночные" важные темы).

        Args:
            signals: Исходные сигналы.
            labels: Метки кластеров от HDBSCAN.

        Returns:
            Список словарей: [{"signals": [...], "label": int}, ...]
        """
        ...

    def _integrate_scheduled_events(
        self,
        clusters: list[dict],
        scheduled_events: list[ScheduledEvent],
        embeddings: np.ndarray,
        texts: list[str],
    ) -> list[dict]:
        """Привязка запланированных событий к кластерам.

        Стратегия:
        1. Для каждого ScheduledEvent эмбеддим title + description
        2. Находим ближайший кластер по cosine similarity
        3. Если similarity > 0.7 -- привязываем к кластеру
        4. Если < 0.7 -- создаём новый кластер из одного события

        Args:
            clusters: Существующие кластеры.
            scheduled_events: Запланированные события.
            embeddings: Эмбеддинги сигналов.
            texts: Тексты сигналов.

        Returns:
            Обновлённые кластеры (с привязанными событиями).
        """
        ...

    async def _label_and_score_clusters(
        self,
        clusters: list[dict],
    ) -> list[EventThread]:
        """LLM-лейблинг кластеров + расчёт significance_score.

        Для каждого кластера (batch по 5):

        Промпт (модель: openai/gpt-4o-mini):
        ```
        For each cluster of news signals, provide:
        1. title: concise name for this event/topic (max 20 words)
        2. summary: what is happening (2-3 sentences)
        3. category: politics/economy/military/diplomacy/society/
                     technology/culture/sports/environment
        4. importance: how important is this for world news (0.0-1.0)
        5. entity_prominence: how prominent are the key actors (0.0-1.0)

        Cluster 1 (5 signals):
        - "Trump announces new tariffs on Chinese EVs"
        - "Beijing threatens retaliation over US trade moves"
        - "EU considers alignment with US on China tariffs"
        ...

        Return JSON array.
        ```

        significance_score = (
            W_IMPORTANCE * importance +
            W_CLUSTER_SIZE * normalized_cluster_size +
            W_RECENCY * recency_score +
            W_SOURCE_DIVERSITY * source_diversity +
            W_ENTITY_PROMINENCE * entity_prominence
        )

        Нормализация cluster_size: min-max по всем кластерам.
        Recency: exponential decay, half-life = 12 hours.
        Source diversity: unique_sources / cluster_size.

        Args:
            clusters: Сырые кластеры.

        Returns:
            Список EventThread с заполненными полями.
        """
        ...

    def _calculate_significance_score(
        self,
        importance: float,
        cluster_size: int,
        max_cluster_size: int,
        recency_score: float,
        source_diversity: float,
        entity_prominence: float,
    ) -> float:
        """Расчёт итогового significance_score.

        Формула:
            0.30 * importance
          + 0.25 * (cluster_size / max_cluster_size)
          + 0.20 * recency_score
          + 0.15 * source_diversity
          + 0.10 * entity_prominence

        Args:
            importance: Оценка важности от LLM (0-1).
            cluster_size: Число сигналов в кластере.
            max_cluster_size: Максимальный размер кластера (для нормализации).
            recency_score: Свежесть (0-1).
            source_diversity: Разнообразие источников (0-1).
            entity_prominence: Значимость сущностей (0-1).

        Returns:
            float 0.0-1.0.
        """
        cluster_norm = cluster_size / max(max_cluster_size, 1)
        return (
            self.W_IMPORTANCE * importance
            + self.W_CLUSTER_SIZE * cluster_norm
            + self.W_RECENCY * recency_score
            + self.W_SOURCE_DIVERSITY * source_diversity
            + self.W_ENTITY_PROMINENCE * entity_prominence
        )

    def _calculate_recency_score(
        self,
        latest_signal: datetime | None,
    ) -> float:
        """Расчёт свежести нити.

        Экспоненциальное затухание с half-life = 12 часов.
        recency = 2^(-hours_ago / 12)

        Args:
            latest_signal: Timestamp свежайшего сигнала.

        Returns:
            float 0.0-1.0.
        """
        if latest_signal is None:
            return 0.0
        hours_ago = (datetime.utcnow() - latest_signal).total_seconds() / 3600
        return 2.0 ** (-hours_ago / 12.0)

    async def _analyze_trajectories(
        self,
        threads: list[EventThread],
    ) -> list[EventTrajectory]:
        """Анализ траекторий для каждой событийной нити.

        Параллельные LLM-вызовы (batch по 5 нитей).

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- аналитик-прогнозист. Для каждого из следующих событий:

        1. Опиши ТЕКУЩЕЕ СОСТОЯНИЕ (где мы сейчас, 2-3 предложения)
        2. Определи МОМЕНТУМ:
           - escalating: ситуация обостряется
           - stable: без значимых изменений
           - de_escalating: ситуация разряжается
           - emerging: только зарождается
           - culminating: приближается к кульминации
           - fading: теряет актуальность
        3. Предложи 3 СЦЕНАРИЯ:
           - baseline (наиболее вероятный)
           - один из: optimistic / pessimistic
           - wildcard (неожиданный поворот)
           Для каждого: описание, вероятность (сумма = 1.0),
           индикаторы, потенциальный заголовок.
        4. Укажи KEY DRIVERS (3-5 факторов) и UNCERTAINTIES (2-3).

        Событие: {thread.title}
        Описание: {thread.summary}
        Категория: {thread.category}
        Ключевые сущности: {thread.entities}

        Верни JSON.
        ```

        Args:
            threads: Top-20 EventThread[].

        Returns:
            EventTrajectory для каждой нити.
        """
        ...

    async def _build_cross_impact_matrix(
        self,
        threads: list[EventThread],
    ) -> CrossImpactMatrix:
        """Построение матрицы перекрёстных влияний.

        LLM оценивает, как развитие каждого события влияет на другие.
        Для 20 событий: до 380 пар, но анализируются только
        потенциально связанные (pre-filter по категориям и сущностям).

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ниже -- список из {n} событий. Для каждой пары, где есть
        значимое взаимное влияние, укажи:
        - source: номер события-причины
        - target: номер события-следствия
        - impact: от -1.0 (ослабляет) до +1.0 (усиливает)
        - explanation: механизм влияния (1 предложение)

        Указывай ТОЛЬКО пары с |impact| >= 0.2.

        События:
        1. {thread_1.title}: {thread_1.summary}
        2. {thread_2.title}: {thread_2.summary}
        ...

        Верни JSON array: [{"source": 1, "target": 3,
        "impact": 0.6, "explanation": "..."}]
        ```

        Args:
            threads: Top-20 EventThread[].

        Returns:
            CrossImpactMatrix с ненулевыми связями.
        """
        ...
```

### LLM-вызовы

| Вызов | Модель | Input ~tokens | Output ~tokens | Назначение |
|---|---|---|---|---|
| `_embed_texts` | text-embedding-3-small | 100-200 текстов | 1536-dim vectors | Эмбеддинг для кластеризации |
| `_label_and_score_clusters` (batch) | openai/gpt-4o-mini | 500-1000 per batch | 200-400 per batch | Лейблинг, категории, importance |
| `_analyze_trajectories` (batch) | anthropic/claude-sonnet-4 | 1000-2000 per thread | 500-800 per thread | Сценарии и траектории |
| `_build_cross_impact_matrix` | anthropic/claude-sonnet-4 | 2000-4000 | 1000-2000 | Матрица влияний |

### Зависимости

- `hdbscan` -- pip package для кластеризации
- `numpy` -- массивы эмбеддингов, расчёты
- `src/llm/providers.py` -- эмбеддинг-API и chat-API

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| Embedding API недоступен | Fallback: TF-IDF + KMeans (sklearn, без LLM) |
| HDBSCAN находит < 5 кластеров | Уменьшить min_cluster_size до 2, retry |
| HDBSCAN помечает > 50% как шум | Уменьшить min_samples до 1, retry |
| LLM-лейблинг провалился для кластера | Использовать заголовок наиболее свежего сигнала |
| < 10 сигналов на входе | Пропустить кластеризацию, каждый сигнал = отдельная нить |

---

## 3. GeopoliticalAnalyst (`src/agents/analysts/geopolitical.py`)

Агент геополитического анализа событийных нитей. Фокус: расстановка сил, интересы акторов, эскалация, санкции, военные последствия.

### Сигнатуры

```python
"""src/agents/analysts/geopolitical.py"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import (
    EventThread,
    GeopoliticalAssessment,
    StrategicActor,
)

if TYPE_CHECKING:
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class GeopoliticalAnalyst(BaseAgent):
    """Агент геополитического анализа событийных нитей.

    Запускается на Stage 3 (Trajectory Analysis) параллельно
    с EconomicAnalyst и MediaAnalyst.

    Для каждого EventThread создаёт GeopoliticalAssessment:
    стратегические акторы, расстановка сил, вероятность эскалации,
    эффекты второго порядка.

    LLM-модель: anthropic/claude-sonnet-4 (глубокий анализ).
    Стоимость: ~$1.00-2.00 за прогноз.
    """

    name = "geopolitical_analyst"

    def get_timeout_seconds(self) -> int:
        return 600  # 10 минут (до 20 LLM-вызовов)

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Геополитический анализ всех событийных нитей.

        Returns:
            {"assessments": List[dict]} -- каждый dict содержит
            GeopoliticalAssessment + thread_id.
        """
        threads = context.event_threads
        trajectories = context.trajectories

        # Параллельный анализ (batch по 5)
        assessments = await self._analyze_batch(threads, trajectories)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        trajectories: list[EventTrajectory],
    ) -> list[GeopoliticalAssessment]:
        """Пакетный анализ нитей.

        Batch по 5 -- чтобы не перегружать LLM API и уложиться
        в rate limits.

        Args:
            threads: Событийные нити.
            trajectories: Траектории (для контекста).

        Returns:
            GeopoliticalAssessment для каждой нити.
        """
        ...

    async def _analyze_thread(
        self,
        thread: EventThread,
        trajectory: EventTrajectory | None,
    ) -> GeopoliticalAssessment:
        """Геополитический анализ одной событийной нити.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- геополитический стратег с 20-летним опытом.
        Проанализируй следующее событие с точки зрения международных
        отношений и геополитики.

        Событие: {thread.title}
        Описание: {thread.summary}
        Категория: {thread.category}
        Ключевые сущности: {thread.entities}
        Текущий моментум: {trajectory.momentum if trajectory else "unknown"}

        Определи:

        1. СТРАТЕГИЧЕСКИЕ АКТОРЫ (2-5):
           Для каждого: имя, роль (initiator/target/mediator/ally/
           observer/spoiler), ключевые интересы, вероятные действия,
           рычаги влияния.

        2. РАССТАНОВКА СИЛ:
           Кто усиливается, кто ослабевает? 2-3 предложения.

        3. АЛЬЯНСНЫЕ СДВИГИ:
           Меняются ли альянсы? Какие?

        4. ВЕРОЯТНОСТЬ ЭСКАЛАЦИИ (0.0-1.0):
           Для военных/санкционных/дипломатических конфликтов.

        5. ЭФФЕКТЫ ВТОРОГО ПОРЯДКА (3-5):
           Что произойдёт как следствие? (не прямое последствие,
           а каскадные эффекты)

        6. САНКЦИОННЫЙ РИСК: none/low/medium/high/imminent

        7. ВОЕННЫЕ ПОСЛЕДСТВИЯ: (если применимо)

        8. УГЛЫ ДЛЯ ЗАГОЛОВКОВ (2-3):
           Как можно подать это событие через геополитическую призму.

        Верни JSON.
        ```

        Args:
            thread: Событийная нить.
            trajectory: Траектория (опционально).

        Returns:
            GeopoliticalAssessment.
        """
        ...
```

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| LLM API timeout для одного thread | Retry 1 раз; если повторно -- skip этот thread |
| Невалидный JSON от LLM | Retry с уточнённым промптом |
| Thread не имеет геополитического значения | Вернуть minimal assessment (escalation_probability=0, пустые actors) |

---

## 4. EconomicAnalyst (`src/agents/analysts/economic.py`)

Агент экономического анализа событийных нитей. Фокус: индикаторы, рынки, торговля, ЦБ, товарные цены.

### Сигнатуры

```python
"""src/agents/analysts/economic.py"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import (
    EventThread,
    EconomicAssessment,
    EconomicIndicator,
)

if TYPE_CHECKING:
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class EconomicAnalyst(BaseAgent):
    """Агент экономического анализа событийных нитей.

    Запускается на Stage 3 параллельно с GeopoliticalAnalyst
    и MediaAnalyst.

    Для каждого EventThread создаёт EconomicAssessment:
    затронутые индикаторы, рыночное влияние, секторы, торговые
    потоки, ЦБ-сигналы.

    LLM-модель: anthropic/claude-sonnet-4.
    Стоимость: ~$1.00-2.00 за прогноз.
    """

    name = "economic_analyst"

    def get_timeout_seconds(self) -> int:
        return 600

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Экономический анализ всех событийных нитей.

        Returns:
            {"assessments": List[dict]}
        """
        threads = context.event_threads
        trajectories = context.trajectories

        assessments = await self._analyze_batch(threads, trajectories)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        trajectories: list[EventTrajectory],
    ) -> list[EconomicAssessment]:
        """Пакетный экономический анализ."""
        ...

    async def _analyze_thread(
        self,
        thread: EventThread,
        trajectory: EventTrajectory | None,
    ) -> EconomicAssessment:
        """Экономический анализ одной нити.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- макроэкономический аналитик с опытом в финансовых
        рынках и международной торговле.

        Проанализируй экономические последствия следующего события.

        Событие: {thread.title}
        Описание: {thread.summary}
        Категория: {thread.category}

        Определи:

        1. ЗАТРОНУТЫЕ ИНДИКАТОРЫ (2-5):
           Для каждого: название, направление (up/down/neutral/volatile),
           масштаб (low/medium/high), уверенность (0-1),
           горизонт (immediate/days/weeks/months).
           Примеры индикаторов: GDP, CPI, S&P 500, USD/RUB, Oil Brent,
           VIX, Treasury Yields, PMI.

        2. РЫНОЧНОЕ ВЛИЯНИЕ:
           strongly_negative / negative / neutral / positive / strongly_positive
           + затронутые сектора экономики

        3. ЦЕПОЧКИ ПОСТАВОК:
           Есть ли влияние на supply chains? 1-2 предложения.

        4. ФИСКАЛЬНЫЙ КАЛЕНДАРЬ:
           Связанные события: заседания ЦБ, публикации данных,
           отчётности компаний, аукционы облигаций.

        5. СИГНАЛЫ ЦЕНТРОБАНКОВ:
           Релевантные заявления/действия ФРС, ЕЦБ, ЦБ РФ, и др.

        6. ТОРГОВЫЕ ПОТОКИ:
           Тарифы, санкции, квоты, эмбарго -- что меняется?

        7. ТОВАРНЫЕ РЫНКИ:
           Конкретные прогнозы по commodities:
           'нефть Brent +2-3%', 'золото стабильно'.

        8. ЗАНЯТОСТЬ (если значимо):
           Влияние на рынок труда.

        9. УГЛЫ ДЛЯ ЗАГОЛОВКОВ (2-3):
           Экономические фреймы подачи.

        Верни JSON.
        ```

        Args:
            thread: Событийная нить.
            trajectory: Траектория (опционально).

        Returns:
            EconomicAssessment.
        """
        ...
```

### Обработка ошибок

Идентична GeopoliticalAnalyst. Дополнительно:

| Ситуация | Стратегия |
|---|---|
| Thread не имеет экономического значения | Вернуть minimal assessment (market_impact="neutral", пустые indicators) |
| Индикаторы без числовых данных | Указать direction="neutral", magnitude="low", confidence=0.3 |

---

## 5. MediaAnalyst (`src/agents/analysts/media.py`)

Агент медийного анализа. Ключевое отличие от других аналитиков: этот агент прогнозирует не "что произойдёт", а "что ЭТИМ ИЗДАНИЕМ будет освещено".

### Сигнатуры

```python
"""src/agents/analysts/media.py"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import (
    EventThread,
    MediaAssessment,
    NewsworthinessScore,
    OutletProfile,
)

if TYPE_CHECKING:
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class MediaAnalyst(BaseAgent):
    """Агент медийного анализа событийных нитей.

    Запускается на Stage 3 параллельно с GeopoliticalAnalyst
    и EconomicAnalyst.

    Ключевая особенность: этот агент НЕ прогнозирует события.
    Он прогнозирует ПОКРЫТИЕ: будет ли данное издание писать
    об этом? Как подаст? Какое место в иерархии?

    Требует OutletProfile из Stage 1 (OutletHistorian).

    LLM-модель: anthropic/claude-sonnet-4.
    Стоимость: ~$0.50-1.00 за прогноз.
    """

    name = "media_analyst"

    def get_timeout_seconds(self) -> int:
        return 300

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        if context.outlet_profile is None:
            return "OutletProfile required for media analysis"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Медийный анализ нитей относительно целевого издания.

        Returns:
            {"assessments": List[dict]}
        """
        threads = context.event_threads
        profile = context.outlet_profile

        assessments = await self._analyze_batch(threads, profile)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        profile: OutletProfile,
    ) -> list[MediaAssessment]:
        """Пакетный медийный анализ.

        Все нити анализируются в одном LLM-вызове (или 2 batch,
        если > 10 нитей) -- для контекста конкуренции между
        историями.

        Args:
            threads: Событийные нити (top-20).
            profile: Профиль целевого издания.

        Returns:
            MediaAssessment для каждой нити.
        """
        ...

    async def _analyze_threads(
        self,
        threads: list[EventThread],
        profile: OutletProfile,
    ) -> list[MediaAssessment]:
        """Анализ группы нитей в одном LLM-вызове.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- главный редактор издания "{profile.outlet_name}".

        Профиль издания:
        - Тональность: {profile.editorial_position.tone}
        - Фокус: {profile.editorial_position.focus_topics}
        - Избегаемые темы: {profile.editorial_position.avoided_topics}
        - Фрейминг: {profile.editorial_position.framing_tendencies}
        - Стиль заголовков: {profile.headline_style} (кратко)
        - Примеры заголовков: {profile.sample_headlines[:5]}

        Вот {n} событий, которые могут стать новостями.
        Для каждого определи, КАК ТВОЁ ИЗДАНИЕ их подаст:

        Для каждого события:

        1. НОВОСТНАЯ ЦЕННОСТЬ (6 баллов 0.0-1.0):
           - timeliness: привязка к моменту
           - impact: масштаб влияния
           - prominence: известность участников
           - proximity: близость к аудитории издания
           - conflict: конфликтность
           - novelty: необычность

        2. РЕДАКЦИОННЫЙ FIT (0.0-1.0):
           Насколько событие соответствует редакционной политике?
           + объяснение (1 предложение)

        3. ПОЗИЦИЯ В НОВОСТНОМ ЦИКЛЕ:
           breaking / developing / emerging / peak / declining / follow_up

        4. МЕДИЙНАЯ НАСЫЩЕННОСТЬ (0.0-1.0):
           Насколько тема уже "заезжена" в медиапространстве?

        5. ВЕРОЯТНОСТЬ ПОКРЫТИЯ (0.0-1.0):
           Вероятность, что ИМЕННО ЭТО ИЗДАНИЕ опубликует материал.

        6. ПРЕДПОЛАГАЕМАЯ ЗАМЕТНОСТЬ:
           top_headline / major / secondary / brief / ignore

        7. ВЕРОЯТНЫЙ ФРЕЙМ:
           Как издание подаст -- через какую призму.

        8. КОНКУРИРУЮЩИЕ ИСТОРИИ:
           Какие другие истории (из этого же списка) будут отвлекать
           внимание.

        9. УГЛЫ ЗАГОЛОВКОВ (2-4):
           Конкретные формулировки заголовков, характерные для
           ЭТОГО издания.

        События:
        {formatted_threads}

        Верни JSON array.
        ```

        Args:
            threads: Нити для анализа.
            profile: Профиль издания.

        Returns:
            MediaAssessment[].
        """
        ...
```

### Особенности MediaAnalyst

1. **Зависимость от OutletProfile**: Это единственный аналитик Stage 3, который требует данные не только от Stage 2, но и от Stage 1 (OutletProfile от OutletHistorian). Если OutletHistorian провалился -- MediaAnalyst получит `validate_context` ошибку и не запустится.

2. **Контекст конкуренции**: Все нити анализируются вместе в одном вызове (или 2 batch), потому что истории конкурируют за внимание. Если FOMC заседание и землетрясение в один день -- нужно понять, что будет top_headline.

3. **Saturation**: Высокий saturation (> 0.7) указывает, что тема уже перенасыщена и издание может предпочесть fresh angle или другую тему. Формула headline_score (Stage 6, Judge) использует `(1 - saturation)` как множитель.

### LLM-вызовы

| Вызов | Модель | Input ~tokens | Output ~tokens | Назначение |
|---|---|---|---|---|
| `_analyze_threads` (batch) | anthropic/claude-sonnet-4 | 3000-6000 | 2000-4000 | Новостная ценность, fit, покрытие |

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| OutletProfile отсутствует | validate_context вернёт ошибку; агент не запускается |
| LLM API timeout | Retry 1 раз; если повторно -- fallback: все нити получают default scores |
| Невалидный JSON | Retry с "Return ONLY valid JSON" |
| Нит с coverage_probability=0 | Нормально -- "издание не будет писать об этом"; нить не попадёт в финальный прогноз |

---

## 6. Диаграмма стадий 2-3

```
        Stage 1 Output
        ┌────────────────────────────────────────────┐
        │ signals: List[SignalRecord]  (100-200)     │
        │ scheduled_events: List[ScheduledEvent]     │
        │ outlet_profile: OutletProfile              │
        └────────────┬───────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │   Stage 2: EventTrend      │
        │   Analyzer                 │
        │                            │
        │   embed → HDBSCAN → LLM   │
        │   label → score → rank     │
        │                            │
        │   + trajectories           │
        │   + cross-impact matrix    │
        └────────────┬───────────────┘
                     │
                     ▼
        event_threads: List[EventThread]  (top-20)
        trajectories: List[EventTrajectory]
        cross_impact_matrix: CrossImpactMatrix
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
  ┌───────────┐ ┌──────────┐ ┌───────────┐
  │Geopolitical│ │Economic  │ │Media      │
  │Analyst    │ │Analyst   │ │Analyst    │
  │           │ │          │ │           │
  │threads +  │ │threads + │ │threads +  │
  │trajectories│ │trajectories│ │outlet_  │
  │           │ │          │ │profile    │
  └─────┬─────┘ └────┬─────┘ └─────┬─────┘
        │            │             │
        ▼            ▼             ▼
  Geopolitical  Economic     Media
  Assessment[]  Assessment[] Assessment[]
        │            │             │
        └────────────┼─────────────┘
                     │
                     ▼
        event_threads[i].assessments = {
            "geopolitical_analyst": GeopoliticalAssessment,
            "economic_analyst": EconomicAssessment,
            "media_analyst": MediaAssessment,
        }
                     │
                     ▼
              Stage 4: Delphi R1
```

---

## 7. Порядок реализации аналитиков

1. **Схемы** (`src/schemas/events.py`): EventThread, EventTrajectory, CrossImpactMatrix, *Assessment, NewsworthinessScore
2. **EventTrendAnalyzer** -- самый сложный (кластеризация + batch LLM + scoring). Начинать с mock-эмбеддингов и KMeans, затем заменить на HDBSCAN
3. **GeopoliticalAnalyst** -- чистый LLM-вызов, простая реализация
4. **EconomicAnalyst** -- аналогичен GeopoliticalAnalyst
5. **MediaAnalyst** -- последним, зависит от OutletProfile

Тестирование:
- Unit: scoring формула (_calculate_significance_score, _calculate_recency_score)
- Integration с mock LLM: кластеризация с фиктивными эмбеддингами
- E2E (`@pytest.mark.integration`): полный прогон с реальными API

---

## 8. Общая стратегия обработки ошибок аналитиков

Принцип: **деградация качества лучше полного провала**.

1. **EventTrendAnalyzer (Stage 2)** -- критический. Если упал -- пайплайн останавливается (нет event_threads для Delphi).
2. **Аналитики Stage 3** -- 2 из 3 достаточно (`min_successful=2`). Наименее критичен MediaAnalyst -- без него Delphi работает, просто не учитывается медийный fit.
3. **Внутри агента**: каждый thread анализируется независимо. Если LLM-вызов для одного thread упал -- остальные продолжают. Minimal assessment для проблемного thread.
4. **Batch retry**: если batch из 5 threads полностью провалился -- retry с меньшим batch (по 1). Если и это не помогло -- skip этих threads.
