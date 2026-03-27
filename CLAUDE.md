# Delphi Press

Веб-продукт для прогнозирования заголовков СМИ. Мультиагентный Дельфи-пайплайн (5 персон, 2 раунда).

**Два режима работы:**
- **Web UI** — пользователь вводит свои API-ключи (OpenRouter, YandexGPT). JWT-авторизация. Пресеты: Light / Standard / Full.
- **Claude Code mode** — пользователь клонирует репо, запускает `/predict`. Субагенты Claude Code = 5 персон (Opus 4.6).

**Стек**: Python 3.12+, FastAPI, ARQ (Redis), SQLite/SQLAlchemy 2.0, Pydantic v2, Jinja2 + Pico.css, Docker Compose.
**LLM**: OpenRouter (Claude/GPT-4/Gemini) + YandexGPT. Клиент через OpenAI SDK с `base_url`.
**Auth**: JWT (PyJWT) + bcrypt. API-ключи пользователей: Fernet-шифрование (cryptography).
**Архитектура**: модульный монолит. Деплой: 4 контейнера (app + worker + redis + nginx).
**Язык интерфейса**: русский. Результаты на языке целевого СМИ.

## Спецификации

**Перед реализацией любого модуля — прочитай его спеку из `docs/`.** Спеки содержат Pydantic-схемы, сигнатуры функций, промпты агентов и контракты между модулями.

### Навигация по спекам

- `src/schemas/` → соответствующие спеки по модулю
- `src/agents/base.py`, `orchestrator.py` → `docs/02-agents-core.md`
- `src/agents/collectors/` → `docs/03-collectors.md`
- `src/agents/analysts/` → `docs/04-analysts.md`
- `src/agents/forecasters/` → `docs/05-delphi-pipeline.md`
- `src/agents/generators/` → `docs/06-generators.md`
- `src/llm/` → `docs/07-llm-layer.md`
- `src/api/`, `src/db/` → `docs/08-api-backend.md`
- `src/api/auth.py`, `src/api/keys.py` → `docs/08-api-backend.md` (§12: аутентификация)
- `src/security/` → `docs/08-api-backend.md` (§12: KeyVault, шифрование)
- `src/web/` → `docs/09-frontend.md`
- `.claude/skills/predict/` → Claude Code predict skill (сессия 12)

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
uv run uvicorn src.main:app --reload --port 8000   # dev server
uv run arq src.worker.WorkerSettings                # background worker
uv run pytest tests/ -v                             # tests
ruff format src/ tests/ && ruff check src/ --fix    # lint
docker compose up -d                                # production
```
