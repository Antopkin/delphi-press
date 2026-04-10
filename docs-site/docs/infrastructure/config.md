# Конфигурация приложения

Delphi Press управляется единой системой конфигурации, объединяющей переменные окружения, файлы настроек и параметры пресетов. Все значения загружаются автоматически при старте приложения.

## Загрузка конфигурации

Приложение использует Pydantic Settings для управления конфигурацией с автоматической загрузкой из переменных окружения и файла `.env`.

**Приоритет источников (от высшего к низшему):**

1. Переменные окружения системы (`export SECRET_KEY=...`)
2. Файл `.env` в корне проекта
3. Значения по умолчанию в коде

```bash
# Загрузить конфигурацию
cp .env.example .env
# Отредактировать .env с нужными значениями
uv run python -c "from src.config import get_settings; print(get_settings().openrouter_api_key)"
```

!!! note "Кэширование"
    Конфигурация кэшируется в памяти процесса через `@lru_cache`. Для сброса в тестах: `get_settings.cache_clear()`.

## Категории переменных окружения

### Приложение

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `SECRET_KEY` | строка | `dev-insecure-key-change-in-production-32ch` | В production | Секретный ключ для подписи сессий и CSRF-токенов. Минимум 32 символа. Генерировать: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DEBUG` | булевый | `false` | Опционально | Включить режим отладки (Swagger UI, трассировки стека). **Никогда не включать в production!** |
| `LOG_LEVEL` | строка | `INFO` | Опционально | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `APP_NAME` | строка | `Delphi Press` | Опционально | Название приложения |
| `APP_VERSION` | строка | `0.9.5` | Опционально | Версия приложения |

### Данные и хранилище

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `DATABASE_URL` | строка | `sqlite+aiosqlite:///data/delphi_press.db` | Опционально | Async SQLAlchemy connection string. Поддерживаются: `sqlite+aiosqlite` (dev), `postgresql+asyncpg` (production). **Для SQLite: WORKERS должен быть 1** |
| `DATA_DIR` | путь | `data` | Опционально | Директория для SQLite БД и кэшей |
| `STATIC_DIR` | путь | `src/web/static` | Опционально | Директория статических файлов (CSS, JS, изображения) |
| `TEMPLATES_DIR` | путь | `src/web/templates` | Опционально | Директория шаблонов Jinja2 |

### Redis и очередь задач

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `REDIS_URL` | строка | `redis://redis:6379` | Опционально | URL подключения к Redis. Формат: `redis://[:password]@host:port/db`. В Docker Compose переполняется из `REDIS_PASSWORD` |
| `REDIS_PASSWORD` | строка | `changeme` | Опционально | Пароль для Redis (используется Docker Compose) |
| `ARQ_MAX_JOBS` | целое | `10` | Опционально | Максимум параллельных задач в очереди (1-50) |
| `ARQ_JOB_TIMEOUT` | целое (сек) | `5400` | Опционально | Таймаут на выполнение одного прогноза (300-7200 сек = 5-120 мин). Default = 1.5 часа |
| `ARQ_CONCURRENCY` | целое | `2` | Опционально | Число воркеров для обработки задач (1-4) |

!!! warning "Таймауты"
    Для полного прогноза (20 event threads, 2 rounds) нужно минимум 30 минут (`ARQ_JOB_TIMEOUT=1800`). При меньших значениях задачи будут автоматически убиваться.

### LLM и провайдеры

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `OPENROUTER_API_KEY` | строка | `` | Опционально | API ключ OpenRouter (sk-or-...). Если не установлен, пользователи должны предоставить свои. Используется как fallback для Web UI |
| `OPENROUTER_BASE_URL` | строка | `https://openrouter.ai/api/v1` | Опционально | Базовый URL для API OpenRouter (обычно не менять) |
| `DEFAULT_MODEL_CHEAP` | строка | `google/gemini-3.1-flash-lite-preview` | Опционально | Дешёвая модель для быстрого анализа |
| `DEFAULT_MODEL_REASONING` | строка | `anthropic/claude-opus-4.6` | Опционально | Модель для сложного анализа (reasoning) |
| `DEFAULT_MODEL_STRONG` | строка | `anthropic/claude-opus-4.6` | Опционально | Мощная модель для финальных решений |
| `LLM_MAX_RETRIES` | целое | `3` | Опционально | Число попыток повтора при ошибке LLM (1-10) |
| `LLM_RETRY_BASE_DELAY` | число (сек) | `1.0` | Опционально | Базовая задержка перед повтором (exponential backoff) |
| `LLM_RETRY_MAX_DELAY` | число (сек) | `30.0` | Опционально | Максимальная задержка перед повтором |
| `LLM_TIMEOUT_SECONDS` | число (сек) | `120.0` | Опционально | Таймаут для одного LLM запроса |
| `MAX_BUDGET_USD` | число | `50.0` | Опционально | Максимальный бюджет в USD на одноходовый прогноз. Остановит pipeline если превышен |
| `BUDGET_WARNING_THRESHOLD` | число | `0.8` | Опционально | Процент бюджета (0.8 = 80%), при достижении выводится warning |

### Pipeline и параметры алгоритма

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `DELPHI_ROUNDS` | целое | `2` | Опционально | Число раундов Дельфи (1-3). Больше = лучше консенсус, но дороже |
| `DELPHI_AGENTS` | целое | `5` | Опционально | Число персон-агентов в Дельфи (3-7) |
| `MAX_EVENT_THREADS` | целое | `20` | Опционально | Максимум параллельных цепочек событий (5-50) |
| `MAX_HEADLINES_PER_PREDICTION` | целое | `7` | Опционально | Максимум заголовков в выходе (3-15) |
| `QUALITY_GATE_MIN_SCORE` | целое | `3` | Опционально | Минимальный скор качества для фильтрации (1-5) |

!!! info "Pipeline tuning"
    Все параметры pipeline можно переопределить через пресеты (см. раздел "Пресеты" ниже). При использовании Web UI параметры берутся из пресета, выбранного пользователем.

### Внешние API (опциональные)

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `EXA_API_KEY` | строка | `` | Опционально | API ключ Exa.ai для поиска источников (graceful degradation, если не установлен) |
| `JINA_API_KEY` | строка | `` | Опционально | API ключ Jina для парсинга веб-страниц (graceful degradation) |
| `METACULUS_TOKEN` | строка | `` | Опционально | Токен API Metaculus для получения исторических прогнозов. Свободный уровень от https://www.metaculus.com/aib/ |
| `METACULUS_TOURNAMENTS` | строка | `32977` | Опционально | Comma-separated ID турниров Metaculus. **32977** = bot testing (~50 Q), **32979** = bot benchmarking (~500 Q, требует BENCHMARKING tier) |

### Сервер и сетка

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `HOST` | строка | `0.0.0.0` | Опционально | IP адрес для привязки (0.0.0.0 = слушать на всех интерфейсах) |
| `PORT` | целое | `8000` | Опционально | Порт uvicorn (1-65535) |
| `WORKERS` | целое | `1` | Опционально | Число worker-процессов uvicorn. **Для SQLite: всегда 1!** Для PostgreSQL: до 4 |
| `CORS_ORIGINS` | JSON list | `["http://localhost:8000"]` | Опционально | Разрешённые CORS origins (JSON array). В production установить явно: `'["https://yourdomain.com"]'` |

!!! danger "CORS и production"
    По умолчанию CORS разрешены только для localhost. В production явно установить домены. **`["*"]` запрещён в production!**

### Аутентификация и безопасность

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `FERNET_KEY` | строка | `3FsRWU3nhSsWfUlLDxtlREMWWZvO0a8PPlZi85leT-o=` | В production | Ключ шифрования Fernet для API-ключей пользователей (base64, 32 байта). Генерировать: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `JWT_EXPIRE_DAYS` | целое | `7` | Опционально | Срок действия JWT токена (1-365 дней) |
| `JWT_ALGORITHM` | строка | `HS256` | Опционально | Алгоритм подписи JWT (обычно не менять) |

### Inverse Problem (опционально)

| Переменная | Тип | По умолчанию | Обязательная | Описание |
|---|---|---|---|---|
| `INVERSE_PROFILES_PATH` | путь | `` | Опционально | Путь к `bettor_profiles.parquet` (построен `scripts/build_bettor_profiles.py`). Если не установлен, /markets dashboard будет пуст |
| `INVERSE_TRADES_PATH` | путь | `` | Опционально | Путь к CSV-файлу с историческими сделками для обогащения профилей |

## Пресеты

Пресеты — это предконфигурированные наборы параметров для различных сценариев использования. Определены в `src/config.py` в словаре `PRESETS`.

### Light (быстрый, дешёвый)

```json
{
  "name": "light",
  "label": "Light",
  "description": "Быстрый прогноз на базе Gemini Flash",
  "estimated_cost_usd": 1.0,
  "model": "google/gemini-2.5-flash",
  "max_event_threads": 5,
  "delphi_rounds": 1,
  "max_headlines": 5,
  "quality_gate_min_score": 2
}
```

**Используется для:**

- Тестирования (smoke tests)
- Демонстраций с ограниченным бюджетом
- Быстрой проверки (~2 мин, ~$1)

### Full (полный, качественный)

```json
{
  "name": "full",
  "label": "Full",
  "description": "Максимальная глубина на Claude Opus",
  "estimated_cost_usd": 15.0,
  "model": "anthropic/claude-opus-4.6",
  "max_event_threads": 20,
  "delphi_rounds": 2,
  "max_headlines": 10,
  "quality_gate_min_score": 4
}
```

**Используется для:**

- Production прогнозов
- Максимальной точности
- Полного Дельфи цикла (~20 мин, ~$15)

### Использование пресетов

В Web UI пользователь выбирает пресет при создании прогноза. Параметры пресета переопределяют значения из `.env`.

```python
from src.config import get_preset

preset = get_preset("light")
print(preset.model)              # "google/gemini-2.5-flash"
print(preset.estimated_cost_usd) # 1.0
print(preset.delphi_rounds)      # 1
```

## Инициализация приложения

### Lifespan (startup/shutdown)

FastAPI приложение использует context manager `lifespan` для управления ресурсами при старте и остановке.

**При старте (`lifespan` entry):**

1. **Логирование** — инициализируется логгер на основе `LOG_LEVEL`
2. **База данных** — создаётся async SQLAlchemy engine, инициализируются таблицы
3. **Redis** — устанавливается соединение для pub/sub и ARQ
4. **ARQ pool** — создается пул воркеров для фоновых задач
5. **KeyVault** — инициализируется шифрование ключей на основе `FERNET_KEY`
6. **Jinja2 globals** — устанавливается версия приложения для cache-busting
7. **Bettor profiles** — загружаются профили для dashboard (опционально)

```python
# Доступ в обработчиках маршрутов
from fastapi import Request

@app.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    engine = request.app.state.engine
    redis = request.app.state.redis
    arq_pool = request.app.state.arq_pool
    key_vault = request.app.state.key_vault
    market_service = request.app.state.market_service
```

**При остановке (`lifespan` exit):**

1. Закрытие ARQ пула
2. Закрытие Redis соединения
3. Закрытие database engine
4. Логирование graceful shutdown

### Валидация конфигурации

При загрузке конфигурации выполняются проверки:

**Обязательные поля для production (`DEBUG=False` и `DELPHI_PRODUCTION=1`):**

- `SECRET_KEY` не должна быть dev-значением (`dev-insecure-key-change-in-production-32ch`)
- `FERNET_KEY` не должна быть dev-значением
- `CORS_ORIGINS` не должна быть `["*"]`

```python
@model_validator(mode="after")
def _reject_insecure_defaults_in_production(self) -> Settings:
    if self.debug or not os.environ.get("DELPHI_PRODUCTION"):
        return self
    if self.secret_key == self._INSECURE_SECRET_KEY:
        raise ValueError("SECRET_KEY is set to the insecure dev default...")
    # ... дальше проверки FERNET_KEY и CORS_ORIGINS
```

**Валидация форматов:**

- `LOG_LEVEL` — только из набора {DEBUG, INFO, WARNING, ERROR, CRITICAL}
- `DATABASE_URL` — должна начинаться с `sqlite+aiosqlite` или `postgresql+asyncpg`

## Docker Compose конфигурация

При деплое через Docker Compose переменные окружения заполняются из `.env` файла и переопределяют дефолты в коде.

### Redis

```yaml
redis:
  image: redis:7.4-alpine
  command: >
    redis-server
    --requirepass ${REDIS_PASSWORD:-changeme}    # Пароль из .env
    --appendonly yes
    --maxmemory 256mb
```

**Переменные:**

- `REDIS_PASSWORD` — пароль доступа (генерируется в .env)

**Лимиты ресурсов:**

- CPU: 0.5 cores
- RAM: 384 MB

### App (FastAPI)

```yaml
app:
  environment:
    - REDIS_URL=redis://:${REDIS_PASSWORD:-changeme}@redis:6379/0
    - DELPHI_PRODUCTION=1  # Включает валидацию секретов
  volumes:
    - sqlite_data:/app/data            # Директория для БД
    - delphi_inverse:/app/data/inverse # Профили бетторов
  depends_on:
    redis:
      condition: service_healthy
```

**Лимиты ресурсов:**

- CPU: 1.5 cores (20% от 8 vCPU сервера)
- RAM: **1024 MB** (было 768 MB до 2026-04-09)

!!! info "Почему 1024M при ~250 MiB usage"
    До 2026-04-10 app-контейнер потреблял ~928 MiB (90.6% от лимита 1024M)
    из-за загрузки 348K полных `BettorProfile` Pydantic-объектов (~500 MiB).
    Оптимизация `CompactProfileStore` (slots dataclass, 3 поля вместо 10,
    pyarrow column projection) снизила потребление до ~250 MiB.
    Лимит 1024M сохранён как generous headroom (~750 MiB запаса).

    | Контейнер | Лимит | Наблюдаемый usage |
    |---|---|---|
    | `delphi-press-app` | 1024 MB | ~250 MiB (после CompactProfileStore) |
    | `delphi-press-worker` | 512 MB | ~90 MiB |
    | `delphi-press-redis` | 384 MB | ~10 MiB |
    | `delphi-press-nginx` | 128 MB | ~8 MiB |
    | `outline-moskino` | 1536 MB | ~450 MiB |
    | `outline-moskino-postgres` | 768 MB | ~80 MiB |
    | `outline-moskino-redis` | 256 MB | ~10 MiB |
    | `faun-cloud-1` | 256 MB | ~70 MiB |
    | `faun-edge-1` | 256 MB | ~100 MiB |
    | `faun-lora_gateway-1` | 128 MB | ~30 MiB |
    | `afisha-bot-bot-1` | 256 MB | ~60 MiB |
    | `afisha-bot-parser-1` | 256 MB | ~70 MiB |
    | **Суммарный лимит** | **~5.8 GiB** | **~1.3 GiB** |

    Шестой-седьмой GiB RAM остаётся системе и file-cache.

**Health check:**
```bash
curl -f http://localhost:8000/api/v1/health
```

### Worker (ARQ)

```yaml
worker:
  command: ["arq", "src.worker.WorkerSettings"]
  environment:
    - REDIS_URL=redis://:${REDIS_PASSWORD:-changeme}@redis:6379/0
    - DELPHI_PRODUCTION=1
  volumes:
    - sqlite_data:/app/data
    - delphi_inverse:/app/data/inverse
```

**Лимиты ресурсов:**

- CPU: 1.0 core
- RAM: 512 MB

### Nginx (reverse proxy)

```yaml
nginx:
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro  # TLS сертификаты
    - ./src/web/static:/var/www/static:ro
    - docs_data:/var/www/docs:ro
```

**Лимиты ресурсов:**

- CPU: 0.5 cores
- RAM: 128 MB

## Примеры конфигурации

### Development локально

```bash
# .env для dev
SECRET_KEY=dev-insecure-key-change-in-production-32ch
DEBUG=true
LOG_LEVEL=DEBUG
DATABASE_URL=sqlite+aiosqlite:///data/delphi_press.db
REDIS_URL=redis://localhost:6379
OPENROUTER_API_KEY=sk-or-...
CORS_ORIGINS=["http://localhost:8000", "http://localhost:3000"]
```

### Production на VPS

```bash
# .env для production
SECRET_KEY=<сгенерировано: python -c "import secrets; print(secrets.token_urlsafe(48))">
DEBUG=false
LOG_LEVEL=WARNING
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/delphi_press
REDIS_PASSWORD=<strong random password>
FERNET_KEY=<сгенерировано: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
OPENROUTER_API_KEY=sk-or-...
CORS_ORIGINS=["https://delphi.example.com"]
DELPHI_PRODUCTION=1  # Включает валидацию секретов
JWT_EXPIRE_DAYS=7
ARQ_JOB_TIMEOUT=1800
MAX_BUDGET_USD=50.0
```

Запуск:

```bash
docker compose up -d
docker compose logs -f app
```

### E2E сухой запуск (без инфраструктуры)

```bash
# Быстрый smoke test (Gemini, 5 threads, ~$0.25)
OPENROUTER_API_KEY=sk-or-... uv run python scripts/dry_run.py \
  --outlet "ТАСС" \
  --model google/gemini-2.5-flash \
  --event-threads 5

# Production-like (Opus, 20 threads, ~$5-15)
OPENROUTER_API_KEY=sk-or-... uv run python scripts/dry_run.py \
  --outlet "ТАСС" \
  --model anthropic/claude-opus-4.6 \
  --event-threads 20
```

Скрипт вызывает `Orchestrator.run_prediction()` напрямую, минуя API/Worker/Redis.

## Лучшие практики

!!! success "Генерирование ключей"
    ```bash
    # SECRET_KEY (44 символа, safe for URLs)
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"

    # FERNET_KEY (base64, 32 байта, для шифрования)
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

!!! warning "Секреты в production"
    - **Никогда** не коммитить `.env` в git
    - Использовать `git-crypt` или AWS Secrets Manager для production ключей
    - Ротировать `SECRET_KEY` и `FERNET_KEY` каждые 90 дней
    - Использовать разные ключи для dev/staging/production

!!! info "Database миграция"
    При переходе с SQLite на PostgreSQL:
    1. Поменять `DATABASE_URL` на PostgreSQL connection string
    2. Установить `WORKERS=2+` (PostgreSQL поддерживает параллельные записи)
    3. Таблицы создаются автоматически при первом старте
    4. Данные придётся мигрировать вручную

!!! tip "Мониторинг budget"
    Всегда установить `MAX_BUDGET_USD` ниже, чем лимит вашего аккаунта OpenRouter. Pipeline автоматически остановится, когда бюджет будет исчерпан.

## Ссылки

- **Исходный код**: `/src/config.py` (AppConfig и PRESETS), `/src/llm/config.py` (LLMConfig)
- **Спека**: `docs/08-api-backend.md` (§1: конфигурация)
- **Инициализация**: `/src/main.py` (lifespan, middlewares)
- **Docker**: `/docker-compose.yml`, `/Dockerfile`
- **Примеры**: `/.env.example`, `scripts/dry_run.py`
