# 00 — Общий обзор системы

## Продукт

**Delphi Press** — веб-продукт для прогнозирования заголовков СМИ на заданную дату. Пользователь вводит название СМИ и целевую дату → система запускает мультиагентный пайплайн прогнозирования → выдаёт ранжированные прогнозы заголовков с уровнями уверенности и цепочкой обоснований.

**Целевая аудитория**: Исследователи-политологи, аналитики медиа, специалисты по молодёжной политике. Интерфейс рассчитан на нетехнических пользователей.

**Язык интерфейса**: Русский. Анализирует СМИ на любом языке. Результаты генерируются на языке целевого СМИ.

---

## Архитектура: модульный монолит с гибридным деплоем

### Принцип

Один Python-проект с чёткими границами между модулями. Каждый модуль:
- Живёт в своей директории
- Имеет определённый контракт (входные/выходные данные)
- Реализуется и тестируется независимо
- Общается с другими модулями через прямые вызовы функций (не HTTP)

### Деплой: 4 контейнера

```
┌─────────────────────────────────────────────────┐
│                    NGINX                         │
│           (reverse proxy + SSL)                  │
│              порты: 80, 443                      │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐    ┌──────────────────────┐
│       APP            │    │      WORKER           │
│   (FastAPI/Uvicorn)  │◄──►│   (ARQ worker)        │
│                      │    │                       │
│ • Веб-интерфейс     │    │ • Пайплайн прогноза   │
│ • REST API           │    │ • Агенты-сборщики     │
│ • SSE streaming      │    │ • Дельфи-симуляция    │
│ • Статика            │    │ • Генерация текста    │
│                      │    │                       │
│   порт: 8000         │    │   (без порта)         │
└──────────┬───────────┘    └──────────┬────────────┘
           │                           │
           ▼                           ▼
┌──────────────────────────────────────────────────┐
│                    REDIS                          │
│        (брокер задач + pub/sub для SSE)           │
│                 порт: 6379                        │
└──────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│              SQLite (файл на диске)               │
│          /app/data/foresighting.db                │
└──────────────────────────────────────────────────┘
```

**Почему не Celery, а ARQ**: ARQ — минималистичный async-совместимый task queue на Redis. FastAPI уже async, агенты async — Celery с его sync-моделью и тяжёлыми зависимостями не нужен. ARQ = 1 файл конфигурации.

**Почему SQLite, а не PostgreSQL**: Zero-config, single-file backup, достаточно для одного VPS. Миграция на PostgreSQL — замена connection string в конфиге.

---

## Стек технологий

| Слой | Технология | Версия | Обоснование |
|---|---|---|---|
| Язык | Python | 3.12+ | Async-native, type hints, экосистема LLM |
| Backend | FastAPI | 0.115+ | Async, SSE-поддержка, auto-OpenAPI, Jinja2 |
| Task Queue | ARQ | 0.26+ | Async Redis queue, минимальный overhead |
| БД | SQLite + aiosqlite | — | Zero-config, async через aiosqlite |
| ORM | SQLAlchemy 2.0 | 2.0+ | Async ORM, Alembic-миграции, type safety |
| Валидация | Pydantic v2 | 2.0+ | Схемы данных, настройки, LLM output parsing |
| LLM клиент | OpenAI Python SDK | 1.0+ | OpenRouter совместим с OpenAI API |
| YandexGPT | yandex-cloud-ml-sdk | — | Официальный SDK |
| HTTP клиент | httpx | 0.27+ | Async HTTP для RSS, web search, scraping |
| RSS | feedparser | 6.0+ | Парсинг RSS/Atom фидов |
| Frontend CSS | Pico.css | 2.0 | Semantic HTML, красиво без классов |
| Frontend JS | Vanilla JS | ES2022 | EventSource API для SSE, no build step |
| Шаблоны | Jinja2 | 3.1+ | Server-rendered, встроен в FastAPI |
| Deployment | Docker Compose | 2.0+ | Multi-container orchestration |
| Web server | Nginx | alpine | Reverse proxy, SSL termination |
| SSL | Let's Encrypt / Certbot | — | Бесплатные сертификаты |
| Форматирование | Ruff | latest | Линтер + форматтер (из CLAUDE.md) |
| Тесты | pytest + pytest-asyncio | — | Async тесты, httpx test client |

---

## Структура проекта

```
foresighting_news/
│
├── docker-compose.yml              # 4 сервиса: app, worker, redis, nginx
├── Dockerfile                      # Multi-stage build
├── nginx/
│   └── nginx.conf                  # Reverse proxy конфиг
│
├── .env.example                    # Шаблон переменных окружения
├── pyproject.toml                  # Зависимости, ruff, pytest
├── alembic.ini                     # Конфиг миграций
├── alembic/
│   ├── env.py
│   └── versions/
│
├── README.md                       # Описание, установка, использование
├── METHODOLOGY.md                  # Методология прогнозирования
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app factory, lifespan
│   ├── config.py                   # pydantic-settings: все env vars
│   ├── worker.py                   # ARQ worker entry point
│   │
│   ├── db/                         # [Спека: 08-api-backend.md]
│   │   ├── __init__.py
│   │   ├── engine.py               # async engine + session factory
│   │   ├── models.py               # ORM-модели
│   │   └── repositories.py         # CRUD-операции
│   │
│   ├── api/                        # [Спека: 08-api-backend.md]
│   │   ├── __init__.py
│   │   ├── router.py               # Главный роутер (монтирует sub-routers)
│   │   ├── predictions.py          # POST /api/v1/predictions, GET, SSE
│   │   ├── outlets.py              # GET /api/v1/outlets (autocomplete)
│   │   └── health.py               # GET /api/v1/health
│   │
│   ├── web/                        # [Спека: 09-frontend.md]
│   │   ├── __init__.py
│   │   ├── router.py               # HTML-роуты: /, /predict/{id}, /about
│   │   ├── templates/
│   │   │   ├── base.html           # Layout: nav, footer, Pico.css
│   │   │   ├── index.html          # Главная: форма ввода
│   │   │   ├── progress.html       # Прогресс: SSE, прогресс-бар
│   │   │   ├── results.html        # Результаты: карточки прогнозов
│   │   │   ├── about.html          # Методология
│   │   │   └── partials/
│   │   │       ├── headline_card.html
│   │   │       └── reasoning_block.html
│   │   └── static/
│   │       ├── css/custom.css
│   │       ├── js/progress.js      # SSE-клиент
│   │       ├── js/form.js          # Autocomplete, валидация
│   │       └── img/
│   │
│   ├── llm/                        # [Спека: 07-llm-layer.md]
│   │   ├── __init__.py
│   │   ├── providers.py            # OpenRouter + YandexGPT клиенты
│   │   ├── router.py               # Выбор модели по задаче + fallback
│   │   └── prompts/                # Шаблоны промптов
│   │       ├── __init__.py
│   │       ├── base.py             # Базовый класс промпта
│   │       ├── event_analysis.py
│   │       ├── delphi.py
│   │       ├── framing.py
│   │       ├── generation.py
│   │       └── quality.py
│   │
│   ├── agents/                     # [Спеки: 02, 03, 04, 05, 06]
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseAgent ABC, AgentResult
│   │   ├── orchestrator.py         # Главный пайплайн (9 стадий)
│   │   ├── registry.py             # Реестр агентов (DI)
│   │   │
│   │   ├── collectors/             # [Спека: 03-collectors.md]
│   │   │   ├── __init__.py
│   │   │   ├── news_scout.py       # Сбор новостей (RSS + web search)
│   │   │   ├── event_calendar.py   # Запланированные события
│   │   │   └── outlet_historian.py # Архив + стиль издания
│   │   │
│   │   ├── analysts/               # [Спека: 04-analysts.md]
│   │   │   ├── __init__.py
│   │   │   ├── event_trend.py      # Кластеризация → траектории
│   │   │   ├── geopolitical.py     # Геополитический контекст
│   │   │   ├── economic.py         # Экономический контекст
│   │   │   └── media.py            # Медиа-анализ издания
│   │   │
│   │   ├── forecasters/            # [Спека: 05-delphi-pipeline.md]
│   │   │   ├── __init__.py
│   │   │   ├── personas.py         # 5 экспертных персон
│   │   │   ├── delphi.py           # Оркестрация Дельфи (2 раунда)
│   │   │   ├── mediator.py         # Синтез расхождений
│   │   │   └── judge.py            # Финальный ранжинг + калибровка
│   │   │
│   │   └── generators/             # [Спека: 06-generators.md]
│   │       ├── __init__.py
│   │       ├── framing.py          # Анализ фрейминга издания
│   │       ├── style_replicator.py # Генерация заголовок + абзац
│   │       └── quality_gate.py     # Факт-чек, стиль, дедуп
│   │
│   ├── data_sources/               # [Спека: 01-data-sources.md]
│   │   ├── __init__.py
│   │   ├── rss.py                  # Async RSS fetcher/parser
│   │   ├── web_search.py           # Обёртки для поисковых API
│   │   ├── scraper.py              # Playwright-based scraper
│   │   └── outlets_catalog.py      # Каталог СМИ: RSS, метаданные
│   │
│   └── schemas/                    # Pydantic-модели (shared)
│       ├── __init__.py
│       ├── prediction.py           # PredictionRequest/Response
│       ├── headline.py             # HeadlinePrediction, Confidence
│       ├── pipeline.py             # PipelineContext, StageResult
│       ├── agent.py                # AgentResult, PersonaAssessment
│       ├── events.py               # SignalRecord, EventThread, Trajectory
│       └── progress.py             # SSE event schemas
│
├── tests/
│   ├── conftest.py
│   ├── test_agents/
│   ├── test_api/
│   ├── test_llm/
│   └── fixtures/
│
├── scripts/
│   ├── seed_outlets.py             # Наполнение каталога СМИ
│   ├── run_prediction.py           # CLI: запуск прогноза без веба
│   └── benchmark.py                # Замер стоимости/времени
│
└── docs/                           # Архитектурная документация
    ├── 00-overview.md              # ← ВЫ ЗДЕСЬ
    ├── 01-data-sources.md
    ├── 02-agents-core.md
    ├── 03-collectors.md
    ├── 04-analysts.md
    ├── 05-delphi-pipeline.md
    ├── 06-generators.md
    ├── 07-llm-layer.md
    ├── 08-api-backend.md
    ├── 09-frontend.md
    ├── 10-deployment.md
    └── prompts/
        ├── realist.md
        ├── geostrateg.md
        ├── economist.md
        ├── media-expert.md
        ├── devils-advocate.md
        ├── mediator.md
        └── judge.md
```

---

## Data Flow: полный пайплайн прогнозирования

### Вход

```
PredictionRequest {
    outlet: str          # "ТАСС", "BBC Russian", "Незыгарь"
    target_date: date    # 2026-04-02
}
```

### 9 стадий пайплайна

```
ВХОД ──► Stage 1: DATA COLLECTION (параллельно, ~2-5 мин)
         │
         ├── NewsScout ──► List[SignalRecord]
         │   • RSS-фиды (20-30 источников)
         │   • Web search (Exa/Jina API)
         │   • Результат: ~100-200 сигналов
         │
         ├── EventCalendar ──► List[ScheduledEvent]
         │   • Политические календари
         │   • Экономические релизы
         │   • LLM: "что запланировано на {target_date}?"
         │
         └── OutletHistorian ──► OutletProfile
             • Скрейпинг последних 30 дней публикаций
             • LLM-анализ стиля и редакционной позиции
             • 20-30 примеров заголовков

         │
         ▼
Stage 2: EVENT IDENTIFICATION (~1-2 мин)
         │
         └── EventTrendAnalyzer
             • Вход: SignalRecord[] + ScheduledEvent[]
             • Кластеризация сигналов в события (HDBSCAN на эмбеддингах)
             • Дедупликация
             • Ранжирование по значимости
             • Выход: top-20 EventThread[]

         │
         ▼
Stage 3: TRAJECTORY ANALYSIS (параллельно по событиям, ~2-3 мин)
         │
         └── Для каждого EventThread:
             • LLM: текущее состояние → моментум → 3 сценария
             • Матрица перекрёстных влияний (cross-impact)
             • Выход: EventTrajectory[] + CrossImpactMatrix

         │
         ▼
Stage 4: DELPHI ROUND 1 (5 агентов параллельно, ~3-5 мин)
         │
         ├── Реалист-аналитик ──► PersonaAssessment
         ├── Геополитический стратег ──► PersonaAssessment
         ├── Экономический аналитик ──► PersonaAssessment
         ├── Медиа-эксперт ──► PersonaAssessment
         └── Адвокат дьявола ──► PersonaAssessment + Challenges
         │
         │  Каждый агент получает: EventTrajectory[] + CrossImpactMatrix
         │  Каждый агент НЕ видит результаты других
         │  Каждый агент использует РАЗНУЮ LLM-модель

         │
         ▼
Stage 5: DELPHI ROUND 2 (~5-8 мин)
         │
         ├── 5a. Медиатор ──► MediatorSynthesis
         │   • Вход: 5 × PersonaAssessment
         │   • Определяет: консенсус, расхождения, пробелы
         │   • Формулирует ключевые вопросы для разрешения споров
         │
         ├── 5b. Агенты пересматривают (параллельно)
         │   • Каждый получает: свой R1 + MediatorSynthesis
         │   • Каждый НЕ получает: чужие R1 (анонимность Дельфи)
         │   • Выход: 5 × RevisedAssessment
         │
         └── 5c. (опционально) Supervisor Search
             • Если разброс > 0.25, поиск фактов для разрешения спора

         │
         ▼
Stage 6: CONSENSUS & SELECTION (~2-3 мин)
         │
         └── Судья (Judge)
             • Медианная агрегация вероятностей
             • Калибровка (Platt scaling, extremization)
             • headline_score = probability × newsworthiness × (1 - saturation)
             • Выход: top-7 RankedPrediction[] + wild cards

         │
         ▼
Stage 7: FRAMING ANALYSIS (параллельно по прогнозам, ~1-2 мин)
         │
         └── Для каждого RankedPrediction:
             • Вход: prediction + OutletProfile
             • LLM: "как {outlet} подаст это событие?"
             • Выход: FramingBrief (угол, тон, источники, пропуски)

         │
         ▼
Stage 8: STYLE-CONDITIONED GENERATION (параллельно, ~1-2 мин)
         │
         └── StyleReplicator
             • Вход: RankedPrediction + FramingBrief + OutletProfile
             • LLM: генерация 2-3 вариантов заголовка + первого абзаца
             • Стилевые примеры из OutletProfile (10 заголовков)
             • Выход: List[GeneratedHeadline] (2-3 варианта на прогноз)

         │
         ▼
Stage 9: QUALITY GATE (~1-2 мин)
         │
         └── QualityGate
             ├── 9a. Фактическая проверка (Claude Sonnet)
             │   • Противоречия с известными фактами?
             │   • Логические несоответствия?
             │   • Score 1-5
             │
             ├── 9b. Стилистическая проверка (YandexGPT)
             │   • Соответствие стилю издания?
             │   • Длина, тон, лексика?
             │   • Score 1-5
             │
             └── 9c. Дедупликация
                 • Нет ли повторов между прогнозами?
                 • Не предсказано ли уже опубликованное?

         │
         ▼
ВЫХОД ──► List[FinalPrediction]
```

### Выход

```
PredictionResponse {
    id: uuid
    outlet: str
    target_date: date
    status: "completed"
    duration_ms: int
    headlines: [
        {
            rank: 1
            headline: "Год после Liberation Day: как тарифы..."
            first_paragraph: "Ровно год назад президент Трамп..."
            confidence: 0.82
            confidence_label: "высокая"
            category: "экономика"
            reasoning: "Годовщина + отмена SCOTUS + текущие Section 122"
            evidence_chain: [
                {source: "AP", summary: "..."},
                {source: "CNBC", summary: "..."}
            ]
            agent_agreement: "consensus"  # 4 из 5 согласились
            dissenting_views: [
                {agent: "адвокат дьявола", view: "Война Ирана затмит тему тарифов"}
            ]
        },
        ...
    ]
}
```

---

## Бюджет на LLM (оценка за 1 прогноз)

| Стадия | Вызовов LLM | Модель | Стоимость |
|---|---|---|---|
| 1: Data Collection | ~5 (календарь + стиль) | GPT-4o-mini + Sonnet | $1.50 |
| 2: Event Identification | ~25 (кластеры) | GPT-4o-mini | $0.50 |
| 3: Trajectory | ~21 (20 событий + матрица) | Claude Sonnet | $3.00 |
| 4: Delphi R1 | 5 (по 1 на агента) | Mix | $8.00 |
| 5a: Mediator | 1 | Claude Opus | $2.00 |
| 5b: Delphi R2 | 5 | Mix | $8.00 |
| 6: Judge | 1 | Claude Opus | $2.00 |
| 7: Framing | ~7 | Claude Sonnet | $2.00 |
| 8: Generation | ~21 (7 × 3 варианта) | YandexGPT / Sonnet | $1.50 |
| 9: Quality Gate | ~14 (dual-model) | Sonnet + YandexGPT | $2.00 |
| **ИТОГО** | **~105** | | **~$30.50** |

---

## Переменные окружения (.env)

```env
# LLM Providers
OPENROUTER_API_KEY=sk-or-...
YANDEX_FOLDER_ID=...
YANDEX_API_KEY=...

# Model defaults (переопределяемые через UI/CLI)
DEFAULT_MODEL_CHEAP=openai/gpt-4o-mini
DEFAULT_MODEL_REASONING=anthropic/claude-sonnet-4
DEFAULT_MODEL_STRONG=anthropic/claude-opus-4
DEFAULT_MODEL_RUSSIAN=yandexgpt

# App
SECRET_KEY=...
DATABASE_URL=sqlite+aiosqlite:///data/foresighting.db
REDIS_URL=redis://redis:6379

# Pipeline tuning
DELPHI_ROUNDS=2
DELPHI_AGENTS=5
MAX_EVENT_THREADS=20
MAX_HEADLINES_PER_PREDICTION=7
QUALITY_GATE_MIN_SCORE=3

# External APIs (опционально)
EXA_API_KEY=...
JINA_API_KEY=...
```

---

## Навигация по спекам модулей

| Документ | Что описывает | Какие файлы реализует |
|---|---|---|
| [01-data-sources.md](01-data-sources.md) | RSS, web search, scraping, каталог СМИ | `src/data_sources/*` |
| [02-agents-core.md](02-agents-core.md) | BaseAgent, оркестратор, реестр, PipelineContext | `src/agents/base.py`, `orchestrator.py`, `registry.py` |
| [03-collectors.md](03-collectors.md) | NewsScout, EventCalendar, OutletHistorian | `src/agents/collectors/*` |
| [04-analysts.md](04-analysts.md) | EventTrend, Geopolitical, Economic, Media | `src/agents/analysts/*` |
| [05-delphi-pipeline.md](05-delphi-pipeline.md) | Персоны, раунды, медиатор, судья, калибровка | `src/agents/forecasters/*` |
| [06-generators.md](06-generators.md) | Framing, StyleReplicator, QualityGate | `src/agents/generators/*` |
| [07-llm-layer.md](07-llm-layer.md) | Провайдеры, роутинг, fallback, cost tracking | `src/llm/*` |
| [08-api-backend.md](08-api-backend.md) | REST API, SSE, БД-схема, ARQ tasks | `src/api/*`, `src/db/*`, `src/worker.py` |
| [09-frontend.md](09-frontend.md) | HTML-шаблоны, CSS, JS, UX-flow | `src/web/*` |
| [10-deployment.md](10-deployment.md) | Docker, nginx, VPS, SSL, мониторинг | `docker-compose.yml`, `Dockerfile`, `nginx/` |
| [prompts/*.md](prompts/) | Полные промпты для каждого агента | `src/llm/prompts/*` |

---

## Порядок реализации

1. **docs/** — архитектурные спеки (текущая фаза)
2. **src/schemas/** + **src/config.py** — модели данных и конфигурация
3. **src/llm/** — LLM-провайдеры (без них ничего не работает)
4. **src/agents/base.py** + **orchestrator.py** — скелет пайплайна
5. **src/agents/collectors/** — сбор данных
6. **src/agents/analysts/** — анализ
7. **src/agents/forecasters/** — Дельфи
8. **src/agents/generators/** — генерация
9. **src/data_sources/** — RSS, search, scraper
10. **src/api/** + **src/db/** — бэкенд
11. **src/web/** — фронтенд
12. **Docker + deploy** — деплой
