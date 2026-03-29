# Delphi Press

Веб-продукт для прогнозирования заголовков СМИ. Мультиагентный Дельфи-пайплайн (5 персон, 2 раунда).

**Два режима работы:**
- **Web UI** — пользователь вводит свой API-ключ (OpenRouter). JWT-авторизация. Пресеты: Light / Standard / Full.
- **Claude Code mode** — пользователь клонирует репо, запускает `/predict`. Субагенты Claude Code = 5 персон (Opus 4.6).

**Стек**: Python 3.12+, FastAPI, ARQ (Redis), SQLite/SQLAlchemy 2.0, Pydantic v2, Jinja2 + Tailwind CSS v4, Docker Compose.
**LLM**: OpenRouter (Claude/GPT-4/Gemini). Клиент через OpenAI SDK с `base_url`.
**Auth**: JWT (PyJWT) + bcrypt. API-ключи пользователей: Fernet-шифрование (cryptography).
**Архитектура**: модульный монолит. Деплой: 4 контейнера (app + worker + redis + nginx).
**Сервер**: `deploy@213.165.220.144` (static IP), Debian 12, Yandex Cloud (4 vCPU 20%, 8GB RAM). Захарденен, Docker 29.3.1, TLS via Let's Encrypt.
**Язык интерфейса**: русский. Результаты на языке целевого СМИ.

## Спецификации

**Перед реализацией любого модуля — прочитай его спеку из `docs/`.** Спеки содержат Pydantic-схемы, сигнатуры функций, промпты агентов и контракты между модулями.

### Навигация по спекам

- `src/schemas/` → соответствующие спеки по модулю
- `src/agents/base.py`, `orchestrator.py` → `docs/02-agents-core.md`
- `src/agents/collectors/` → `docs/03-collectors.md`
- `src/data_sources/outlet_resolver.py`, `wikidata_client.py`, `feed_discovery.py` → `docs/03-collectors.md` (§7: OutletResolver)
- `src/agents/analysts/` → `docs/04-analysts.md`
- `src/agents/forecasters/` → `docs/05-delphi-pipeline.md`
- `src/agents/generators/` → `docs/06-generators.md`
- `src/llm/` → `docs/07-llm-layer.md`
- `src/api/`, `src/db/` → `docs/08-api-backend.md`
- `src/api/auth.py`, `src/api/keys.py` → `docs/08-api-backend.md` (§12: аутентификация)
- `src/security/` → `docs/08-api-backend.md` (§12: KeyVault, шифрование)
- `src/data_sources/foresight.py` → `tasks/research/metaculus_polymarket_api.md`, `tasks/research/gdelt_api.md`
- `src/agents/collectors/foresight_collector.py` → `docs/03-collectors.md` + ресёрчи выше
- `src/web/` → `docs/09-frontend.md`
- `src/eval/` → `tasks/research/retrospective_testing.md`
- `src/inverse/` → `tasks/research/polymarket_inverse_problem.md` (обратная задача: профилирование участников, informed consensus)
- Roadmap (задачи, баги, сессии) → `docs/11-roadmap.md`
- `scripts/dry_run.py` → E2E dry run без инфраструктуры
- `tests/fixtures/mock_llm.py` → MockLLMClient для E2E тестов
- `.claude/skills/predict/` → Claude Code predict skill (сессия 12)

## Дизайн-система (Impeccable)

Проект использует [Impeccable](https://github.com/pbakaus/impeccable) — систему дизайн-скиллов для Claude Code (21 скилл в `.claude/skills/`).

**Первый запуск**: выполни `/teach-impeccable` для настройки дизайн-контекста проекта. Результат сохраняется в `.impeccable.md`.

**Основной скилл**: `/frontend-design` — активируется при работе с `src/web/`. Содержит 7 справочных модулей (типографика, цвет, пространство, анимация, взаимодействие, адаптивность, UX-тексты).

**Рабочие команды** (20 стиринг-команд):

| Категория | Команды |
|---|---|
| Аудит и ревью | `/audit`, `/critique`, `/polish` |
| Типографика и цвет | `/typeset`, `/colorize` |
| Лейаут и пространство | `/arrange`, `/adapt` |
| Выразительность | `/bolder`, `/quieter`, `/delight` |
| Движение и взаимодействие | `/animate`, `/onboard` |
| Оптимизация и упрощение | `/optimize`, `/harden`, `/distill`, `/clarify` |
| Рефакторинг | `/extract`, `/normalize` |
| Продвинутое | `/overdrive` |
| Настройка | `/teach-impeccable` |

**Стек фронтенда**: Tailwind CSS v4.2.2 (PostCSS build, @theme config) + 17 JS-referenced `fn-*` components + Newsreader/Source Sans 3/JetBrains Mono (Google Fonts). Спека: `docs/09-frontend.md`.

## Доменный глоссарий

**Перед работой с кодом — прочитай `GLOSSARY.md`.** Определения всех доменных терминов (медиация, событийная нить, фрейминг и др.) для предотвращения семантического дрифта.

## Правила кода

- **Async everywhere**: все I/O — async (httpx, aiosqlite, ARQ)
- **Type hints**: все функции типизированы
- **Pydantic schemas**: входы/выходы агентов — Pydantic-модели из `src/schemas/`
- **Structured output**: LLM-ответы парсятся в Pydantic-модели, не в сырые строки
- **Error handling**: агенты не бросают исключения — возвращают `AgentResult(success=False, error=...)`
- **Cost tracking**: каждый LLM-вызов логируется с tokens_in/out и cost_usd
- **Imports**: абсолютные от `src.` (`from src.schemas.prediction import PredictionRequest`)
- **Docstrings**: Google-style. Module-level docstring обязателен (стадия пайплайна, ссылка на спеку, контракт вход/выход)

## Команды

```bash
npm run css:build                                   # build CSS: input.css → tailwind.css
npm run css:dev                                     # watch mode: input.css → tailwind.css
uv run uvicorn src.main:app --reload --port 8000   # dev server
uv run arq src.worker.WorkerSettings                # background worker
uv run pytest tests/ -v                             # tests
uv run pytest tests/test_integration/ -v            # E2E integration tests only
ruff format src/ tests/ && ruff check src/ --fix    # lint
docker compose up -d                                # production
```

### E2E Dry Run (без Redis/DB/Docker)

```bash
# Дешёвая модель, 5 event threads (быстрый smoke test, ~$0.25)
uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 5

# Production-like (Opus, 20 threads, ~$5-15)
uv run python scripts/dry_run.py --outlet "ТАСС" --model anthropic/claude-opus-4.6

# Полный список аргументов
uv run python scripts/dry_run.py --help
```

Требует `OPENROUTER_API_KEY` в env. Скрипт вызывает `Orchestrator.run_prediction()` напрямую, минуя API/worker/Redis.

## Архитектура pipeline

Полное описание: **[`docs/architecture.md`](docs/architecture.md)** — 9 стадий, 28 LLM-задач, data flow, task IDs, known gotchas.

Краткая навигация по pipeline: `docs/11-roadmap.md` (таблица компонентов + ключевые файлы).
