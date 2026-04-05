# Тестирование в AI-assisted разработке

> Дата: 2026-04-05. Проект: Delphi Press v0.9.5, Python 3.12+, FastAPI, pytest 8.0+, 1324 теста.

## Источники

1. [AI-Assisted Development in 2026: Best Practices, Real Risks](https://dev.to/austinwdigital/ai-assisted-development-in-2026-best-practices-real-risks-and-the-new-bar-for-engineers-3fom)
2. [Hypothesis — Pydantic Integration](https://docs.pydantic.dev/latest/integrations/hypothesis/)
3. [Mutation Testing with Mutmut 2026](https://johal.in/mutation-testing-with-mutmut-python-for-code-reliability-2026/)
4. [Snapshot testing with Syrupy](https://til.simonwillison.net/pytest/syrupy)
5. [LLM Testing: A Practical Guide — Langfuse](https://langfuse.com/blog/2025-10-21-testing-llm-applications)
6. [Pytest Parallel Execution 2025](https://johal.in/pytest-parallel-execution-for-large-test-suites-in-python-2025/)
7. [Making PyPI's test suite 81% faster](https://blog.trailofbits.com/2025/05/01/making-pypis-test-suite-81-faster/)
8. [Coverage.py Threshold Enforcement in CI 2026](https://johal.in/coverage-py-pytest-plugin-threshold-enforcement-in-ci-2026/)
9. [Using Hypothesis and Schemathesis to Test FastAPI](https://testdriven.io/blog/fastapi-hypothesis/)
10. [DeepEval — LLM Evaluation Framework](https://github.com/confident-ai/deepeval)

---

## Текущая стратегия (аудит)

### Что работает хорошо

- **MockLLMClient** — Protocol-based mock с dispatcher. Call log + call counts дают observability. Более продвинуто, чем большинство LLM testing frameworks.
- **E2E integration test** — покрывает 9 стадий, 18 агентов, проверяет PredictionContext, progress callbacks, resilience, registry, schema round-trip.
- **Protocol-based mocking** — все внешние источники (RSS, web search, scraper, Polymarket) через `AsyncMock(spec=Protocol)`.
- **asyncio_mode="auto"** — нет boilerplate `@pytest.mark.asyncio`.
- **TDD hook** — предупреждение при правке test_*.py в green-фазе.

### Gaps

| Gap | Риск | Описание |
|-----|------|----------|
| Нет coverage gates | Высокий | Нет ответа на "что не покрыто" |
| Нет slow test detection | Средний | Скрытые медленные тесты |
| Нет property-based testing | Средний | Pydantic-схемы без генеративных тестов |
| Нет flaky test detection | Средний | async-тесты с таймаутами |
| Нет contract testing OpenAPI | Средний | spec ≠ Pydantic-модели |
| Нет snapshot testing LLM | Низкий | Структурный drift невидим |
| Нет параллелизации | Низкий | 1324 теста последовательно |
| Нет mutation testing | Низкий | Логические ошибки невидимы |

---

## Рекомендации по расширению

| Стратегия | Effort | Impact | Приоритет |
|-----------|--------|--------|-----------|
| **Coverage gates** (`pytest-cov --cov-fail-under=78`) | 1 час | Высокий | **P1** |
| **Slow test detection** (`--durations=20` + `@pytest.mark.slow`) | 2 часа | Высокий | **P1** |
| **pytest-timeout** (30s max per test) | 1 час | Высокий | **P1** |
| **Property-based (Hypothesis)** для Pydantic schemas | 4 часа | Высокий | **P2** |
| **Flaky detection** (`pytest-randomly` + `pytest-rerunfailures`) | 2 ��аса | Средний | **P2** |
| **Contract testing** (schemathesis для OpenAPI) | 3 часа | Средний | **P2** |
| **Snapshot testing** (syrupy для структуры ответов) | 3 часа | Средний | **P3** |
| **pytest-xdist** параллелизация | 4 часа | Средний | **P3** |
| **Mutation testing** (mutmut, целевой) | 8 часов | Низкий | **P4** |

---

## Property-based testing (Hypothesis)

### Нужно ли?

**Да, для Pydantic-схем.** Pydantic v2 + Hypothesis: `st.from_type()` автоматически работает с constrained типами. Генерирует 200+ вариантов, включая юникод, whitespace-only строки, float vs int.

### Пример

```python
from hypothesis import given, settings
import hypothesis.strategies as st
from src.schemas.prediction import PredictionRequest

@given(st.from_type(PredictionRequest))
@settings(max_examples=200)
def test_prediction_request_always_serializable(req: PredictionRequest):
    assert req.model_dump_json()
    restored = PredictionRequest.model_validate_json(req.model_dump_json())
    assert restored == req
```

### Приоритетные схемы

- `PredictionRequest` — outlet/target_date граничные значения
- `HeadlineOutput` — rank bounds, confidence [0.0, 1.0], unicode
- `LLMResponse` — cost_usd >= 0, tokens >= 0
- `AgentResult` — success/error комбинации

---

## Параллелизация (pytest-xdist)

### Оценка для 1324 тестов

Реалистичное ускорение с `-n 4`: 2.5–3x при правильной изоляции.

**Ключевое препятствие: SQLite.** Решение: каждый xdist worker получает собственную in-memory SQLite:

```python
# conftest.py
@pytest.fixture(scope="session")
def db_url():
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"sqlite+aiosqlite:///file:{worker}_test.db?mode=memory&cache=shared&uri=true"
```

**Конфигурация:**
```toml
[tool.pytest.ini_options]
addopts = "-n auto --dist=loadscope"
```

---

## Coverage gates

### Рекомендуемый threshold: 78% (стартовый)

```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=78"
```

Повышать на 2% каждые 2 недели.

| Модуль | Цель |
|--------|------|
| `src/schemas/` | 95% |
| `src/agents/` | 85% |
| `src/llm/` | 80% |
| `src/db/` | 75% |
| `src/web/` | 60% |

---

## Конкретный план внедрения

### Неделя 1 — Low effort, high impact

**Шаг 1: Coverage baseline (2 часа)**
```bash
uv add --dev pytest-cov
uv run pytest tests/ --cov=src --cov-report=term-missing --cov-report=html -q
```

**Шаг 2: Slow test detection (1 час)**
```bash
uv run pytest tests/ --durations=20 -q
```
Маркировать тесты >1 сек как `@pytest.mark.slow`. В CI: `-m "not slow"`.

**Шаг 3: pytest-timeout (1 час)**
```bash
uv add --dev pytest-timeout
```
```toml
timeout = 30  # секунд максимум
```

### Неделя 2 — Property-based testing

**Шаг 4: Hypothesis для Pydantic (4 часа)**
```bash
uv add --dev hypothesis
```
5–10 Hypothesis-тестов для schemas, 200+ вариантов каждый.

### Неделя 3 — Flaky + Contract

**Шаг 5: Flaky detection (2 часа)**
```bash
uv add --dev pytest-randomly pytest-rerunfailures
uv run pytest tests/ --reruns=3 --reruns-delay=0.5
```

**Шаг 6: OpenAPI contract testing (3 часа)**
```bash
uv add --dev schemathesis
```
Schemathesis генерирует тест-кейсы из `/openapi.json` автоматически.

### Месяц 2 — Snapshot + Mutation

**Шаг 7: Snapshot testing (syrupy, 3 часа)** — структура PipelineContext после E2E.

**Шаг 8: Mutation testing (mutmut, 8 часов, P4)** — только `src/agents/judge.py`, `src/eval/metrics.py`. Quarterly аудит, не CI-step.
