# 03 — Агенты-коллекторы

> Реализуемые файлы: `src/agents/collectors/news_scout.py`, `src/agents/collectors/event_calendar.py`, `src/agents/collectors/outlet_historian.py`
>
> Зависимости: `src/agents/base.py` (02-agents-core.md), `src/data_sources/*` (01-data-sources.md), `src/schemas/events.py`

---

## Обзор

Коллекторы -- первая стадия пайплайна (Stage 1: Data Collection). Три агента работают **параллельно**, каждый собирает свой тип данных:

| Агент | Что собирает | Источники | Время | LLM |
|---|---|---|---|---|
| **NewsScout** | Новостные сигналы (100-200 шт.) | RSS + Web Search | 2-5 мин | Опционально (классификация) |
| **EventCalendar** | Запланированные события на target_date | Web Search + LLM | 1-3 мин | Обязательно (поиск + структурирование) |
| **OutletHistorian** | Стилевой и редакционный профиль СМИ | Scraper + LLM | 2-5 мин | Обязательно (анализ стиля) |

Все три наследуют `BaseAgent` (см. 02-agents-core.md). Провал 1 из 3 допустим (`min_successful=2`), но:
- Без NewsScout -- мало сигналов для кластеризации (деградация качества)
- Без EventCalendar -- не учтены запланированные события (пропуск очевидного)
- Без OutletHistorian -- нет стилевого профиля (генерация будет generic)

---

## 1. Общие схемы данных (`src/schemas/events.py`)

Схемы, используемые коллекторами как output и последующими стадиями как input.

```python
"""src/schemas/events.py — Часть 1: Базовые схемы коллекторов."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


# =====================================================================
# SignalRecord — единица данных от NewsScout
# =====================================================================

class SignalSource(str, Enum):
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
        description="Уникальный идентификатор сигнала. Формат: "
        "'rss_{hash}' или 'ws_{hash}'. Hash от URL + title.",
    )

    title: str = Field(
        ...,
        description="Заголовок новости / поста. Оригинальный язык.",
        max_length=500,
    )

    summary: str = Field(
        default="",
        description="Краткое содержание (первые 2-3 предложения или "
        "description из RSS). Максимум 1000 символов.",
        max_length=1000,
    )

    url: str = Field(
        ...,
        description="URL источника. Для RSS -- ссылка на статью, "
        "для web search -- URL из результата.",
    )

    source_name: str = Field(
        ...,
        description="Название источника. Примеры: 'Reuters', 'ТАСС', "
        "'BBC News'.",
    )

    source_type: SignalSource = Field(
        ...,
        description="Тип источника (RSS, Web Search, Social, Wire).",
    )

    published_at: datetime | None = Field(
        default=None,
        description="Дата/время публикации (из RSS pubDate или "
        "published_date из поиска). Может быть None.",
    )

    language: str = Field(
        default="",
        description="Язык контента (ISO 639-1: 'ru', 'en', 'zh', etc.). "
        "Определяется из RSS lang или эвристически.",
    )

    categories: list[str] = Field(
        default_factory=list,
        description="Категории/теги из RSS или классификации LLM. "
        "Примеры: ['politics', 'economy', 'military'].",
    )

    entities: list[str] = Field(
        default_factory=list,
        description="Именованные сущности, упомянутые в сигнале. "
        "Извлекаются простым NER или из заголовка. "
        "Примеры: ['Trump', 'ЕЦБ', 'НАТО'].",
    )

    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Предварительная оценка релевантности (0-1). "
        "Для RSS: на основе свежести и источника. "
        "Для web search: на основе score из API.",
    )


# =====================================================================
# ScheduledEvent — единица данных от EventCalendar
# =====================================================================

class EventType(str, Enum):
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


class EventCertainty(str, Enum):
    """Степень уверенности, что событие действительно состоится."""
    CONFIRMED = "confirmed"       # Официально подтверждено
    LIKELY = "likely"             # Высокая вероятность (по расписанию)
    POSSIBLE = "possible"         # Возможно (слухи, предварительно)
    SPECULATIVE = "speculative"   # Спекулятивно (на основе паттернов)


class ScheduledEvent(BaseModel):
    """Запланированное событие на target_date.

    Собирается EventCalendar через поиск + LLM-структурирование.
    Включает как точно запланированные (саммит G7), так и
    предполагаемые (ежемесячный отчёт).
    """

    id: str = Field(
        ...,
        description="Уникальный идентификатор. Формат: 'evt_{hash}'.",
    )

    title: str = Field(
        ...,
        description="Название события. Примеры: 'Заседание FOMC', "
        "'Саммит НАТО в Брюсселе', 'Суд над X'.",
        max_length=300,
    )

    description: str = Field(
        default="",
        description="Подробное описание события: участники, повестка, "
        "контекст. До 500 символов.",
        max_length=500,
    )

    event_date: date = Field(
        ...,
        description="Дата события (совпадает или близка к target_date).",
    )

    event_type: EventType = Field(
        ...,
        description="Тип события (political, economic, etc.).",
    )

    certainty: EventCertainty = Field(
        default=EventCertainty.LIKELY,
        description="Степень уверенности в проведении события.",
    )

    location: str = Field(
        default="",
        description="Место проведения. Примеры: 'Вашингтон', 'онлайн', "
        "'Москва, Кремль'.",
    )

    participants: list[str] = Field(
        default_factory=list,
        description="Ключевые участники / организации. "
        "Примеры: ['Federal Reserve', 'Jerome Powell'].",
    )

    potential_impact: str = Field(
        default="",
        description="Потенциальное влияние на новостную повестку. "
        "Краткая оценка от LLM.",
        max_length=300,
    )

    source_url: str = Field(
        default="",
        description="URL источника информации о событии.",
    )

    newsworthiness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Оценка новостной значимости (0-1). "
        "1.0 = гарантированно будет в топе новостей.",
    )


# =====================================================================
# OutletProfile — результат OutletHistorian
# =====================================================================

class ToneProfile(str, Enum):
    """Тональность издания."""
    NEUTRAL = "neutral"
    CONSERVATIVE = "conservative"
    LIBERAL = "liberal"
    SENSATIONALIST = "sensationalist"
    ANALYTICAL = "analytical"
    OFFICIAL = "official"
    OPPOSITIONAL = "oppositional"


class OutletProfile(BaseModel):
    """Полный стилевой и редакционный профиль СМИ.

    Формируется OutletHistorian на основе анализа последних 30 дней
    публикаций. Используется на стадиях Framing (Stage 7) и
    Generation (Stage 8) для стилевой адаптации.
    """

    outlet_name: str = Field(
        ...,
        description="Каноническое название издания.",
    )

    outlet_url: str = Field(
        default="",
        description="Основной URL издания.",
    )

    language: str = Field(
        default="ru",
        description="Основной язык издания (ISO 639-1).",
    )

    # --- Стилевой профиль ---

    headline_style: HeadlineStyle = Field(
        ...,
        description="Характеристики стиля заголовков.",
    )

    writing_style: WritingStyle = Field(
        ...,
        description="Характеристики стиля текстов.",
    )

    # --- Редакционный профиль ---

    editorial_position: EditorialPosition = Field(
        ...,
        description="Редакционная позиция и предпочтения.",
    )

    # --- Примеры ---

    sample_headlines: list[str] = Field(
        default_factory=list,
        description="10-30 последних заголовков для few-shot примеров. "
        "Используются в промптах генерации.",
        min_length=0,
        max_length=50,
    )

    sample_first_paragraphs: list[str] = Field(
        default_factory=list,
        description="5-10 примеров первых абзацев для стилевого "
        "копирования.",
    )

    # --- Метаданные ---

    analysis_period_days: int = Field(
        default=30,
        description="Период анализа в днях (сколько дней назад "
        "были проанализированы публикации).",
    )

    articles_analyzed: int = Field(
        default=0,
        description="Количество проанализированных статей.",
    )

    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp проведения анализа.",
    )


class HeadlineStyle(BaseModel):
    """Стилевые характеристики заголовков издания."""

    avg_length_chars: int = Field(
        default=60,
        description="Средняя длина заголовка в символах.",
    )

    avg_length_words: int = Field(
        default=8,
        description="Средняя длина заголовка в словах.",
    )

    uses_colons: bool = Field(
        default=False,
        description="Используют ли заголовки двоеточие для разделения "
        "темы и детали. Пример: 'Саммит НАТО: Зеленский требует гарантий'.",
    )

    uses_quotes: bool = Field(
        default=False,
        description="Часто ли используются цитаты в заголовках. "
        "Пример: 'Путин: «Мы готовы к переговорам»'.",
    )

    uses_questions: bool = Field(
        default=False,
        description="Используются ли вопросительные заголовки.",
    )

    uses_numbers: bool = Field(
        default=False,
        description="Частое использование цифр. "
        "Пример: '5 причин роста доллара'.",
    )

    capitalization: str = Field(
        default="sentence_case",
        description="Стиль капитализации: 'sentence_case', 'title_case', "
        "'all_caps_first_word', 'lowercase'.",
    )

    vocabulary_register: str = Field(
        default="neutral",
        description="Регистр лексики: 'formal', 'neutral', 'colloquial', "
        "'technical', 'mixed'.",
    )

    emotional_tone: str = Field(
        default="neutral",
        description="Эмоциональная тональность: 'neutral', 'alarming', "
        "'optimistic', 'dramatic', 'ironic', 'dry'.",
    )

    common_patterns: list[str] = Field(
        default_factory=list,
        description="Часто повторяющиеся паттерны заголовков. "
        "Примеры: '{Персона} заявил, что...', "
        "'{Событие}: что это значит для...', "
        "'Источники: {утверждение}'.",
    )


class WritingStyle(BaseModel):
    """Стилевые характеристики текстов издания."""

    first_paragraph_style: str = Field(
        default="inverted_pyramid",
        description="Стиль первого абзаца: 'inverted_pyramid' (кто-что-где-когда), "
        "'narrative' (сторителлинг), 'analytical' (тезис + контекст), "
        "'quote_lead' (начинается с цитаты).",
    )

    avg_first_paragraph_sentences: int = Field(
        default=2,
        description="Среднее количество предложений в первом абзаце.",
    )

    avg_first_paragraph_words: int = Field(
        default=40,
        description="Среднее количество слов в первом абзаце.",
    )

    attribution_style: str = Field(
        default="source_first",
        description="Стиль атрибуции: 'source_first' ('По данным Reuters, ...'), "
        "'source_last' ('..., сообщает Reuters'), "
        "'inline' ('Reuters сообщает, что...').",
    )

    uses_dateline: bool = Field(
        default=False,
        description="Есть ли датлайн (МОСКВА, 2 апреля -).",
    )

    paragraph_length: str = Field(
        default="short",
        description="Типичная длина абзаца: 'short' (1-2 предложения), "
        "'medium' (3-4), 'long' (5+).",
    )


class EditorialPosition(BaseModel):
    """Редакционная позиция и предпочтения издания."""

    tone: ToneProfile = Field(
        default=ToneProfile.NEUTRAL,
        description="Общая тональность издания.",
    )

    focus_topics: list[str] = Field(
        default_factory=list,
        description="Темы, на которых издание фокусируется. "
        "Примеры: ['внутренняя политика', 'экономика РФ', "
        "'международные отношения'].",
    )

    avoided_topics: list[str] = Field(
        default_factory=list,
        description="Темы, которые издание обходит стороной или "
        "освещает минимально.",
    )

    framing_tendencies: list[str] = Field(
        default_factory=list,
        description="Типичные фреймы подачи: 'pro_government', "
        "'market_oriented', 'human_interest', 'conflict_frame', "
        "'national_security', etc.",
    )

    source_preferences: list[str] = Field(
        default_factory=list,
        description="Предпочтительные источники/эксперты. "
        "Примеры: ['официальные лица', 'МИД', 'анонимные источники'].",
    )

    stance_on_current_topics: dict[str, str] = Field(
        default_factory=dict,
        description="Позиция по текущим ключевым темам. "
        "Формат: {'тема': 'позиция'}. "
        "Примеры: {'конфликт на Украине': 'провоенная', "
        "'санкции': 'критика Запада'}.",
    )

    omissions: list[str] = Field(
        default_factory=list,
        description="Что издание систематически пропускает или "
        "преуменьшает. Примеры: ['протесты', 'критика власти', "
        "'альтернативные точки зрения'].",
    )
```

---

## 2. NewsScout (`src/agents/collectors/news_scout.py`)

Агент сбора новостных сигналов. Параллельно загружает RSS-фиды и выполняет веб-поиск, формирует унифицированный список `SignalRecord`.

### Логика работы

1. **Определить источники RSS** для текущей задачи: общие мировые (Reuters, AP, BBC) + региональные (зависит от outlet) + тематические
2. **Параллельно загрузить RSS-фиды** (20-30 источников, `asyncio.gather`)
3. **Параллельно выполнить 3-5 веб-поисков** (Exa/Jina API) по запросам, сформулированным на основе target_date и текущих трендов
4. **Дедуплицировать** по URL
5. **Опционально: LLM-классификация** (GPT-4o-mini) -- добавить categories + entities к сигналам без них
6. **Сортировать по relevance_score** (свежесть + источник + score из поиска)

### Сигнатуры

```python
"""src/agents/collectors/news_scout.py"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import SignalRecord, SignalSource

if TYPE_CHECKING:
    from src.data_sources.rss import RSSFetcher, RSSItem
    from src.data_sources.web_search import WebSearchClient, SearchResult
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class NewsScout(BaseAgent):
    """Агент сбора новостных сигналов из RSS и веб-поиска.

    Запускается на Stage 1 (Collection) параллельно с EventCalendar
    и OutletHistorian.

    Результат: 100-200 SignalRecord, отсортированных по relevance_score.

    LLM-модель: openai/gpt-4o-mini (опционально, для классификации).
    Стоимость: ~$0.10-0.30 за прогноз (если классификация включена).
    """

    name = "news_scout"

    def __init__(self, llm_client: LLMClient) -> None:
        super().__init__(llm_client)
        # Инициализация data source клиентов (lazy)
        self._rss: RSSFetcher | None = None
        self._search: WebSearchClient | None = None

    def get_timeout_seconds(self) -> int:
        """RSS + Search = потенциально медленные сети."""
        return 600  # 10 минут

    def validate_context(self, context: PipelineContext) -> str | None:
        """NewsScout не требует предварительных данных."""
        if not context.outlet:
            return "outlet is required"
        if not context.target_date:
            return "target_date is required"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Основная логика сбора сигналов.

        Returns:
            {"signals": List[SignalRecord]} -- 100-200 записей.
        """
        # 1. Определение RSS-источников
        rss_urls = self._get_rss_sources(context.outlet)

        # 2. Формирование поисковых запросов
        search_queries = self._build_search_queries(
            context.outlet, context.target_date,
        )

        # 3. Параллельный сбор
        rss_task = self._fetch_all_rss(rss_urls)
        search_task = self._run_web_searches(search_queries)

        rss_signals, search_signals = await asyncio.gather(
            rss_task, search_task,
            return_exceptions=True,
        )

        # Обработка ошибок -- если одна ветка упала, используем другую
        all_signals: list[SignalRecord] = []

        if isinstance(rss_signals, list):
            all_signals.extend(rss_signals)
        else:
            self.logger.error("RSS fetch failed: %s", rss_signals)

        if isinstance(search_signals, list):
            all_signals.extend(search_signals)
        else:
            self.logger.error("Web search failed: %s", search_signals)

        if not all_signals:
            raise RuntimeError("Both RSS and web search failed")

        # 4. Дедупликация
        signals = self._deduplicate(all_signals)

        # 5. Опциональная LLM-классификация
        signals = await self._classify_signals(signals)

        # 6. Сортировка + ограничение
        signals.sort(key=lambda s: s.relevance_score, reverse=True)
        signals = signals[:200]

        self.logger.info("Collected %d signals (%d RSS, %d search)",
                         len(signals),
                         sum(1 for s in signals
                             if s.source_type == SignalSource.RSS),
                         sum(1 for s in signals
                             if s.source_type == SignalSource.WEB_SEARCH))

        return {"signals": signals}

    def _get_rss_sources(self, outlet: str) -> list[str]:
        """Получить список RSS-URL для заданного outlet.

        Комбинирует:
        - Глобальные источники (Reuters, AP, BBC, Al Jazeera, etc.) -- 10-15
        - Региональные (ТАСС, РИА для русскоязычных; CNN, NYT для англоязычных) -- 5-10
        - Тематические (финансы, политика) -- 5-10

        Args:
            outlet: Название целевого СМИ.

        Returns:
            Список RSS-URL (20-30 штук).
        """
        ...

    def _build_search_queries(
        self,
        outlet: str,
        target_date: date,
    ) -> list[str]:
        """Сформировать 3-5 поисковых запросов.

        Стратегия:
        1. Общий: "major news events {target_date} world"
        2. Региональный: "news {region_of_outlet} {target_date}"
        3. Тематический: "scheduled events politics economy {target_date}"
        4. Outlet-specific: "topics covered by {outlet} this week"
        5. Trending: "breaking news today {current_date}" (для контекста)

        Args:
            outlet: Название СМИ.
            target_date: Целевая дата прогноза.

        Returns:
            3-5 поисковых запросов.
        """
        ...

    async def _fetch_all_rss(
        self,
        rss_urls: list[str],
    ) -> list[SignalRecord]:
        """Параллельная загрузка всех RSS-фидов.

        Использует src/data_sources/rss.py:RSSFetcher.
        Каждый фид загружается независимо; ошибки отдельных фидов
        логируются, но не прерывают сбор.

        Маппинг RSSItem -> SignalRecord:
        - title -> title
        - description -> summary (truncate to 1000 chars)
        - link -> url
        - feed_title -> source_name
        - published -> published_at
        - categories -> categories

        Args:
            rss_urls: Список RSS-URL.

        Returns:
            Список SignalRecord из всех успешно загруженных фидов.
            Типичный размер: 80-150 записей.
        """
        ...

    async def _run_web_searches(
        self,
        queries: list[str],
    ) -> list[SignalRecord]:
        """Выполнение веб-поисков через Exa/Jina API.

        Использует src/data_sources/web_search.py:WebSearchClient.
        Каждый запрос -- отдельный API-вызов. Запросы выполняются
        параллельно.

        Маппинг SearchResult -> SignalRecord:
        - title -> title
        - snippet -> summary
        - url -> url
        - source -> source_name
        - score -> relevance_score (нормализовать 0-1)

        Args:
            queries: Поисковые запросы.

        Returns:
            Список SignalRecord из результатов поиска.
            Типичный размер: 30-60 записей (10-15 на запрос).
        """
        ...

    def _deduplicate(
        self,
        signals: list[SignalRecord],
    ) -> list[SignalRecord]:
        """Дедупликация сигналов по URL.

        При дубле -- оставляем сигнал с более высоким relevance_score.

        Args:
            signals: Список с возможными дублями.

        Returns:
            Дедуплицированный список.
        """
        ...

    async def _classify_signals(
        self,
        signals: list[SignalRecord],
    ) -> list[SignalRecord]:
        """Опциональная LLM-классификация сигналов без категорий.

        Вызывается только для сигналов, у которых categories пуст
        и entities пусты. Пакетная обработка (batch по 20 сигналов).

        LLM-модель: openai/gpt-4o-mini (дешёвая, быстрая).
        Промпт: "Classify each headline into categories and extract
        named entities."

        Формат запроса к LLM:
        ```
        Classify each headline. Return JSON array:
        [{"index": 0, "categories": ["politics"], "entities": ["Trump"]}]

        Headlines:
        0: "Trump announces new tariffs on China"
        1: "ECB holds rates steady"
        ...
        ```

        Args:
            signals: Все собранные сигналы.

        Returns:
            Сигналы с заполненными categories и entities.
        """
        ...

    @staticmethod
    def _make_signal_id(url: str, title: str) -> str:
        """Генерация стабильного ID для сигнала.

        Args:
            url: URL источника.
            title: Заголовок.

        Returns:
            Строка 'sig_{hash8}', например 'sig_a1b2c3d4'.
        """
        raw = f"{url}|{title}".encode("utf-8")
        return f"sig_{hashlib.sha256(raw).hexdigest()[:8]}"
```

### Конфигурация RSS-источников

RSS-фиды определяются в `src/data_sources/outlets_catalog.py`. NewsScout обращается к каталогу через:

```python
from src.data_sources.outlets_catalog import get_rss_feeds_for_context

feeds = get_rss_feeds_for_context(
    outlet="ТАСС",
    categories=["global", "regional_ru", "politics", "economy"],
)
# -> ["https://tass.com/rss/v2.xml", "https://ria.ru/export/rss2/...", ...]
```

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| RSS-фид не отвечает (timeout 30s) | Пропустить, логировать warning |
| RSS-фид отдаёт невалидный XML | Пропустить, логировать warning |
| Web Search API 429 (rate limit) | Retry с exponential backoff (3 попытки) |
| Web Search API 500 | Retry 1 раз, затем пропустить |
| Все RSS-фиды упали | Продолжить только с web search |
| Все web search упали | Продолжить только с RSS |
| LLM-классификация упала | Пропустить (сигналы без categories) |
| < 10 сигналов собрано | Вернуть что есть + warning в логе |

---

## 3. EventCalendar (`src/agents/collectors/event_calendar.py`)

Агент поиска запланированных событий на целевую дату. Основной источник -- веб-поиск + LLM-структурирование.

### Логика работы

1. **Сформировать поисковые запросы** по типам событий (политические, экономические, дипломатические, судебные, культурные)
2. **Выполнить 5-8 веб-поисков** (параллельно)
3. **LLM-структурирование**: из сырых результатов поиска извлечь и структурировать события
4. **Дедупликация**: одно событие может упоминаться в разных источниках
5. **Оценка newsworthiness**: LLM ранжирует события по медийной значимости

### Сигнатуры

```python
"""src/agents/collectors/event_calendar.py"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import ScheduledEvent, EventType, EventCertainty

if TYPE_CHECKING:
    from src.data_sources.web_search import WebSearchClient
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class EventCalendar(BaseAgent):
    """Агент поиска запланированных событий на target_date.

    Комбинирует веб-поиск с LLM-структурированием для извлечения
    событий из множества источников (календари, расписания, анонсы).

    Результат: 10-30 ScheduledEvent, ранжированных по newsworthiness.

    LLM-модель:
    - Структурирование: openai/gpt-4o-mini (дешёвый, быстрый)
    - Итоговая оценка: anthropic/claude-sonnet-4 (точность)

    Стоимость: ~$0.50-1.00 за прогноз.
    """

    name = "event_calendar"

    def get_timeout_seconds(self) -> int:
        return 300  # 5 минут

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.target_date:
            return "target_date is required"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Основная логика поиска событий.

        Returns:
            {"scheduled_events": List[ScheduledEvent]}
        """
        target = context.target_date

        # 1. Поисковые запросы по типам событий
        queries = self._build_event_queries(target)

        # 2. Параллельный поиск
        raw_results = await self._search_events(queries)

        # 3. LLM: извлечение и структурирование событий
        events = await self._extract_events(raw_results, target)

        # 4. Дедупликация
        events = self._deduplicate_events(events)

        # 5. LLM: оценка newsworthiness + potential_impact
        events = await self._assess_events(events, context.outlet)

        # 6. Сортировка
        events.sort(key=lambda e: e.newsworthiness, reverse=True)

        self.logger.info("Found %d scheduled events for %s", len(events), target)

        return {"scheduled_events": events}

    def _build_event_queries(self, target_date: date) -> list[str]:
        """Формирование поисковых запросов по типам событий.

        Генерирует 5-8 запросов, покрывающих основные домены:

        1. Политика: "political events scheduled {date}"
                     "parliamentary sessions votes {date}"
        2. Экономика: "economic data releases {date}"
                      "central bank meetings {date}"
                      "earnings reports {date}"
        3. Дипломатия: "international summits meetings {date}"
                       "UN sessions {date}"
        4. Суды: "major court hearings verdicts {date}"
        5. Культура/спорт: "major events conferences {date}"

        Для русскоязычных СМИ -- дублирует часть запросов на русском.

        Args:
            target_date: Целевая дата.

        Returns:
            5-8 поисковых запросов.
        """
        ...

    async def _search_events(
        self,
        queries: list[str],
    ) -> list[dict]:
        """Параллельное выполнение поисковых запросов.

        Args:
            queries: Поисковые запросы.

        Returns:
            Список сырых результатов поиска (title + snippet + url).
        """
        ...

    async def _extract_events(
        self,
        raw_results: list[dict],
        target_date: date,
    ) -> list[ScheduledEvent]:
        """LLM-извлечение структурированных событий из сырых результатов.

        Промпт (модель: openai/gpt-4o-mini):
        ```
        You are an event extraction assistant. From the following
        search results, extract scheduled events for {target_date}.

        For each event, provide:
        - title (concise, factual)
        - description (what will happen, who participates)
        - event_type (political/economic/diplomatic/judicial/
                      military/cultural/scientific/sports/other)
        - certainty (confirmed/likely/possible/speculative)
        - location
        - participants (list of key names/organizations)
        - potential_impact (1 sentence: why this matters for news)

        Only include events that are actually scheduled for {target_date}
        or within 1 day of it. Do NOT include general news.

        Return JSON array of events.

        Search results:
        {formatted_results}
        ```

        Args:
            raw_results: Сырые результаты веб-поиска.
            target_date: Целевая дата для фильтрации.

        Returns:
            Структурированные ScheduledEvent[].
        """
        ...

    def _deduplicate_events(
        self,
        events: list[ScheduledEvent],
    ) -> list[ScheduledEvent]:
        """Дедупликация событий по семантическому сходству.

        Стратегия: fuzzy matching по title (Levenshtein ratio > 0.8)
        + совпадение event_type + event_date. При дубле оставляем
        более полное описание.

        Args:
            events: Потенциально дублированные события.

        Returns:
            Уникальные события.
        """
        ...

    async def _assess_events(
        self,
        events: list[ScheduledEvent],
        outlet: str,
    ) -> list[ScheduledEvent]:
        """LLM-оценка newsworthiness и potential_impact.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        You are a news editor at {outlet}. Rate each scheduled event
        for newsworthiness (0.0-1.0) considering:
        - Will this event generate headlines?
        - How many outlets will cover it?
        - Is it routine or exceptional?
        - Does it affect many people?

        Events:
        {formatted_events}

        Return JSON array: [{"index": 0, "newsworthiness": 0.85,
        "potential_impact": "..."}]
        ```

        Args:
            events: Структурированные события.
            outlet: Название СМИ (для контекста).

        Returns:
            События с заполненными newsworthiness и potential_impact.
        """
        ...
```

### LLM-вызовы

| Вызов | Модель | Input ~tokens | Output ~tokens | Назначение |
|---|---|---|---|---|
| `_extract_events` | openai/gpt-4o-mini | 2000-4000 | 1000-2000 | Структурирование результатов поиска в ScheduledEvent |
| `_assess_events` | anthropic/claude-sonnet-4 | 1000-2000 | 500-1000 | Оценка newsworthiness и impact |

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| Web Search API недоступен | Fallback: LLM-запрос "What events are scheduled for {date}?" без поиска |
| LLM не парсит JSON | Retry 1 раз с уточнённым промптом + "Return ONLY valid JSON" |
| 0 событий найдено | Вернуть пустой список (не ошибка -- может быть тихий день) |
| > 50 событий | Оставить top-30 по newsworthiness |

---

## 4. OutletHistorian (`src/agents/collectors/outlet_historian.py`)

Агент анализа стилевого и редакционного профиля целевого СМИ. Скрейпит последние 30 дней публикаций и проводит LLM-анализ.

### Логика работы

1. **Проверить кеш**: если профиль для данного outlet создан < 7 дней назад -- вернуть из кеша (стиль меняется медленно)
2. **Получить URL издания** из каталога `outlets_catalog.py`
3. **Скрейпить последние 30 дней**: использовать `src/data_sources/scraper.py` для получения заголовков и первых абзацев
4. **Собрать 50-100 статей** (заголовок + первый абзац + URL + дата)
5. **LLM-анализ стиля заголовков**: HeadlineStyle
6. **LLM-анализ стиля текстов**: WritingStyle
7. **LLM-анализ редакционной позиции**: EditorialPosition
8. **Формирование OutletProfile**

### Сигнатуры

```python
"""src/agents/collectors/outlet_historian.py"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.schemas.events import (
    OutletProfile,
    HeadlineStyle,
    WritingStyle,
    EditorialPosition,
)

if TYPE_CHECKING:
    from src.data_sources.scraper import Scraper, ScrapedArticle
    from src.data_sources.outlets_catalog import OutletCatalogEntry
    from src.llm.providers import LLMClient
    from src.schemas.pipeline import PipelineContext


class OutletHistorian(BaseAgent):
    """Агент анализа стиля и редакционной позиции целевого СМИ.

    Скрейпит последние 30 дней публикаций, анализирует через LLM
    стиль заголовков, структуру текстов и редакционные предпочтения.

    Результат: OutletProfile -- используется в Framing (Stage 7)
    и Generation (Stage 8).

    LLM-модель: anthropic/claude-sonnet-4 (точность анализа стиля).
    Стоимость: ~$1.00-1.50 за прогноз.

    Кеширование: профиль кешируется на 7 дней (стиль СМИ меняется
    медленно). Кеш хранится в SQLite.
    """

    name = "outlet_historian"

    # Период анализа
    ANALYSIS_PERIOD_DAYS = 30

    # Максимум статей для анализа
    MAX_ARTICLES = 100

    # TTL кеша профиля (дни)
    CACHE_TTL_DAYS = 7

    def get_timeout_seconds(self) -> int:
        return 600  # 10 минут (скрейпинг может быть медленным)

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.outlet:
            return "outlet is required"
        return None

    async def execute(self, context: PipelineContext) -> dict:
        """Основная логика анализа издания.

        Returns:
            {"outlet_profile": OutletProfile}
        """
        outlet = context.outlet

        # 1. Проверка кеша
        cached = await self._get_cached_profile(outlet)
        if cached is not None:
            self.logger.info("Using cached profile for '%s'", outlet)
            return {"outlet_profile": cached}

        # 2. Получение метаданных издания из каталога
        catalog_entry = self._get_catalog_entry(outlet)

        # 3. Скрейпинг
        articles = await self._scrape_articles(catalog_entry)

        if len(articles) < 5:
            self.logger.warning(
                "Only %d articles scraped for '%s' (min: 5)",
                len(articles), outlet,
            )
            # Продолжаем с тем что есть -- лучше плохой профиль, чем никакого

        # 4. LLM-анализ (3 параллельных вызова)
        headline_style, writing_style, editorial = await asyncio.gather(
            self._analyze_headline_style(articles, outlet),
            self._analyze_writing_style(articles, outlet),
            self._analyze_editorial_position(articles, outlet),
        )

        # 5. Формирование профиля
        profile = OutletProfile(
            outlet_name=outlet,
            outlet_url=catalog_entry.url if catalog_entry else "",
            language=catalog_entry.language if catalog_entry else "ru",
            headline_style=headline_style,
            writing_style=writing_style,
            editorial_position=editorial,
            sample_headlines=[a.title for a in articles[:30]],
            sample_first_paragraphs=[
                a.first_paragraph for a in articles[:10]
                if a.first_paragraph
            ],
            analysis_period_days=self.ANALYSIS_PERIOD_DAYS,
            articles_analyzed=len(articles),
        )

        # 6. Сохранение в кеш
        await self._cache_profile(outlet, profile)

        return {"outlet_profile": profile}

    async def _get_cached_profile(
        self,
        outlet: str,
    ) -> OutletProfile | None:
        """Проверить наличие актуального профиля в кеше (SQLite).

        Args:
            outlet: Название СМИ.

        Returns:
            OutletProfile если кеш актуален (< CACHE_TTL_DAYS), иначе None.
        """
        ...

    async def _cache_profile(
        self,
        outlet: str,
        profile: OutletProfile,
    ) -> None:
        """Сохранить профиль в кеш (SQLite).

        Args:
            outlet: Название СМИ.
            profile: Профиль для кеширования.
        """
        ...

    def _get_catalog_entry(
        self,
        outlet: str,
    ) -> OutletCatalogEntry | None:
        """Получить метаданные издания из каталога.

        Args:
            outlet: Название СМИ.

        Returns:
            Каталожная запись или None если издание не в каталоге.
        """
        ...

    async def _scrape_articles(
        self,
        catalog_entry: OutletCatalogEntry | None,
    ) -> list[ScrapedArticle]:
        """Скрейпинг последних публикаций издания.

        Использует src/data_sources/scraper.py:Scraper.
        Стратегия:
        1. Если есть RSS-фид в каталоге -- сначала из RSS (быстрее)
        2. Если RSS недостаточно -- playwright-скрейпинг главной страницы
           и архива
        3. Берём заголовки + первые абзацы за последние ANALYSIS_PERIOD_DAYS

        Args:
            catalog_entry: Метаданные издания.

        Returns:
            50-100 статей (заголовок + первый абзац + URL + дата).
        """
        ...

    async def _analyze_headline_style(
        self,
        articles: list[ScrapedArticle],
        outlet: str,
    ) -> HeadlineStyle:
        """LLM-анализ стиля заголовков.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- лингвист-медиааналитик. Проанализируй стиль заголовков
        издания "{outlet}" на основе следующих примеров.

        Определи:
        1. Средняя длина (символы, слова)
        2. Использование двоеточий (Тема: деталь)
        3. Использование цитат в заголовках
        4. Вопросительные заголовки
        5. Числа в заголовках
        6. Стиль капитализации
        7. Регистр лексики (формальный/нейтральный/разговорный)
        8. Эмоциональная тональность
        9. Повторяющиеся паттерны/шаблоны (минимум 3)

        Заголовки:
        {headlines}

        Верни JSON:
        {
            "avg_length_chars": int,
            "avg_length_words": int,
            "uses_colons": bool,
            "uses_quotes": bool,
            "uses_questions": bool,
            "uses_numbers": bool,
            "capitalization": "sentence_case|title_case|...",
            "vocabulary_register": "formal|neutral|...",
            "emotional_tone": "neutral|alarming|...",
            "common_patterns": ["pattern1", "pattern2", ...]
        }
        ```

        Args:
            articles: Статьи для анализа.
            outlet: Название издания.

        Returns:
            HeadlineStyle с заполненными полями.
        """
        ...

    async def _analyze_writing_style(
        self,
        articles: list[ScrapedArticle],
        outlet: str,
    ) -> WritingStyle:
        """LLM-анализ стиля текстов.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- лингвист-медиааналитик. Проанализируй стиль текстов
        издания "{outlet}" на основе первых абзацев.

        Определи:
        1. Стиль первого абзаца:
           - inverted_pyramid: кто-что-где-когда
           - narrative: сторителлинг, погружение в сцену
           - analytical: тезис + контекст
           - quote_lead: начинается с цитаты
        2. Среднее число предложений в первом абзаце
        3. Среднее число слов в первом абзаце
        4. Стиль атрибуции источников:
           - source_first: "По данным Reuters, ..."
           - source_last: "..., сообщает Reuters"
           - inline: "Reuters сообщает, что..."
        5. Наличие датлайна (ГОРОД, дата —)
        6. Типичная длина абзаца (short/medium/long)

        Первые абзацы:
        {first_paragraphs}

        Верни JSON:
        {
            "first_paragraph_style": "inverted_pyramid|narrative|...",
            "avg_first_paragraph_sentences": int,
            "avg_first_paragraph_words": int,
            "attribution_style": "source_first|source_last|inline",
            "uses_dateline": bool,
            "paragraph_length": "short|medium|long"
        }
        ```

        Args:
            articles: Статьи для анализа.
            outlet: Название издания.

        Returns:
            WritingStyle.
        """
        ...

    async def _analyze_editorial_position(
        self,
        articles: list[ScrapedArticle],
        outlet: str,
    ) -> EditorialPosition:
        """LLM-анализ редакционной позиции.

        Промпт (модель: anthropic/claude-sonnet-4):
        ```
        Ты -- медиааналитик. На основе заголовков и текстов издания
        "{outlet}" за последние 30 дней, определи:

        1. Общая тональность издания:
           neutral, conservative, liberal, sensationalist,
           analytical, official, oppositional

        2. Основные темы фокуса (5-10 тем, в порядке приоритета)

        3. Темы, которые издание избегает или почти не освещает

        4. Фрейминговые тенденции:
           - pro_government / oppositional
           - market_oriented / state_oriented
           - human_interest / institutional
           - conflict_frame / cooperation_frame
           - national_security / human_rights

        5. Предпочтительные источники и типы экспертов

        6. Позиция по ключевым текущим темам (3-5 тем):
           Формат: {тема: краткое описание позиции}

        7. Систематические пропуски / слепые зоны

        Заголовки и абзацы:
        {articles_text}

        Верни JSON:
        {
            "tone": "neutral|conservative|...",
            "focus_topics": ["topic1", "topic2", ...],
            "avoided_topics": ["topic1", ...],
            "framing_tendencies": ["tendency1", ...],
            "source_preferences": ["pref1", ...],
            "stance_on_current_topics": {"topic": "stance", ...},
            "omissions": ["omission1", ...]
        }
        ```

        Args:
            articles: Статьи для анализа.
            outlet: Название издания.

        Returns:
            EditorialPosition.
        """
        ...
```

### LLM-вызовы

Три вызова выполняются **параллельно** через `asyncio.gather`:

| Вызов | Модель | Input ~tokens | Output ~tokens | Назначение |
|---|---|---|---|---|
| `_analyze_headline_style` | anthropic/claude-sonnet-4 | 2000-3000 | 500-800 | Анализ стиля заголовков |
| `_analyze_writing_style` | anthropic/claude-sonnet-4 | 3000-5000 | 300-500 | Анализ стиля текстов |
| `_analyze_editorial_position` | anthropic/claude-sonnet-4 | 4000-6000 | 800-1200 | Анализ редакционной позиции |

### Кеширование

- **Где**: таблица `outlet_profiles` в SQLite
- **Ключ**: `outlet_name` (нормализованный: lowercase, strip)
- **TTL**: 7 дней (стиль СМИ не меняется часто)
- **Инвалидация**: вручную через CLI `scripts/invalidate_cache.py`
- **Размер**: ~5-10 KB на профиль (JSON)

### Обработка ошибок

| Ситуация | Стратегия |
|---|---|
| Издание не в каталоге | Web search "site:{outlet}", попытка найти URL автоматически |
| Scraper заблокирован (403/captcha) | Fallback: web search "{outlet} headlines this week" |
| < 5 статей за 30 дней | Расширить период до 60 дней, предупредить в логе |
| 0 статей | Вернуть minimal OutletProfile (default values + outlet_name) |
| LLM не парсит JSON | Retry 1 раз с "Return ONLY valid JSON, no markdown" |
| Один из 3 LLM-вызовов упал | Использовать default значения для этого раздела |

---

## 5. Диаграмма взаимодействия коллекторов

```
                    PipelineContext
                    (outlet, target_date)
                         │
            ┌────────────┼────────────┐
            │            │            │
            ▼            ▼            ▼
     ┌────────────┐ ┌──────────┐ ┌──────────────┐
     │ NewsScout  │ │ Event    │ │ Outlet       │
     │            │ │ Calendar │ │ Historian    │
     └─────┬──────┘ └────┬─────┘ └──────┬───────┘
           │              │              │
      ┌────┴────┐    ┌───┴───┐    ┌─────┴─────┐
      │         │    │       │    │           │
      ▼         ▼    ▼       ▼    ▼           ▼
   ┌─────┐ ┌──────┐ │  Web   │ ┌────────┐ ┌─────┐
   │ RSS │ │ Web  │ │ Search │ │Scraper │ │ LLM │
   │Fetch│ │Search│ │  +LLM  │ │        │ │ x3  │
   └──┬──┘ └──┬───┘ └───┬───┘ └───┬────┘ └──┬──┘
      │       │          │         │          │
      ▼       ▼          ▼         ▼          ▼
  List[Signal  ]    List[Sched   ]     OutletProfile
   Record]            uledEvent]
      │               │              │
      └───────────────┼──────────────┘
                      │
                      ▼
              PipelineContext
              (signals, scheduled_events, outlet_profile)
```

---

## 6. Порядок реализации коллекторов

1. **Схемы** (`src/schemas/events.py`): SignalRecord, ScheduledEvent, OutletProfile и вложенные
2. **NewsScout** -- проще всего, минимум LLM-зависимостей
3. **EventCalendar** -- требует рабочий web_search + LLM-parsing
4. **OutletHistorian** -- самый сложный (скрейпинг + 3 LLM-вызова + кеш)

Для каждого агента -- сначала интеграционный тест с mock LLM, затем E2E тест с реальным API (помечен `@pytest.mark.integration`).
