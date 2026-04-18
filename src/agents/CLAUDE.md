# Правила для src/agents/

Обязательные правила при создании или редактировании агентов. Полная 9-стадийная спека: `docs-site/docs/architecture/pipeline.md`.

## Контракт BaseAgent (НЕ нарушать)

- **Переопределяй `execute()`, НИКОГДА `run()`** — `run()` final: мапит исключения в `AgentResult(success=False)`, трекает LLM-usage, управляет таймаутами.
- **`execute()` возвращает `dict[str, Any]`** — становится `AgentResult.data`. Документируй ожидаемые ключи в docstring (`{"signals": [...], ...}`).
- **Исключения в `execute()` не ловить** — они конвертируются `run()`'ом в `AgentResult(success=False, error=...)`. Try/except только для recovery с fallback-данными.
- **Реализуй `validate_context()`** если агент требует входные слоты. Return `None` — OK, return `str` — error message (pipeline остановится).
- **Уникальный class-level `name`** (например `name = "news_scout"`) — идентифицирует агента в логах и STAGES конфиге.

## LLM cost tracking (ОБЯЗАТЕЛЬНО после КАЖДОГО вызова)

```python
response = await self.llm.complete(task="task_id", messages=[...])
self.track_llm_usage(
    model=response.model,
    tokens_in=response.tokens_in,
    tokens_out=response.tokens_out,
    cost_usd=response.cost_usd,
)
```

Пропуск = тихая потеря в per-agent метриках (global BudgetTracker всё ещё трекает). Не enforce'ится линтером — только grep-audit.

## Module-level docstring (обязателен)

```python
"""Stage N: AgentName — краткая роль.

Спека: docs-site/docs/<category>/<page>.md.

Контракт:
    Вход: PipelineContext с <slot_name> (<type>).
    Выход: AgentResult.data = {"key": ...}
"""
```

Gold standard: `src/agents/forecasters/judge.py`.

## Pipeline — 9 стадий (one-liner для ориентации)

1. **COLLECTION** — сбор 100-200 сигналов (NewsScout, EventCalendar, OutletHistorian, ForesightCollector; parallel, `min_successful=2/4`)
2. **EVENT_IDENTIFICATION** — кластеризация в ~20 EventThread (EventTrendAnalyzer; sequential, required)
3. **TRAJECTORY** — 3 аналитика (Geopolitical, Economic, Media; parallel, `min_successful=2/3`)
4. **DELPHI_R1** — 5 персон независимо (parallel, `min_successful=3/5`)
5. **DELPHI_R2** — Mediator синтез → 5 персон ревизия (Mediator sequential + 5 parallel; `min_successful=3/5`)
6. **CONSENSUS** — Judge агрегирует timeline + ранжирует заголовки (sequential, **детерминированный**, без LLM)
7. **FRAMING** — адаптация под редакционный голос outlet (sequential)
8. **GENERATION** — StyleReplicator генерирует заголовки (sequential)
9. **QUALITY_GATE** — fact-check + style-check параллельно (sequential stage, parallel subtasks)

## Параллельные стадии — `min_successful`

Минимум успешных агентов. Если меньше — стадия падает (unless `required=False`, редко). После parallel-агентов orchestrator merge'ит результаты в context через `context.merge_agent_result()`. Sequential auto-merge'ится.

## Что сюда НЕ кладём

- LLM model tables / pricing / retry-параметры → `src/llm/CLAUDE.md` + `docs-site/docs/architecture/llm.md`
- UI/web правила → `.claude/rules/frontend-design.md`
- Generic async patterns → `.claude/rules/async-patterns.md`
- Pydantic schema conventions → `.claude/rules/pydantic-schemas.md`
- Testing patterns → `.claude/rules/testing.md`
