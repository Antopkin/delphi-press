# Code style & conventions

Стиль кода Delphi Press. Claude Code и внешние контрибьюторы должны следовать.

## Async everywhere

Все I/O функции — `async def`. Никогда `requests`, только `httpx.AsyncClient`.

```python
# ✅ правильно
async with httpx.AsyncClient() as client:
    response = await client.get(url)

# ❌ неправильно
import requests
response = requests.get(url)
```

- `time.sleep()` запрещён — `await asyncio.sleep()`.
- Параллельные задачи: `await asyncio.gather(*tasks, return_exceptions=True)`.
- Таймауты: `async with asyncio.timeout(seconds):`.
- БД: только `aiosqlite` через SQLAlchemy async engine. Никогда sync `sqlite3`.

## Type hints

Все функции типизированы. Для Python 3.12+: `str | None` вместо `Optional[str]`.

```python
async def fetch_signals(outlet: str, limit: int = 100) -> list[SignalRecord]: ...
```

## Pydantic v2

Все схемы агентов и API — `BaseModel` v2:

- Валидаторы: `@field_validator("field")` + `@classmethod`. **НЕ** `@validator`.
- `ConfigDict`: `model_config = ConfigDict(from_attributes=True)`. **НЕ** `class Config`.
- Обязательные поля: `Field(...)` с `description`. Опциональные: `Field(default=...)`.
- Иммутабельные результаты: `@dataclass(frozen=True)` или `model_config = ConfigDict(frozen=True)`.
- JSON парсинг: `Model.model_validate_json(text)`. **НЕ** `Model.parse_raw()`.
- Строковые enum: `StrEnum`, не `str, Enum`.

Детальнее для агентов: [agents-llm.md](https://github.com/Antopkin/delphi-press/blob/main/.claude/rules/agents-llm.md).

## AgentResult контракт

Frozen dataclass из `src/schemas/agent.py`:

```python
@dataclass(frozen=True)
class AgentResult:
    success: bool
    data: dict  # структура документирована в execute() docstring
    error: str | None
    cost_usd: float
    tokens_in: int
    tokens_out: int
    duration_ms: int
```

- Агенты **не бросают исключения** — возвращают `AgentResult(success=False, error=...)`.
- `data` — каждый агент документирует структуру в `execute()` docstring.

## BaseAgent контракт

- Переопределять `execute()`, **никогда** `run()`. `run()` — final.
- `execute()` возвращает `dict`, который становится `AgentResult.data`.
- Исключения из `execute()` ловятся `run()` → `AgentResult(success=False, error=...)`.
- Каждый агент реализует `validate_context()` если нужны входные слоты.

## LLM cost tracking — обязательно

После **каждого** LLM-вызова:

```python
response = await self.llm.complete(task="task_id", messages=[...])
self.track_llm_usage(
    model=response.model,
    tokens_in=response.tokens_in,
    tokens_out=response.tokens_out,
    cost_usd=response.cost_usd,
)
```

`task` — строковый идентификатор для `ModelRouter`, см. [architecture/llm.md](../architecture/llm.md).

## Imports

Абсолютные от `src.`:

```python
# ✅ правильно
from src.schemas.prediction import PredictionRequest
from src.agents.base import BaseAgent

# ❌ неправильно
from ..schemas.prediction import PredictionRequest
```

## Docstrings — Google style

**Module-level docstring обязателен** для каждого файла в `src/`:

```python
"""Краткая роль модуля в одну строку.

Спека: docs-site/docs/<category>/<page>.md.
Контракт: Вход → Выход.
"""
```

Пример: `src/agents/forecasters/judge.py` — gold standard.

## Комментарии

- **Default — не писать**. Хорошо названные идентификаторы объясняют WHAT сами.
- Писать комментарий только если WHY неочевидно: скрытое ограничение, обход бага, нелогичный инвариант.
- Не ссылаться на текущую задачу / fix / вызывающий код («used by X», «added for Y») — это PR description, не код.

## Testing

Детальнее: [.claude/rules/testing.md](https://github.com/Antopkin/delphi-press/blob/main/.claude/rules/testing.md).

- Фреймворк: `pytest` + `pytest-asyncio`
- Асинхронные: `@pytest.mark.asyncio` + `async def test_...`
- Mock LLM: `MockLLMClient` в `tests/fixtures/mock_llm.py` — Protocol, не наследование
- Тесты пишутся на **поведение** (public interface), не на реализацию
- Один тест — одно поведение
- Именование: `test_<module>_<behavior>`

## Linting

```bash
ruff format src/ tests/
ruff check src/ --fix
```

Конфиг — `pyproject.toml` `[tool.ruff]`.

## Структура проекта

- `src/` — production код
- `tests/` — pytest, зеркалит структуру `src/`
- `scripts/` — CLI утилиты (dry_run, eval)
- `docs-site/` — MkDocs, single source of truth
- `.claude/rules/` — path-scoped conventions для Claude Code
- `data/` — local БД, parquet, кэши (gitignored)
