# Python экосистема 2026 — обновления Q1

> Research date: 2026-04-05

## Источники

1. [uv CHANGELOG — GitHub](https://github.com/astral-sh/uv/blob/main/CHANGELOG.md)
2. [Ruff v0.15.0 — Astral Blog](https://astral.sh/blog/ruff-v0.15.0)
3. [Python 3.14 What's New](https://docs.python.org/3/whatsnew/3.14.html)
4. [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/)
5. [SQLAlchemy 2.1.0b1 Released](https://www.sqlalchemy.org/blog/2026/01/21/sqlalchemy-2.1.0b1-released/)
6. [SQLAlchemy 2.1 Migration Guide](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html)
7. [pytest 9.0.0 Announcement](https://docs.pytest.org/en/stable/announce/release-9.0.0.html)
8. [pytest-asyncio 1.0 Migration](https://thinhdanggroup.github.io/pytest-asyncio-v1-migrate/)
9. [Pydantic Releases](https://github.com/pydantic/pydantic/releases)
10. [OpenAI Python SDK Releases](https://github.com/openai/openai-python/releases)

---

## Матрица обновлений

| Пакет | В проекте | Последняя | Breaking Changes | Effort | Приоритет |
|-------|-----------|-----------|-----------------|--------|-----------|
| **uv** | (менеджер) | 0.11.3 | Нет | — | Low |
| **ruff** | 0.15.8 | 0.15.9 | Нет (patch) | Нет | Low |
| **FastAPI** | 0.135.2 | 0.135.2 | `strict_content_type` по умолч. | Низкий | Medium |
| **Pydantic** | 2.12.5 | 2.12.5 | Нет | Нет | — |
| **SQLAlchemy** | 2.0.48 | 2.0.49 / 2.1.0b1 | 2.1: greenlet не auto-install | Средний | High (Q3) |
| **pytest** | 9.0.2 | 9.0.2 | Python 3.9 dropped | Нет | — |
| **pytest-asyncio** | 1.3.0 | 1.3.0 | `event_loop` fixture удалён | Средний | Medium |
| **httpx** | 0.28.1 | 0.28.1 | 1.0 не вышел | Нет | Low |
| **pyarrow** | 23.0.1 | 23.0.1 | Нет | Нет | — |
| **openai SDK** | 2.30.0 | ~2.30.x | v2: output types changed | Низкий | Medium |
| **Python** | 3.12+ | 3.14.3 | 3.13: get_event_loop() RuntimeError; 3.14: free-threading | Высокий | Low |

---

## Python 3.13/3.14

**Рекомендация: оставаться на 3.12 до осени 2026.**

- **3.13**: `asyncio.get_event_loop()` бросает RuntimeError — может сломать код. Free-threading 40% overhead.
- **3.14**: Free-threading 5-10% overhead, asyncio debugger, template strings. Но требует пересборки native пакетов (numpy, scipy, cryptography).

---

## Ключевые паттерны 2026

### 1. TaskGroup вместо gather

```python
# Устаревший
results = await asyncio.gather(task1(), task2())

# Современный (3.11+)
async with asyncio.TaskGroup() as tg:
    t1 = tg.create_task(task1())
    t2 = tg.create_task(task2())
```

TaskGroup отменяет все задачи при первой ошибке. Для Delphi Press — улучшит error propagation при сбое персоны.

### 2. Ruff ASYNC rules

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "ASYNC", "B", "RUF"]
```

Новые правила: `ASYNC212` (blocking http в async), `ASYNC300` (create_task без сохранения), `ASYNC109` (timeout patterns).

### 3. asyncio.timeout()

```python
async with asyncio.timeout(30.0):
    result = await llm_call()
```

### 4. SQLAlchemy 2.1: явная зависимость asyncio

```toml
dependencies = ["sqlalchemy[asyncio]>=2.1"]  # greenlet не auto
```

---

## Рекомендации для Delphi Press

### Приоритет 1 — Немедленно

**Обновить SQLAlchemy до 2.0.49:**
```bash
uv add "sqlalchemy[asyncio]>=2.0.49"
```

**Расширить ruff ruleset:**
```toml
select = ["E", "F", "I", "ASYNC", "B", "RUF"]
```
Ожидание: 5-20 новых предупреждений по async-антипаттернам.

**Проверить `event_loop` в тестах:**
```bash
grep -r "event_loop" tests/
```
pytest-asyncio 1.3.0 удалил fixture — тесты с ним молча сломаны.

### Приоритет 2 — Q2 2026

- Аудит FastAPI `strict_content_type`
- Миграция `gather` → `TaskGroup` в оркестраторе
- Проверить openai SDK 2.x возвращаемые типы

### Приоритет 3 — Q3 2026

- Тестирование на Python 3.13 в CI-матрице
- Отслеживать SQLAlchemy 2.1 stable
- Оценить uv workspaces (если вынести модули)
