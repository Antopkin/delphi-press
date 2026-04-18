---
title: "Стадии 1–2: Сбор данных и идентификация событий"
description: "Стадия 1 (Collection) занимается параллельным сбором 100–200 новостных сигналов и планировщиком событий. Стадия 2 (Event Identification) кластеризует сигналы в событийные нити и оценивает их..."
---

# Стадии 1–2: Сбор данных и идентификация событий

## Обзор

**Стадия 1 (Collection)** занимается параллельным сбором 100–200 новостных сигналов и планировщиком событий. **Стадия 2 (Event Identification)** кластеризует сигналы в событийные нити и оценивает их значимость.

Результат Стадии 1 передаётся в Стадию 2, которая отсеивает шум и группирует связанные новости в **20 событийных нитей**, готовых для анализа.

---

## Стадия 1: Сбор данных

### Архитектура: четыре параллельных агента

| Агент | Входная роль | Выходная схема | LLM |
|-------|----------|---|---|
| **NewsScout** | RSS + поиск | `list[SignalRecord]` | Только классификация |
| **EventCalendar** | Поиск событий на target_date | `list[ScheduledEvent]` | ExtractEventsPrompt, AssessEventsPrompt |
| **OutletHistorian** | Профилирование издания | `OutletProfile` | HeadlineStyle, WritingStyle, EditorialPosition |
| **ForesightCollector** | Метакулус + Polymarket + GDELT | foresight_events, foresight_signals | Нет |

Все четыре агента запускаются **параллельно** через `asyncio.gather()`. Таймаут каждого: 600 сек (NewsScout, OutletHistorian), 120 сек (ForesightCollector).

### NewsScout: Сбор новостных сигналов

**Входные данные:**

- Целевое издание (`context.outlet`)
- Целевая дата (`context.target_date`)

**Процесс:**

1. **RSS-сбор**: 8 глобальных фидов + фиды из каталога издания
   ```python
   GLOBAL_RSS_FEEDS = [
       "https://feeds.bbci.co.uk/news/world/rss.xml",
       "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
       "https://www.aljazeera.com/xml/rss/all.xml",
       "https://feeds.washingtonpost.com/rss/world",
       "https://www.theguardian.com/world/rss",
       "https://tass.com/rss/v2.xml",
       "https://ria.ru/export/rss2/archive/index.xml",
       "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
   ]
   ```
   
   **Таблица источников GLOBAL_RSS_FEEDS:**

   | Категория | Издание | Язык |
   |-----------|---------|------|
   | Глобальные | BBC News | EN |
   | Глобальные | The New York Times | EN |
   | Глобальные | Al Jazeera | EN |
   | Глобальные | The Washington Post | EN |
   | Глобальные | The Guardian | EN |
   | Русскоязычные | ТАСС | RU |
   | Русскоязычные | РИА Новости | RU |
   | Русскоязычные | РБК | RU |

   !!! note "Динамические RSS-фиды"
       Дополнительные RSS-фиды загружаются динамически через `OutletResolver` при указании конкретного целевого издания. Механизм позволяет интегрировать фиды любых других медиаизданий, обнаруженных через Wikidata и директорию RSS.
   
   Параметры: `days_back=7`, таймаут на фид **15 сек**, параллелизм 20 фидов, кеш 5 минут.

2. **Web Search**: 3 поисковых запроса
   ```python
   [
       f"latest news {date_str}",
       f"{outlet} headlines {date_str}",
       f"breaking news world events {date_str}",
   ]
   ```
   
   Каждый запрос: `num_results=15`, выполняются параллельно.

3. **Дедупликация**: По URL (case-insensitive), сохраняется версия с наивысшей `relevance_score`.

4. **LLM-классификация** (опциональная): Если сигнал не имеет categories или entities, отправляется в `news_scout_search` (Gemini 3.1 Flash Lite).
   - Батчи по 20 сигналов
   - JSON-режим

5. **Ранжирование и отсев**: Сортировка по `relevance_score` (убывание), топ-200 (`MAX_SIGNALS = 200`).

!!! warning "RSS-таймаут"
    Таймаут на один фид составляет **15 секунд**, не 30.

**Схема SignalRecord:**

| Поле | Тип | Обязательное |
|------|-----|---|
| `id` | str | ✓ (формат: `rss_{sha256[:8]}` или `ws_{hash}`) |
| `title` | str | ✓ |
| `summary` | str | max 1000 символов |
| `url` | str | ✓ |
| `source_name` | str | ✓ (e.g., "BBC News", "Reuters") |
| `source_type` | SignalSource | ✓ (RSS, WEB_SEARCH, SOCIAL, WIRE) |
| `published_at` | datetime | None |
| `language` | str | ISO 639-1 ("ru", "en", etc.) |
| `categories` | list[str] | [] |
| `entities` | list[str] | [] |
| `relevance_score` | float | 0.0–1.0 (RSS: 0.5, Web Search: 0.4) |

!!! note
    SignalSource — это `StrEnum` со значениями в **нижнем регистре**: `rss`, `web_search`, `social`, `wire`.

### EventCalendar: Поиск запланированных событий

**Входные данные:**

- Целевая дата (`context.target_date`)
- Целевое издание (`context.outlet`)

**Процесс:**

1. **Web Search**: 7 специализированных запросов по доменам
   ```python
   [
       f"scheduled political events {date}",
       f"economic calendar events {date}",
       f"diplomatic meetings summits {date}",
       f"court hearings legal proceedings {date}",
       f"cultural sports events {date}",
       f"parliamentary sessions votes {date}",
       f"central bank meetings decisions {date}",
   ]
   ```
   
   Каждый: `num_results=10`, параллельно.

2. **LLM-структурирование** (ExtractEventsPrompt): Парсинг результатов поиска → ScheduledEvent-объекты.
   - Модель: gemini-3.1-flash-lite (task `event_calendar`)
   - JSON-режим

3. **Дедупликация**: Levenshtein-расстояние (ratio > 80) + совпадение типа события + дата.
   - Пороговое значение: `LEVENSHTEIN_THRESHOLD = 80`
   - При дубликате сохраняется версия с более длинным описанием

4. **LLM-оценка newsworthiness** (AssessEventsPrompt):
   - Модель: claude-opus-4.6 (task `event_assessment`)
   - Для каждого события оценивается `newsworthiness` и `potential_impact`

5. **Ранжирование и отсев**: Сортировка по `newsworthiness` (убывание), топ-30 (`MAX_EVENTS = 30`).

**Схема ScheduledEvent:**

| Поле | Тип | Обязательное |
|------|-----|---|
| `id` | str | ✓ (формат: `evt_{sha256[:8]}`) |
| `title` | str | ✓ |
| `description` | str | |
| `event_date` | date | ✓ |
| `event_type` | EventType | ✓ |
| `certainty` | EventCertainty | confirmed/likely/possible/speculative |
| `location` | str | |
| `participants` | list[str] | |
| `source_url` | str | |
| `newsworthiness` | float | 0.0–1.0 |
| `potential_impact` | str | |

### OutletHistorian: Профилирование издания

**Входные данные:**

- Целевое издание (`context.outlet`)

**Процесс:**

1. **Скрейпинг статей**: До 20 статей с последних 14 дней (`max_articles=20`, `days_back=14`).

2. **Параллельный LLM-анализ** (три задачи одновременно):

   a) **HeadlineStylePrompt** (outlet_historian, claude-opus-4.6)
      - Вход: топ-50 заголовков
      - Выход: `HeadlineStyle`
        - avg_length_chars, avg_length_words
        - uses_colons, uses_quotes, uses_questions, uses_numbers
        - capitalization, vocabulary_register, emotional_tone
        - common_patterns

   b) **WritingStylePrompt** (outlet_historian, claude-opus-4.6)
      - Вход: топ-20 первых абзацев
      - Выход: `WritingStyle`
        - first_paragraph_style
        - avg_first_paragraph_sentences, avg_first_paragraph_words
        - attribution_style, uses_dateline
        - paragraph_length

   c) **EditorialPositionPrompt** (outlet_historian, claude-opus-4.6)
      - Вход: топ-30 статей (заголовок + первый абзац)
      - Выход: `EditorialPosition`
        - tone (neutral/conservative/liberal/sensationalist/analytical/official/oppositional)
        - focus_topics, avoided_topics
        - framing_tendencies, source_preferences
        - stance_on_current_topics (dict), omissions

3. **Кеширование**: Результат кешируется на 7 дней.

4. **Fallback**: Если LLM-анализ не удаётся, возвращаются значения по умолчанию.

**Схема OutletProfile:**

| Поле | Тип | Обязательное |
|------|-----|---|
| `outlet_name` | str | ✓ |
| `outlet_url` | str | |
| `language` | str | ISO 639-1 (по умолчанию "ru") |
| `headline_style` | HeadlineStyle | ✓ |
| `writing_style` | WritingStyle | ✓ |
| `editorial_position` | EditorialPosition | ✓ |
| `sample_headlines` | list[str] | max 50, обычно 30 |
| `sample_first_paragraphs` | list[str] | max ~10 |
| `analysis_period_days` | int | 30 |
| `articles_analyzed` | int | обычно 20 |
| `analyzed_at` | datetime | timestamp анализа |

### ForesightCollector: Форсайт-данные

**Входные данные:**

- Целевое издание (`context.outlet`)
- Целевая дата (`context.target_date`)

**API-источники:**

1. **Metaculus**: Endpoint `GET https://www.metaculus.com/api/posts/`
   - Auth: optional Token (бесплатный)
   - Таймаут: 30 сек
   - Выход: `list[dict]` → маппируется в foresight_events

2. **Polymarket**: 3 отдельных API
   - **Gamma API** (markets list): `https://gamma-api.polymarket.com/markets`
   - **CLOB API** (price history): `https://clob.polymarket.com`
   - **Data API** (live trades): `https://data-api.polymarket.com`
   - Таймаут: 30 сек за API
   - Выход: `list[dict]` (markets + price_history + metrics) → foresight_signals

3. **GDELT**: Global Event Data Monitoring
   - Endpoint: `https://api.gdeltproject.org/api/v2/`
   - Параметр: `language` (russian/english/etc.)
   - Параметр: `query` (только ASCII, Cyrillic отклоняется)
   - Таймаут: 30 сек
   - Выход: `list[dict]` → foresight_signals

**Грейсфул деградация:**

- Каждый API вызывается в `asyncio.gather(..., return_exceptions=True)`
- Если один API падает, агент продолжает с остальными
- Лог: какие источники дали данные (`sources_used: list[str]`)

**Маппинг Polymarket:**

- condition_id (CTF hash) → используется как market_id (совпадает с inverse profiles)
- Если условие доступно: price_history → compute_market_metrics
- Если inverse profiles загружены: live trades (Data API) → compute_informed_signal

**Ограничения выхода:**

- `MAX_FORESIGHT_EVENTS = 30`
- `MAX_FORESIGHT_SIGNALS = 100`

---

## Стадия 2: Идентификация событий (Event Identification)

### Архитектура: единственный агент

| Агент | Входные схемы | Выходные схемы | Процесс |
|-------|---|---|---|
| **EventTrendAnalyzer** | signals[], scheduled_events[] | event_threads[], trajectories[], cross_impact_matrix | TF-IDF → HDBSCAN → LLM-лейблинг → scoring |

EventTrendAnalyzer запускается **последовательно** после Collection. Это единственный агент Stage 2.

### Процесс кластеризации

#### 1. Подготовка сигналов

```python
if len(signals) < 10:  # _MIN_SIGNALS_FOR_CLUSTERING
    # Каждый сигнал = отдельная нить (без кластеризации)
    raw_clusters = [{"signals": [s], ...} for s in signals]
else:
    # Полная кластеризация
```

#### 2. TF-IDF векторизация

```python
from sklearn.feature_extraction.text import TfidfVectorizer

vectorizer = TfidfVectorizer(max_features=1536)
texts = [f"{signal.title}. {signal.summary}" for signal in signals]
embeddings = vectorizer.fit_transform(texts).toarray()
```

!!! warning
    Используется **TF-IDF** (scikit-learn), а **НЕ** API-эмбеддинги! Stop-words не отключаются.

#### 3. Кластеризация: HDBSCAN с fallback на KMeans

```python
import hdbscan

clusterer = hdbscan.HDBSCAN(
    min_cluster_size=3,        # HDBSCAN_MIN_CLUSTER_SIZE
    min_samples=2,             # HDBSCAN_MIN_SAMPLES
    metric="euclidean",        # Евклидова метрика, НЕ cosine!
)
labels = clusterer.fit_predict(embeddings)
```

**Fallback (если hdbscan не установлен):**
```python
from sklearn.cluster import KMeans

n_clusters = min(20, max(3, len(signals) // 3))
kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
labels = kmeans.fit_predict(embeddings)
```

**Обработка noise-кластера (-1):**

- Если в noise-кластере < 5 сигналов → отбросить
- Если >= 5 → создать pseudo-кластер

#### 4. LLM-лейблинг кластеров

Модель: **google/gemini-3.1-flash-lite-preview** (task `event_clustering`), JSON-режим.

**Вход**: top-10 заголовков из каждого кластера.

**Выход**: ClusterLabel
```python
{
    "title": "Краткое название события",
    "summary": "2-3 предложения о смысле события",
    "category": "politics | economy | etc.",
    "importance": 0.0–1.0,
    "entity_prominence": 0.0–1.0,
}
```

**Graceful fallback**: Если LLM падает, используются заголовки первых 3 сигналов как title/summary.

#### 5. Расчёт significance_score

```python
sig_score = (
    0.30 * importance +
    0.25 * (cluster_size / max_cluster_size) +
    0.20 * recency_score +
    0.15 * source_diversity +
    0.10 * entity_prominence
)
```

**source_diversity**: `len(unique_sources) / len(signals_in_cluster)`

**recency_score**: Экспоненциальное затухание с half-life 12 часов
```python
hours_ago = (now - latest_signal).total_seconds() / 3600
recency_score = 2.0 ** (-hours_ago / 12.0)
```

#### 6. Ранжирование и отсев

Сортировка по significance_score (убывание), топ-20 (по умолчанию).

### Схема EventThread

| Поле | Тип | Обязательное |
|------|-----|---|
| `id` | str | ✓ (формат: `thread_{md5[:8]}`) |
| `title` | str | ✓ |
| `summary` | str | ✓ |
| `signal_ids` | list[str] | ID сигналов в кластере |
| `scheduled_event_ids` | list[str] | Связанные запланированные события |
| `cluster_size` | int | Количество сигналов в кластере |
| `category` | str | politics/economy/etc. |
| `entities` | list[str] | Топ-10 сущностей по частоте |
| `source_diversity` | float | 0.0–1.0 |
| `earliest_signal` | datetime | Самый старый сигнал |
| `latest_signal` | datetime | Самый свежий сигнал |
| `recency_score` | float | 0.0–1.0 |
| `significance_score` | float | 0.0–1.0 (итоговый балл) |
| `importance` | float | 0.0–1.0 (от LLM) |
| `entity_prominence` | float | 0.0–1.0 (от LLM) |

### Траектории и cross-impact (параллельные LLM-задачи)

После лейблинга, для каждого EventThread вычисляются:

1. **EventTrajectory** (task `trajectory_analysis`, claude-opus-4.6)
   - current_state, momentum (escalating/stable/de_escalating)
   - 3 сценария (baseline, optimistic, pessimistic) с вероятностями
   - key_drivers, uncertainties

2. **CrossImpactMatrix** (task `cross_impact_analysis`, claude-opus-4.6)
   - Матрица влияний между всеми парами event_threads
   - impact_score: -1.0 до +1.0
   - Sparse representation (только ненулевые ячейки)

Обе задачи выполняются параллельно через `asyncio.gather()`. Graceful fallback: если одна падает, результаты других сохраняются.

---

## PipelineContext: слоты Stage 1–2

| Слот | Тип | Кто заполняет | Кто читает |
|------|-----|---|---|
| `signals` | list[dict] | NewsScout | EventTrendAnalyzer, Framing, QualityGate |
| `scheduled_events` | list[dict] | EventCalendar | EventTrendAnalyzer, Framing |
| `outlet_profile` | dict | OutletHistorian | Framing, Generation |
| `foresight_events` | list[dict] | ForesightCollector | Delphi R1 (опционально) |
| `foresight_signals` | list[dict] | ForesightCollector | Delphi R1 (опционально) |
| `event_threads` | list[dict] | EventTrendAnalyzer | Delphi R1, Trajectory, Framing, QualityGate |
| `trajectories` | list[dict] | EventTrendAnalyzer | Delphi R1 (опционально) |
| `cross_impact_matrix` | dict | EventTrendAnalyzer | Delphi R1, Consensus |

---

## Обработка ошибок и graceful degradation

### Stage 1

| Сценарий | Поведение |
|----------|---|
| RSS fetch все упали | Логирование, продолжение с web search |
| Web search упал | Логирование, продолжение с RSS |
| Оба упали | RuntimeError: "Both RSS and web search returned no results" |
| LLM-классификация упала | Пропуск batch, сигналы возвращаются без categories/entities |
| EventCalendar LLM упал | Запланированные события возвращаются без newsworthiness |
| OutletHistorian LLM упал | Возвращаются значения по умолчанию |
| Polymarket/GDELT/Metaculus упал | Продолжение с остальными источниками, лог sources_used |

### Stage 2

| Сценарий | Поведение |
|----------|---|
| < 10 сигналов | Каждый сигнал становится отдельной нитью (skip clustering) |
| LLM-лейблинг упал | Использование заголовков первых 3 сигналов как title/summary |
| Trajectory LLM упал | Пропуск trajectories, event_threads всё равно возвращаются |
| Cross-impact LLM упал | Пропуск cross_impact_matrix, event_threads всё равно возвращаются |

---

## Производительность и параметры

| Параметр | Значение | Назначение |
|----------|----------|---|
| NewsScout таймаут | 600 сек | Параллелизм 20 фидов + web search |
| RSS timeout | 15 сек | На один фид |
| RSS cache TTL | 300 сек (5 мин) | Conditional GET (ETag, Last-Modified) |
| MAX_SIGNALS | 200 | Топ по relevance_score |
| MAX_EVENTS | 30 | Топ по newsworthiness |
| EventCalendar таймаут | Включен в 600 сек NewsScout | Параллельно с ним |
| OutletHistorian таймаут | 600 сек | Параллельно с NewsScout |
| ForesightCollector таймаут | 120 сек | 3 API параллельно |
| EventTrendAnalyzer таймаут | 600 сек | Последовательно после Collection |
| MAX_THREADS | 20 | Топ event_threads по significance_score |
| HDBSCAN min_cluster_size | 3 | Минимум сигналов в кластере |
| HDBSCAN min_samples | 2 | Параметр плотности |
| HDBSCAN metric | euclidean | Расстояние в TF-IDF пространстве |
| TfidfVectorizer max_features | 1536 | Размер вокабуляра |
| Levenshtein threshold | 80 | Для дедупликации ScheduledEvent |
| Half-life recency | 12 часов | Экспоненциальное затухание |

---

## Примеры работы

### Пример 1: NewsScout на ТАСС за 2026-04-05

**Входные данные:**
```python
context.outlet = "ТАСС"
context.target_date = date(2026, 4, 5)
```

**Выход (sample):**
```python
{
    "signals": [
        {
            "id": "rss_a1b2c3d4",
            "title": "Правительство России одобрило новый налоговый пакет",
            "summary": "На заседании кабинета...",
            "url": "https://tass.com/...",
            "source_name": "ТАСС",
            "source_type": "rss",
            "published_at": datetime(2026, 4, 5, 14, 30, tzinfo=UTC),
            "language": "ru",
            "categories": ["politics", "economy"],
            "entities": ["Россия", "Правительство"],
            "relevance_score": 0.8,
        },
        # ... ещё 199 сигналов
    ]
}
```

### Пример 2: EventTrendAnalyzer с 150 сигналами

**Входные данные:**
```python
signals: list[SignalRecord]  # 150 сигналов
```

**Процесс:**
1. TF-IDF на 150 заголовков+summary
2. HDBSCAN → ~12 кластеров + noise
3. LLM-лейблинг каждого кластера
4. Расчёт significance_score
5. Сортировка, топ-20

**Выход (sample):**
```python
{
    "event_threads": [
        {
            "id": "thread_a1b2c3d4",
            "title": "Дипломатический кризис между Россией и ЕС",
            "summary": "После новых санкций дипломатическое напряжение между...",
            "signal_ids": ["rss_x1", "ws_x2", "rss_x3", ...],
            "cluster_size": 24,
            "significance_score": 0.87,
            "recency_score": 0.95,
            "source_diversity": 0.67,  # 8 разных источников из 24 сигналов
            "entities": ["Россия", "ЕС", "Брюссель", ...],
        },
        # ... ещё 19 потокиков
    ],
    "trajectories": [
        {
            "thread_id": "thread_a1b2c3d4",
            "current_state": "Дипломатическое напряжение нарастает...",
            "momentum": "escalating",
            "scenarios": [
                {"scenario_type": "baseline", "probability": 0.5, ...},
                {"scenario_type": "pessimistic", "probability": 0.3, ...},
                {"scenario_type": "optimistic", "probability": 0.2, ...},
            ],
        },
        # ... ещё 19 траекторий
    ],
    "cross_impact_matrix": {
        "entries": [
            {
                "source_thread_id": "thread_a1b2c3d4",
                "target_thread_id": "thread_e5f6g7h8",
                "impact_score": 0.65,
                "explanation": "Дипломатический кризис отрицательно влияет на торговлю...",
            },
        ]
    }
}
```

---

## Исходный код

- `src/agents/collectors/news_scout.py`
- `src/agents/collectors/event_calendar.py`
- `src/agents/collectors/outlet_historian.py`
- `src/agents/collectors/foresight_collector.py`
- `src/agents/analysts/event_trend.py`
- `src/data_sources/rss.py`
- `src/data_sources/foresight.py`
- `src/schemas/events.py`
- `src/schemas/pipeline.py`
- `src/llm/router.py`
