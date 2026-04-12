# Delphi Press

Веб-продукт для прогнозирования заголовков СМИ. Мультиагентный Дельфи-пайплайн (5 персон, 2 раунда).

**Три режима работы:**
- **Web UI** — пользователь вводит свой API-ключ (OpenRouter). JWT-авторизация. Пресеты: Light / Opus.
- **Claude Code mode** — пользователь открывает Claude Code в директории проекта, просит прогноз на естественном языке. `claude-agent-sdk` → Claude Code Max подписка ($0/run). Sonnet 4.6 (сбор), Opus 4.6 (анализ). Результаты в локальной БД.
- **CLI mode** — `scripts/dry_run.py --provider claude_code --db data/delphi_press.db` для headless запуска.

**Стек**: Python 3.12+, FastAPI, ARQ (Redis), SQLite/SQLAlchemy 2.0, Pydantic v2, Jinja2 + Tailwind CSS v4, Docker Compose, pyarrow.
**Версия**: 0.9.5. **Тесты**: 1324.
**LLM**: OpenRouter (Claude/GPT-4/Gemini). Клиент через OpenAI SDK с `base_url`. max_tokens unlimited. Metaculus отключён (403).
**Auth**: JWT (PyJWT) + bcrypt. API-ключи пользователей: Fernet-шифрование (cryptography).
**Архитектура**: модульный монолит. Деплой: 4 контейнера (app + worker + redis + nginx).
**Сервер**: `deploy@213.165.220.144` (static IP), Debian 12, Yandex Cloud (4 vCPU 20%, 8GB RAM). Захарденен, Docker 29.3.1, TLS via Let's Encrypt.
**Язык интерфейса**: русский. Результаты на языке целевого СМИ.

## Документация

Актуальная документация проекта: **`docs-site/docs/`** ([delphi.antopkin.ru/docs/](https://delphi.antopkin.ru/docs/)).

### Навигация по документации

- Архитектура и pipeline: `docs-site/docs/architecture/`
- LLM-инфраструктура: `docs-site/docs/architecture/llm.md`
- Метод Дельфи (раунды, персоны): `docs-site/docs/delphi-method/`
- Методология (inverse problem, walk-forward): `docs-site/docs/methodology/`
- API reference: `docs-site/docs/api/reference.md`
- Frontend: `docs-site/docs/frontend/web-ui.md`
- Промпты агентов: `docs-site/docs/appendix/prompts.md`
- Инфраструктура: `docs-site/docs/infrastructure/`
- Roadmap и задачи: `docs-site/docs/roadmap/tasks.md`
- Changelog: `CHANGELOG.md`

Архивные предреализационные спеки: `docs/` (историческая ссылка, не source of truth).

### Утилиты

- `scripts/dry_run.py` → E2E dry run без инфраструктуры
- `tests/fixtures/mock_llm.py` → MockLLMClient для E2E тестов
- `.claude/skills/predict/` → Claude Code predict skill

## Дизайн-система (Impeccable)

Проект использует [Impeccable](https://github.com/pbakaus/impeccable) — систему дизайн-скиллов для Claude Code (20 скиллов в `.claude/skills/`).

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

**Стек фронтенда**: Tailwind CSS v4.2.2 (PostCSS build, @theme config) + 17 JS-referenced `fn-*` components + Newsreader/Source Sans 3/JetBrains Mono (Google Fonts). Документация: `docs-site/docs/frontend/web-ui.md`.

## Доменный глоссарий

**Перед работой с кодом — прочитай `GLOSSARY.md`.** Определения всех доменных терминов (медиация, событийная нить, фрейминг и др.) для предотвращения семантического дрифта.

## Синхронизация документации

При изменениях кода, затрагивающих публичные контракты:

- Изменение Pydantic-схемы в `src/schemas/` → обновить соответствующую страницу `docs-site/`
- Новый агент или LLM task → обновить `docs-site/docs/architecture/pipeline.md`
- Изменение порогов/констант → обновить страницу с формулами
- Bug fix с архитектурными выводами → добавить в `docs-site/docs/dead-ends/case-studies.md`

Сборка документации: `cd docs-site && mkdocs build --strict`

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

Полное описание: **[`docs-site/docs/architecture/pipeline.md`](docs-site/docs/architecture/pipeline.md)** — 9 стадий, 28 LLM-задач, data flow, task IDs, known gotchas.
