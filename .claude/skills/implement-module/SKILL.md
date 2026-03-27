---
name: implement-module
description: Автономная реализация модуля по спецификации из docs/
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
---

# /implement-module <module-name>

Автономно реализуй модуль проекта Delphi Press.

## Маршрут модуль → спека

| Аргумент | Спека | Путь |
|---|---|---|
| schemas | docs/02-agents-core.md + docs/03-06 | src/schemas/ |
| config | docs/00-overview.md | src/config.py |
| llm | docs/07-llm-layer.md | src/llm/ |
| agents-core | docs/02-agents-core.md | src/agents/base.py, registry.py, orchestrator.py |
| collectors | docs/03-collectors.md | src/agents/collectors/ |
| analysts | docs/04-analysts.md | src/agents/analysts/ |
| forecasters | docs/05-delphi-pipeline.md | src/agents/forecasters/ |
| generators | docs/06-generators.md | src/agents/generators/ |
| api | docs/08-api-backend.md | src/api/, src/db/ |
| frontend | docs/09-frontend.md | src/web/ |
| deploy | docs/10-deployment.md | Docker, nginx, compose |

## Workflow

### Шаг 0: Bootstrap (только первая сессия)
Если `pyproject.toml` не существует:
1. Создай `pyproject.toml`:
   - `[project]`: name="delphi-press", python=">=3.12"
   - Зависимости: fastapi, uvicorn[standard], pydantic[dotenv], pydantic-settings, httpx, aiosqlite, sqlalchemy[asyncio], arq, sse-starlette, feedparser, openai, jinja2
   - Dev-зависимости: pytest, pytest-asyncio, ruff, httpx (для TestClient)
2. `uv sync` — установить зависимости
3. Создай директории: `src/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
4. В `tests/conftest.py` — базовые fixtures: `mock_llm`, `pipeline_context`
5. Проверь: `uv run pytest tests/ -v` — должен пройти (0 тестов, 0 ошибок)
6. Продолжай к Шагу 1

### Шаг 1: Чтение контекста
1. Прочитай GLOSSARY.md — доменные термины
2. Прочитай спеку модуля из docs/ (по таблице выше)
3. Прочитай существующие src/schemas/ — Pydantic-модели
4. Прочитай src/agents/base.py — паттерн BaseAgent (если есть)
5. Прочитай существующие тесты в tests/ — паттерн тестирования
6. Прочитай промпты из docs/prompts/ если реализуешь агентов

### Шаг 2: Планирование
1. Войди в Plan Mode
2. Определи файлы для создания (с полными путями)
3. Определи зависимости от других модулей
4. Определи тесты для каждого файла
5. Если зависимость не реализована — спланируй stub/interface
6. Выйди из Plan Mode после одобрения

### Шаг 3: Вертикальная реализация (Red-Green цикл)
Для каждого компонента модуля:
1. **RED**: Напиши 1-2 теста на поведение компонента
2. **GREEN**: Напиши минимальную реализацию, проходящую тесты
3. **VERIFY**: `uv run pytest tests/<path> -v`
4. **FIX**: Если тесты падают — исправь реализацию (не тесты!)
5. Повтори для следующего компонента

Правила Red-Green:
- Один тест за раз. Не пиши все тесты сразу.
- Тест проверяет поведение через public interface, не реализацию.
- Минимальный код для прохождения текущего теста. Не предвосхищай будущие.
- Никогда не рефакторь на красном.

### Шаг 4: Рефакторинг (только когда всё зелёное)
1. Все тесты зелёные?
2. Убери дублирование
3. Проверь docstrings (Google-style, module-level обязателен)
4. `ruff format src/ tests/ && ruff check src/ --fix`
5. `uv run pytest tests/ -v` — финальная проверка

### Шаг 5: Коммит
1. `git add` — только файлы модуля + тесты
2. Сообщение: `feat(<module>): implement <краткое описание>`
3. Пример: `feat(collectors): implement NewsScout, EventCalendar, OutletHistorian agents`

## Обязательные правила

### Docstrings
Module-level docstring в каждом файле:
```python
"""Stage N: STAGE_NAME — краткое описание.

Спека: docs/XX-module.md

Контракт:
    Вход: PipelineContext с [слоты]
    Выход: AgentResult.data = {"key": Type}
"""
```

### Импорты
Абсолютные от `src.`:
```python
from src.schemas.agent import AgentResult
from src.agents.base import BaseAgent
```

### Агенты
- `execute()` — вся логика. `run()` НИКОГДА не переопределять.
- `self.track_llm_usage(model, tokens_in, tokens_out, cost_usd)` после каждого LLM-вызова.
- LLM-ответы парсить через `Model.model_validate_json()`, не сырые строки.
- Агент не бросает исключения наружу — `run()` оборачивает в `AgentResult(success=False)`.

### Stubs для нереализованных зависимостей
Если модуль зависит от нереализованного кода:
```python
# src/llm/client.py — stub, будет реализован в сессии llm
from typing import Protocol

class LLMClient(Protocol):
    async def complete(self, *, task: str, messages: list, **kwargs) -> "LLMResponse": ...
```
