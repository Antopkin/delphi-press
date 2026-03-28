"""Схемы данных коллекторов и аналитиков.

Стадии пайплайна: 1 (Collection → SignalRecord, ScheduledEvent, OutletProfile),
                  2 (Event Identification → EventThread),
                  3 (Trajectory → EventTrajectory, CrossImpactMatrix, *Assessment).
Спеки: docs/03-collectors.md (§1), docs/04-analysts.md (§1).
Контракт: SignalRecord[] + ScheduledEvent[] + OutletProfile → EventThread[] →
          EventTrajectory[] + CrossImpactMatrix + *Assessment[].
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# =====================================================================
# Part 1: Collector schemas (Stage 1)
# =====================================================================


class SignalSource(StrEnum):
    """Источник сигнала."""

    RSS = "rss"
    WEB_SEARCH = "web_search"
    SOCIAL = "social"
    WIRE = "wire"


class SignalRecord(BaseModel):
    """Один новостной сигнал (новость, пост, заголовок).

    Атомарная единица информации, собранная NewsScout.
    Из 100-200 таких сигналов EventTrendAnalyzer формирует EventThread[].
    """

    id: str = Field(
        ...,
        description="Уникальный идентификатор сигнала. Формат: 'rss_{hash}' или 'ws_{hash}'.",
    )
    title: str = Field(..., description="Заголовок новости / поста. Оригинальный язык.")
    summary: str = Field(
        default="",
        description="Краткое содержание (первые 2-3 предложения).",
    )
    url: str = Field(..., description="URL источника.")
    source_name: str = Field(
        ..., description="Название источника. Примеры: 'Reuters', 'ТАСС', 'BBC News'."
    )
    source_type: SignalSource = Field(
        ..., description="Тип источника (RSS, Web Search, Social, Wire)."
    )
    published_at: datetime | None = Field(default=None, description="Дата/время публикации.")
    language: str = Field(
        default="", description="Язык контента (ISO 639-1: 'ru', 'en', 'zh', etc.)."
    )
    categories: list[str] = Field(
        default_factory=list,
        description="Категории/теги. Примеры: ['politics', 'economy', 'military'].",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Именованные сущности. Примеры: ['Trump', 'ЕЦБ', 'НАТО'].",
    )
    relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Предварительная оценка релевантности (0-1)."
    )


# =====================================================================
# ScheduledEvent — единица данных от EventCalendar
# =====================================================================


class EventType(StrEnum):
    """Тип запланированного события."""

    POLITICAL = "political"
    ECONOMIC = "economic"
    DIPLOMATIC = "diplomatic"
    JUDICIAL = "judicial"
    MILITARY = "military"
    CULTURAL = "cultural"
    SCIENTIFIC = "scientific"
    SPORTS = "sports"
    OTHER = "other"


class EventCertainty(StrEnum):
    """Степень уверенности, что событие действительно состоится."""

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    SPECULATIVE = "speculative"


class ScheduledEvent(BaseModel):
    """Запланированное событие на target_date.

    Собирается EventCalendar через поиск + LLM-структурирование.
    """

    id: str = Field(..., description="Уникальный идентификатор. Формат: 'evt_{hash}'.")
    title: str = Field(..., description="Название события.")
    description: str = Field(default="", description="Подробное описание события.")
    event_date: date = Field(..., description="Дата события.")
    event_type: EventType = Field(..., description="Тип события.")
    certainty: EventCertainty = Field(
        default=EventCertainty.LIKELY, description="Степень уверенности в проведении события."
    )
    location: str = Field(default="", description="Место проведения.")
    participants: list[str] = Field(default_factory=list, description="Ключевые участники.")
    potential_impact: str = Field(
        default="", description="Потенциальное влияние на новостную повестку."
    )
    source_url: str = Field(default="", description="URL источника информации о событии.")
    newsworthiness: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Оценка новостной значимости (0-1)."
    )


# =====================================================================
# OutletProfile — результат OutletHistorian
# =====================================================================


class ToneProfile(StrEnum):
    """Тональность издания."""

    NEUTRAL = "neutral"
    CONSERVATIVE = "conservative"
    LIBERAL = "liberal"
    SENSATIONALIST = "sensationalist"
    ANALYTICAL = "analytical"
    OFFICIAL = "official"
    OPPOSITIONAL = "oppositional"


class HeadlineStyle(BaseModel):
    """Стилевые характеристики заголовков издания."""

    avg_length_chars: int = Field(default=60, description="Средняя длина заголовка в символах.")
    avg_length_words: int = Field(default=8, description="Средняя длина заголовка в словах.")
    uses_colons: bool = Field(default=False, description="Используют ли заголовки двоеточие.")
    uses_quotes: bool = Field(default=False, description="Часто ли используются цитаты.")
    uses_questions: bool = Field(
        default=False, description="Используются ли вопросительные заголовки."
    )
    uses_numbers: bool = Field(default=False, description="Частое использование цифр.")
    capitalization: str = Field(
        default="sentence_case",
        description="Стиль капитализации (sentence_case, title_case и др.).",
    )
    vocabulary_register: str = Field(
        default="neutral",
        description="Регистр лексики: 'formal', 'neutral', 'colloquial', 'technical', 'mixed'.",
    )
    emotional_tone: str = Field(
        default="neutral",
        description="Эмоциональная тональность (neutral, alarming, optimistic и др.).",
    )
    common_patterns: list[str] = Field(
        default_factory=list, description="Часто повторяющиеся паттерны."
    )


class WritingStyle(BaseModel):
    """Стилевые характеристики текстов издания."""

    first_paragraph_style: str = Field(
        default="inverted_pyramid",
        description="Стиль первого абзаца (inverted_pyramid, narrative и др.).",
    )
    avg_first_paragraph_sentences: int = Field(
        default=2, description="Среднее количество предложений в первом абзаце."
    )
    avg_first_paragraph_words: int = Field(
        default=40, description="Среднее количество слов в первом абзаце."
    )
    attribution_style: str = Field(
        default="source_first",
        description="Стиль атрибуции: 'source_first', 'source_last', 'inline'.",
    )
    uses_dateline: bool = Field(default=False, description="Есть ли датлайн.")
    paragraph_length: str = Field(
        default="short", description="Типичная длина абзаца: 'short', 'medium', 'long'."
    )


class EditorialPosition(BaseModel):
    """Редакционная позиция и предпочтения издания."""

    tone: ToneProfile = Field(
        default=ToneProfile.NEUTRAL, description="Общая тональность издания."
    )
    focus_topics: list[str] = Field(
        default_factory=list, description="Темы, на которых фокусируется."
    )
    avoided_topics: list[str] = Field(
        default_factory=list, description="Темы, которые обходит стороной."
    )
    framing_tendencies: list[str] = Field(
        default_factory=list, description="Типичные фреймы подачи."
    )
    source_preferences: list[str] = Field(
        default_factory=list, description="Предпочтительные источники/эксперты."
    )
    stance_on_current_topics: dict[str, str] = Field(
        default_factory=dict, description="Позиция по текущим ключевым темам. {'тема': 'позиция'}."
    )
    omissions: list[str] = Field(
        default_factory=list, description="Что издание систематически пропускает."
    )


class OutletProfile(BaseModel):
    """Полный стилевой и редакционный профиль СМИ.

    Формируется OutletHistorian на основе анализа последних 30 дней публикаций.
    Используется на стадиях Framing (Stage 7) и Generation (Stage 8).
    """

    outlet_name: str = Field(..., description="Каноническое название издания.")
    outlet_url: str = Field(default="", description="Основной URL издания.")
    language: str = Field(default="ru", description="Основной язык издания (ISO 639-1).")
    headline_style: HeadlineStyle = Field(..., description="Характеристики стиля заголовков.")
    writing_style: WritingStyle = Field(..., description="Характеристики стиля текстов.")
    editorial_position: EditorialPosition = Field(
        ..., description="Редакционная позиция и предпочтения."
    )
    sample_headlines: list[str] = Field(
        default_factory=list,
        description="10-30 последних заголовков для few-shot примеров.",
        min_length=0,
        max_length=50,
    )
    sample_first_paragraphs: list[str] = Field(
        default_factory=list, description="5-10 примеров первых абзацев."
    )
    analysis_period_days: int = Field(default=30, description="Период анализа в днях.")
    articles_analyzed: int = Field(default=0, description="Количество проанализированных статей.")
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp проведения анализа."
    )


# =====================================================================
# Part 2: Analyst schemas (Stages 2-3)
# =====================================================================


class EventThread(BaseModel):
    """Событийная нить — кластер связанных сигналов, объединённых общей темой.

    Создаётся EventTrendAnalyzer из 100-200 SignalRecord.
    Одна нить = одна тема/событие, которое может стать заголовком.
    """

    id: str = Field(..., description="Уникальный идентификатор нити. Формат: 'thread_{hash}'.")
    title: str = Field(..., description="Краткое название нити (1 предложение).")
    summary: str = Field(..., description="Развёрнутое описание нити. 2-4 предложения.")
    signal_ids: list[str] = Field(default_factory=list, description="ID сигналов в кластере.")
    scheduled_event_ids: list[str] = Field(
        default_factory=list, description="ID запланированных событий, связанных с нитью."
    )
    cluster_size: int = Field(default=0, description="Общее количество сигналов в кластере.")
    category: str = Field(
        default="", description="Основная категория: 'politics', 'economy', etc."
    )
    entities: list[str] = Field(
        default_factory=list, description="Ключевые сущности нити (люди, организации, страны)."
    )
    source_diversity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Разнообразие источников (0-1)."
    )
    earliest_signal: datetime | None = Field(
        default=None, description="Timestamp самого раннего сигнала."
    )
    latest_signal: datetime | None = Field(
        default=None, description="Timestamp самого свежего сигнала."
    )
    recency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Свежесть нити (0-1).")
    significance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Итоговый балл значимости (0-1)."
    )
    importance: float = Field(default=0.0, ge=0.0, le=1.0, description="Важность темы (0-1).")
    entity_prominence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Значимость упомянутых сущностей (0-1)."
    )
    assessments: dict[str, object] = Field(
        default_factory=dict,
        description="Оценки от аналитиков Stage 3 (по ключам аналитиков).",
    )


# =====================================================================
# EventTrajectory — анализ траектории события
# =====================================================================


class ScenarioType(StrEnum):
    """Тип сценария развития / оценки."""

    BASELINE = "baseline"
    OPTIMISTIC = "optimistic"
    PESSIMISTIC = "pessimistic"
    BLACK_SWAN = "black_swan"
    WILDCARD = "wildcard"


class Scenario(BaseModel):
    """Один сценарий развития события."""

    scenario_type: ScenarioType = Field(..., description="Тип сценария.")
    description: str = Field(..., description="Описание сценария. 2-3 предложения.")
    probability: float = Field(
        ..., ge=0.0, le=1.0, description="Вероятность сценария (0-1). Сумма = 1.0."
    )
    key_indicators: list[str] = Field(
        default_factory=list, description="Индикаторы реализации сценария. 2-3 штуки."
    )
    headline_potential: str = Field(
        default="", description="Какой заголовок может породить этот сценарий."
    )


class EventTrajectory(BaseModel):
    """Траектория развития событийной нити.

    Для каждого EventThread генерируется одна EventTrajectory,
    описывающая текущее состояние, динамику и 3 сценария.
    """

    thread_id: str = Field(..., description="ID связанного EventThread.")
    current_state: str = Field(..., description="Описание текущего состояния события.")
    momentum: str = Field(
        ...,
        description="Динамика (escalating, stable, de_escalating и др.).",
    )
    momentum_explanation: str = Field(default="", description="Почему такой моментум.")
    scenarios: list[Scenario] = Field(
        ...,
        description="3 сценария развития. Сумма вероятностей = 1.0.",
        min_length=2,
        max_length=4,
    )
    key_drivers: list[str] = Field(
        default_factory=list, description="Ключевые факторы, определяющие развитие."
    )
    uncertainties: list[str] = Field(
        default_factory=list, description="Основные неопределённости."
    )


# =====================================================================
# CrossImpactMatrix — перекрёстные влияния между событиями
# =====================================================================


class CrossImpactEntry(BaseModel):
    """Одна ячейка матрицы перекрёстных влияний."""

    source_thread_id: str = Field(..., description="ID события-причины.")
    target_thread_id: str = Field(..., description="ID события-следствия.")
    impact_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Сила влияния (-1 до +1). Положительные: усиливает. Отрицательные: ослабляет.",
    )
    explanation: str = Field(default="", description="Краткое объяснение механизма влияния.")


class CrossImpactMatrix(BaseModel):
    """Матрица перекрёстных влияний между событийными нитями.

    Описывает, как развитие одного события влияет на другие.
    Используется в Delphi для согласования прогнозов.
    """

    entries: list[CrossImpactEntry] = Field(
        default_factory=list, description="Ненулевые ячейки матрицы (sparse representation)."
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_impact(self, source_id: str, target_id: str) -> float:
        """Получить силу влияния source -> target. 0.0 если связь не найдена."""
        for entry in self.entries:
            if entry.source_thread_id == source_id and entry.target_thread_id == target_id:
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


class StrategicActor(BaseModel):
    """Геополитический актор и его позиция."""

    name: str = Field(..., description="Имя актора (страна, лидер, организация).")
    role: str = Field(
        default="",
        description="Роль в событии: initiator / target / mediator / ally / observer / spoiler.",
    )
    interests: list[str] = Field(default_factory=list, description="Ключевые интересы актора.")
    likely_actions: list[str] = Field(
        default_factory=list, description="Вероятные действия в ближайшие дни."
    )
    leverage: str = Field(
        default="",
        description="Рычаги влияния: экономические, военные, дипломатические, информационные.",
    )


class GeopoliticalAssessment(BaseModel):
    """Геополитическая оценка событийной нити.

    Создаётся GeopoliticalAnalyst для каждого EventThread.
    """

    thread_id: str = Field(..., description="ID оцениваемого EventThread.")
    strategic_actors: list[StrategicActor] = Field(
        default_factory=list, description="Ключевые геополитические акторы. 2-5 акторов."
    )
    power_dynamics: str = Field(default="", description="Описание расстановки сил.")
    alliance_shifts: list[str] = Field(
        default_factory=list, description="Возможные сдвиги в альянсах."
    )
    escalation_probability: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Вероятность эскалации (0-1)."
    )
    second_order_effects: list[str] = Field(
        default_factory=list, description="Эффекты второго порядка. 3-5 пунктов."
    )
    sanctions_risk: str = Field(
        default="none",
        description="Санкционный риск: 'none', 'low', 'medium', 'high', 'imminent'.",
    )
    military_implications: str = Field(
        default="", description="Военные последствия (если применимо)."
    )
    headline_angles: list[str] = Field(
        default_factory=list, description="Возможные углы подачи для заголовков."
    )


class EconomicIndicator(BaseModel):
    """Экономический индикатор, затронутый событием."""

    name: str = Field(..., description="Название индикатора.")
    direction: str = Field(
        default="neutral",
        description="Ожидаемое направление: 'up', 'down', 'neutral', 'volatile'.",
    )
    magnitude: str = Field(
        default="low", description="Масштаб изменения: 'low', 'medium', 'high'."
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Уверенность в прогнозе направления (0-1)."
    )
    timeframe: str = Field(
        default="days", description="Временной горизонт: 'immediate', 'days', 'weeks', 'months'."
    )


class EconomicAssessment(BaseModel):
    """Экономическая оценка событийной нити.

    Создаётся EconomicAnalyst для каждого EventThread.
    """

    thread_id: str = Field(..., description="ID оцениваемого EventThread.")
    affected_indicators: list[EconomicIndicator] = Field(
        default_factory=list, description="Затронутые экономические индикаторы."
    )
    market_impact: str = Field(
        default="neutral",
        description="Ожидаемое влияние на рынки: 'strongly_negative' .. 'strongly_positive'.",
    )
    affected_sectors: list[str] = Field(
        default_factory=list, description="Затронутые сектора экономики."
    )
    supply_chain_impact: str = Field(default="", description="Влияние на цепочки поставок.")
    fiscal_calendar_events: list[str] = Field(
        default_factory=list, description="Связанные события фискального календаря."
    )
    central_bank_signals: list[str] = Field(
        default_factory=list, description="Релевантные сигналы от центробанков."
    )
    trade_flow_impact: str = Field(default="", description="Влияние на торговые потоки.")
    commodity_prices: list[str] = Field(
        default_factory=list, description="Затронутые товарные рынки."
    )
    employment_impact: str = Field(default="", description="Влияние на рынок труда.")
    headline_angles: list[str] = Field(
        default_factory=list, description="Возможные экономические углы для заголовков."
    )


class NewsworthinessScore(BaseModel):
    """Оценка новостной ценности по 6 измерениям.

    Основана на модифицированной модели Galtung & Ruge.
    """

    timeliness: float = Field(default=0.0, ge=0.0, le=1.0, description="Актуальность (0-1).")
    impact: float = Field(default=0.0, ge=0.0, le=1.0, description="Масштаб влияния (0-1).")
    prominence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Известность участников (0-1)."
    )
    proximity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Близость к аудитории издания (0-1)."
    )
    conflict: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Степень конфликтности (0-1)."
    )
    novelty: float = Field(default=0.0, ge=0.0, le=1.0, description="Необычность (0-1).")

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


class MediaAssessment(BaseModel):
    """Медийная оценка событийной нити относительно целевого СМИ.

    Создаётся MediaAnalyst для каждого EventThread.
    """

    thread_id: str = Field(..., description="ID оцениваемого EventThread.")
    newsworthiness: NewsworthinessScore = Field(
        ..., description="Оценка новостной ценности по 6 измерениям."
    )
    editorial_fit: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Соответствие редакционной политике (0-1)."
    )
    editorial_fit_explanation: str = Field(
        default="", description="Почему событие подходит/не подходит изданию."
    )
    news_cycle_position: str = Field(
        default="emerging",
        description="Позиция в новостном цикле (breaking, developing, emerging и др.).",
    )
    saturation: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Медийная насыщенность (0-1)."
    )
    coverage_probability: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Вероятность публикации (0-1)."
    )
    predicted_prominence: str = Field(
        default="secondary",
        description="Заметность: 'top_headline', 'major', 'secondary', 'brief', 'ignore'.",
    )
    likely_framing: str = Field(default="", description="Предполагаемый фрейм подачи.")
    competing_stories: list[str] = Field(
        default_factory=list, description="Конкурирующие истории в этот день."
    )
    headline_angles: list[str] = Field(
        default_factory=list, description="Возможные углы заголовков для данного издания."
    )
