# База данных

## Архитектура

**Delphi Press** использует **SQLite** с асинхронным драйвером **aiosqlite** через **SQLAlchemy 2.0 async ORM**. База данных хранит полный жизненный цикл прогноза: от создания до завершения, включая все заголовки, шаги пайплайна, метрики LLM и каталог СМИ.

| Параметр | Значение |
|----------|----------|
| **СУБД** | SQLite 3 |
| **Драйвер** | aiosqlite (async) |
| **ORM** | SQLAlchemy 2.0 (Mapped style) |
| **Размещение** | `/app/data/delphi_press.db` |
| **Таблиц** | 8 |
| **Строк на prod** | ~100k (predictions) + миллионы (raw_articles) |

## Параметры подключения

### Dev-режим (local SQLite)

```python
# .env или src/config.py
DATABASE_URL=sqlite+aiosqlite:///data/delphi_press.db
```

!!! note "Запрет `check_same_thread`"
    Благодаря asyncio, SQLite работает в одном потоке, поэтому параметр `check_same_thread=False` безопасен. Это включено в `src/db/engine.py`.

### Prod-режим (Docker)

```yaml
# docker-compose.yml
services:
  app:
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////app/data/delphi_press.db
    volumes:
      - app_data:/app/data
```

База данных разделяется между контейнерами `app` и `worker` через виртуальный том.

## Инициализация

Таблицы создаются автоматически при запуске приложения:

```python
# src/main.py
async def lifespan(app: FastAPI):
    async with create_engine(settings) as engine:
        await init_db(engine)  # CREATE TABLE IF NOT EXISTS
        yield
        await dispose_engine(engine)
```

!!! warning "Миграции"
    Delphi Press **не использует Alembic** или другую систему миграций. Все изменения схемы делаются напрямую через модели SQLAlchemy. Для production: перед изменением модели выполнить `ALTER TABLE` вручную или использовать инструмент миграции.

## Таблицы и связи

### `predictions` — Основная таблица

Запись о прогнозе — главная сущность системы.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `VARCHAR(36)` | PRIMARY KEY | UUID прогноза |
| `outlet_name` | `VARCHAR(200)` | NOT NULL | Исходное имя издания (как ввёл пользователь) |
| `outlet_normalized` | `VARCHAR(200)` | NOT NULL, INDEX | Нормализованное имя для поиска |
| `target_date` | `DATE` | NOT NULL, INDEX | Дата прогноза |
| `status` | `ENUM` | NOT NULL, INDEX | `pending` \| `collecting` \| `analyzing` \| `forecasting` \| `generating` \| `completed` \| `failed` |
| `created_at` | `DATETIME` | NOT NULL, INDEX | Timestamp создания (UTC) |
| `completed_at` | `DATETIME` | nullable | Timestamp завершения |
| `total_duration_ms` | `INTEGER` | nullable | Время выполнения в ms |
| `total_llm_cost_usd` | `FLOAT` | nullable | Сумма cost всех LLM-вызовов |
| `error_message` | `TEXT` | nullable | Стек ошибки при FAILED |
| `pipeline_config` | `JSON` | nullable | Сохранённая конфиг (дельфи-раунды, агенты, пресет) |
| `predicted_timeline` | `JSON` | nullable | Отформатированная лента событий (Stage 3) |
| `delphi_summary` | `JSON` | nullable | Итоговые прогнозы (Stage 5 consensus) |
| `user_id` | `VARCHAR(36)` | FK users, nullable | Владелец прогноза (или NULL для public/batch) |
| `preset` | `VARCHAR(20)` | default='full' | Пресет: `light` \| `full` |
| `is_public` | `BOOLEAN` | default=0 | Видна ли витрина (Web UI) |

**Индексы:**
- `(status, created_at)` — для быстрого получения последних прогнозов по статусу
- `(outlet_normalized, target_date)` — для дедупликации (предотвратить двойные прогнозы)

**Связи:**
```
predictions ──→ users (1 user owns many predictions)
predictions ──→ headlines (1 prediction has many headlines, cascade delete)
predictions ──→ pipeline_steps (1 prediction has many steps, cascade delete)
```

### `headlines` — Спрогнозированные заголовки

Таблица хранит массив (обычно 5-10) заголовков на один прогноз, отсортированные по рангу.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID строки |
| `prediction_id` | `VARCHAR(36)` | FK predictions, INDEX | Ссылка на родительский прогноз |
| `rank` | `INTEGER` | NOT NULL | Позиция (1, 2, 3…) для сортировки |
| `headline_text` | `TEXT` | NOT NULL | Сам заголовок (на языке СМИ) |
| `first_paragraph` | `TEXT` | NOT NULL, default='' | Первый абзац (для соцсетей) |
| `confidence` | `FLOAT` | NOT NULL | Уверенность [0.0…1.0] из Stage 5 |
| `confidence_label` | `VARCHAR(20)` | NOT NULL, default='' | Категория: `very_high` \| `high` \| `medium` \| `low` |
| `category` | `VARCHAR(50)` | NOT NULL, default='' | Рубрика: `politics`, `economy`, `crime` и т. д. |
| `reasoning` | `TEXT` | NOT NULL, default='' | Объяснение почему этот заголовок |
| `evidence_chain` | `JSON` | nullable | Array фактов (из Stage 1 + Stage 3) |
| `dissenting_views` | `JSON` | nullable | Array контраргументов (из Дельфи R2) |
| `agent_agreement` | `VARCHAR(20)` | NOT NULL, default='' | Consensus score: `strong` \| `moderate` \| `weak` |
| `created_at` | `DATETIME` | NOT NULL | Timestamp создания |

**Индексы:**
- `(prediction_id, rank)` — быстрое получение headlines в порядке сортировки

**Примечание:**
Заголовки загружаются **eagerly** (lazy='selectin') при загрузке Prediction, благодаря чему один запрос возвращает все связанные данные.

### `pipeline_steps` — Метрики агентов

Логирует выполнение каждого агента с подробностью по tokens, cost и ошибкам.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID |
| `prediction_id` | `VARCHAR(36)` | FK predictions, INDEX | Ссылка на прогноз |
| `agent_name` | `VARCHAR(50)` | NOT NULL | Имя агента: `NewsCollector`, `ForesightCollector`, `TrajectoryAnalyst` и т. д. |
| `step_order` | `INTEGER` | NOT NULL | Порядок выполнения (1…18) |
| `status` | `ENUM` | NOT NULL | `running` \| `completed` \| `failed` \| `skipped` |
| `started_at` | `DATETIME` | nullable | Когда начало |
| `completed_at` | `DATETIME` | nullable | Когда закончилось |
| `duration_ms` | `INTEGER` | nullable | Время выполнения агента в ms |
| `llm_model_used` | `VARCHAR(100)` | nullable | Модель: `anthropic/claude-opus-4.6` или fallback |
| `llm_tokens_in` | `INTEGER` | default=0 | Входные токены (от пользователя) |
| `llm_tokens_out` | `INTEGER` | default=0 | Выходные токены (от LLM) |
| `llm_cost_usd` | `FLOAT` | default=0.0 | Стоимость в USD (по ценам OpenRouter) |
| `input_summary` | `TEXT` | nullable | Краткое описание входа (для отладки) |
| `output_summary` | `TEXT` | nullable | Краткое описание выхода |
| `output_data` | `JSON` | nullable | Структурированный выход агента (Pydantic → JSON) |
| `error_message` | `TEXT` | nullable | Исключение / traceback при FAILED |

**Индексы:**
- `(prediction_id, step_order)` — получение шагов в порядке выполнения
- `(agent_name)` — анализ производительности по конкретному агенту

**Примечание:**
Загружается **eagerly** при fetch Prediction → `await session.refresh(pred, ["pipeline_steps"])`

### `outlets` — Справочник СМИ

Каталог известных изданий с метаданными (язык, политические взгляды, примеры заголовков).

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID |
| `name` | `VARCHAR(200)` | NOT NULL | Полное имя издания (русское) |
| `normalized_name` | `VARCHAR(200)` | NOT NULL, UNIQUE, INDEX | Нормализованное (для поиска и сравнения) |
| `country` | `VARCHAR(5)` | NOT NULL, default='' | ISO-3166 код: `RU`, `UA`, `BY` и т. д. |
| `language` | `VARCHAR(5)` | NOT NULL, default='' | ISO-639-1: `ru`, `uk`, `en` и т. д. |
| `political_leaning` | `VARCHAR(30)` | NOT NULL, default='' | `centrist` \| `left` \| `right` \| `progovt` \| `independent` |
| `rss_feeds` | `JSON` | nullable | Array объектов `{url, category}` для RSS-сбора |
| `website_url` | `VARCHAR(500)` | NOT NULL, default='' | Основной URL сайта |
| `style_description` | `TEXT` | NOT NULL, default='' | Описание стиля письма для промптов агентов |
| `editorial_focus` | `JSON` | nullable | Array рубрик: `["politics", "economy", "crime"]` |
| `sample_headlines` | `JSON` | nullable | Array реальных заголовков (для few-shot learning) |
| `last_analyzed_at` | `DATETIME` | nullable | Когда последний раз агент анализировал выход |
| `created_at` | `DATETIME` | NOT NULL | Timestamp создания |

**Индексы:**
- `(country)` — фильтр по стране
- `(language)` — фильтр по языку
- `(normalized_name)` — поиск по имени (unique constraint)

**Заполнение:**
Таблица предзаполняется при инициализации БД. Может обновляться через OutletResolver (динамическое разрешение новых изданий через Wikidata + RSS Discovery).

### `users` — Пользователи Web UI

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `VARCHAR(36)` | PRIMARY KEY | UUID пользователя |
| `email` | `VARCHAR(255)` | UNIQUE, NOT NULL, INDEX | Email для входа |
| `hashed_password` | `VARCHAR(255)` | NOT NULL | bcrypt хеш пароля |
| `is_active` | `BOOLEAN` | default=True | Заблокирован ли пользователь |
| `created_at` | `DATETIME` | NOT NULL | Дата регистрации |

**Связи:**
```
users ──→ user_api_keys (1 user has many API keys, cascade delete)
users ──→ predictions (1 user has many predictions)
```

### `user_api_keys` — Зашифрованные API-ключи

Хранит API-ключи пользователей для LLM-провайдеров (OpenRouter, Anthropic API и т. д.), зашифрованные с помощью **Fernet** из `cryptography`.

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID |
| `user_id` | `VARCHAR(36)` | FK users, INDEX | Владелец ключа |
| `provider` | `VARCHAR(50)` | NOT NULL | Провайдер: `openrouter`, `anthropic`, `openai` и т. д. |
| `encrypted_key` | `TEXT` | NOT NULL | Зашифрованный API-ключ (не расшифровывается в БД) |
| `label` | `VARCHAR(100)` | default='' | Человеческое описание (напр. "My Anthropic API key") |
| `is_active` | `BOOLEAN` | default=True | Отозван ли ключ |
| `created_at` | `DATETIME` | NOT NULL | Дата добавления |
| `last_used_at` | `DATETIME` | nullable | Последнее использование |

**Constraints:**
- `UNIQUE(user_id, provider)` — один ключ на провайдера на пользователя

**Безопасность:**
Ключи **никогда** не выгружаются в frontend. Используются только на backend для вызовов OpenRouter API.

### `feed_sources` — RSS-фиды

Управляет RSS-подписками для каждого издания (для Stage 1: NewsCollector).

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID |
| `outlet_id` | `INTEGER` | FK outlets, INDEX | Издание, для которого этот фид |
| `rss_url` | `VARCHAR(500)` | NOT NULL, UNIQUE | URL RSS-ленты |
| `etag` | `VARCHAR(200)` | nullable | ETag для HTTP conditional requests (сэкономить bandwidth) |
| `last_modified` | `VARCHAR(200)` | nullable | Last-Modified header (для повторных запросов) |
| `last_fetched` | `DATETIME` | nullable | Когда последний раз fetchили |
| `error_count` | `INTEGER` | default=0 | Счётчик последовательных ошибок |
| `is_active` | `BOOLEAN` | default=True | Деактивирован ли (circuit breaker после 5 ошибок) |
| `created_at` | `DATETIME` | NOT NULL | Дата добавления |

**Circuit Breaker:**
Если фид возвращает ошибку 5 раз подряд, он автоматически деактивируется (`is_active=False`). Может быть переактивирован вручную или через endpoint API.

**Связи:**
```
feed_sources ──→ outlets (many feeds per outlet, cascade delete)
```

### `raw_articles` — Сырые статьи

Хранит все собранные статьи из RSS/web search/скрейпинга. Используется Stage 1 (Collection) и Stage 3 (Analysis).

| Колонка | Тип | Constraints | Описание |
|---------|-----|-------------|---------|
| `id` | `INTEGER` | PRIMARY KEY, autoincrement | Внутренний ID |
| `url` | `VARCHAR(2000)` | NOT NULL, UNIQUE | Постоянная ссылка на статью (дедупликация) |
| `title` | `VARCHAR(500)` | NOT NULL | Заголовок оригинальной статьи |
| `summary` | `TEXT` | NOT NULL, default='' | Краткое описание (первые 100 слов) |
| `cleaned_text` | `TEXT` | nullable | Извлечённый основной текст (после дочистки) |
| `published_at` | `DATETIME` | nullable, INDEX | Дата публикации (может быть NULL если не найдена) |
| `source_outlet` | `VARCHAR(200)` | NOT NULL, INDEX | Издание-источник |
| `language` | `VARCHAR(5)` | NOT NULL, default='und' | ISO-639-1 язык контента |
| `categories` | `JSON` | nullable | Array тегов: `["politics", "economics"]` |
| `fetch_method` | `ENUM` | NOT NULL | Откуда взята: `rss` \| `search` \| `scrape` |
| `created_at` | `DATETIME` | NOT NULL, INDEX | Timestamp сбора (UTC) |

**Индексы:**
- `(source_outlet, published_at)` — быстрое получение статей по изданию за дату
- `(published_at)` — для retention cleanup
- `(created_at)` — для очистки старых записей

**Retention Policy:**
Статьи старше 30 дней удаляются автоматически (cron job). Можно настроить через:
```python
# src/crons/cleanup.py
await raw_article_repo.delete_older_than(days=30)
```

!!! warning "Размер таблицы"
    raw_articles может вырасти до миллионов записей. Рекомендуется регулярно вызывать cleanup и индексировать `(source_outlet, published_at)` для fast queries.

## Паттерны работы

### Инициализация сессии

```python
from src.db.engine import get_session, create_session_factory

# В endpoint
async def predict(request: PredictionRequest, session: AsyncSession = Depends(get_session)):
    # session — готовая сессия с autocommit=False
    prediction = await PredictionRepository(session).create(...)
    await session.commit()
```

### CRUD через репозитории

Вся логика работы с БД инкапсулирована в репозиториях (`src/db/repositories.py`):

```python
# Создание прогноза
pred_repo = PredictionRepository(session)
prediction = await pred_repo.create(
    id=str(uuid.uuid4()),
    outlet_name="ТАСС",
    outlet_normalized="tass",
    target_date=date(2026, 4, 6),
)

# Обновление статуса
await pred_repo.update_status(
    prediction.id,
    PredictionStatus.COMPLETED,
    total_duration_ms=12000,
    total_llm_cost_usd=5.32,
)

# Сохранение заголовков
headlines_data = [
    {
        "rank": 1,
        "headline_text": "...",
        "confidence": 0.95,
        ...
    }
]
await pred_repo.save_headlines(prediction.id, headlines_data)

# Получение последних прогнозов
predictions, total = await pred_repo.get_recent(limit=20, offset=0)
```

### Транзакции

```python
async with session.begin():  # begin() автоматически commits при выходе
    await pred_repo.create(...)
    await pred_repo.save_headlines(...)
    # Если выпадет ошибка → rollback; если успешно → commit
```

### Асинхронный паттерн

Все операции асинхронны:

```python
# ✓ Правильно
result = await session.execute(select(Prediction).where(...))
predictions = result.scalars().all()

# ✗ Неправильно (блокирует)
predictions = session.query(Prediction).all()
```

## Производительность

### Lazy loading и selectin

Все relationships загружаются с `lazy="selectin"` для избежания N+1 queries:

```python
# Вместо:
prediction = await session.get(Prediction, prediction_id)
# У нас:
prediction.headlines  # ← уже загружены в selectin
```

### Индексирование

Основные индексы уже добавлены на часто используемые колонки:

```python
# Автоматически используются:
ix_predictions_status_created     # get_recent()
ix_predictions_outlet_date        # дедупликация
ix_headlines_prediction_rank      # сортировка по rank
ix_steps_prediction_order         # логирование агентов
ix_raw_articles_outlet_published  # сбор статей по дате
```

### Размер БД

На текущем production (~100k predictions):

| Таблица | Примерный размер |
|---------|-----------------|
| predictions | ~50 MB |
| headlines | ~150 MB |
| pipeline_steps | ~200 MB |
| raw_articles | ~2-3 GB (после cleanup) |
| **Итого** | ~2.4 GB |

!!! note "Ограничение памяти сервера"
    На сервере с 8 GB RAM рекомендуется держать raw_articles ≤ 2 GB. При выходе за лимит включить более агрессивный cleanup (например, 14 дней вместо 30).

## Миграция и бэкап

### Локальный бэкап

```bash
# Сохранить текущую БД
cp /app/data/delphi_press.db /backup/delphi_press_$(date +%Y%m%d).db
```

### Экспорт в CSV (для анализа)

```python
# scripts/export_predictions.py
import pandas as pd
from sqlalchemy import select
from src.db.models import Prediction, Headline

async def export():
    async with get_session(session_factory) as session:
        predictions = await session.execute(select(Prediction))
        df = pd.read_sql(select(Prediction), session.sync_session)
        df.to_csv("predictions.csv", index=False)
```

### Переход на PostgreSQL (future)

Если понадобится масштабирование:

```python
# Изменить DATABASE_URL в .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/delphi_press

# Установить asyncpg
pip install asyncpg
```

Все модели SQLAlchemy совместимы с PostgreSQL без изменений.

## Отладка

### Включить SQL logging

```python
# .env
DEBUG=true

# Тогда в логах появятся все SQL-запросы (медленно!)
```

### Инспектировать БД напрямую

```bash
# Подключиться к SQLite
sqlite3 /app/data/delphi_press.db

# Получить список таблиц
.tables

# Схему таблицы
.schema predictions

# Запрос
SELECT COUNT(*) FROM predictions WHERE status='completed';
```

### Проверить индексы

```sql
-- Все индексы
SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index';

-- Использован ли индекс
EXPLAIN QUERY PLAN
SELECT * FROM predictions WHERE status='completed' ORDER BY created_at DESC;
```

## Контракт с агентами

Все агенты пайплайна возвращают данные в строго типизированных Pydantic-моделях (из `src/schemas/`), которые репозитории сохраняют в БД:

```
Agent Output (Pydantic) ──→ Repository.save_*() ──→ ORM Model ──→ SQL INSERT
```

Например:

```python
# Stage 4: DelphoiPersonaForecast выдаёт GeneratedForecast
forecast: GeneratedForecast = await delphi_agent.run(...)

# Оркестратор сохраняет
step = await pipeline_step_repo.save_pipeline_step(
    prediction_id=pred.id,
    step_data={
        "agent_name": "DelphoiPersona_1",
        "output_data": forecast.model_dump(),  # Pydantic → dict
        ...
    }
)
# output_data сохраняется как JSON в pipeline_steps.output_data
```

## Ссылки на спеку

Полное определение ORM-моделей: **`src/db/models.py`**

Реализация репозиториев: **`src/db/repositories.py`**

Инициализация engine: **`src/db/engine.py`**

Обзор архитектуры: **`docs/08-api-backend.md`** (§2-4)
