# Claude Code mode

Claude Code mode — альтернативный provider для исполнения пайплайна через подписку **Claude Code Max** вместо OpenRouter API. Даёт **$0/run** для разработчика, но требует локальной установки Claude Code CLI.

!!! info "Когда использовать"
    - Разработка и отладка: pipeline шагает без расходов
    - Исследовательские прогоны (бенчмарки, walk-forward): десятки прогонов без счёта за API
    - Headless cron на машине разработчика: локальная БД, без зависимости от OpenRouter

    Production Web UI **продолжает использовать OpenRouter** (пользователи вводят свои ключи).

## Архитектура

```
Пользователь → natural language ("прогноз для ТАСС")
           ↓
    predict skill (.claude/skills/predict/SKILL.md)
           ↓
    scripts/dry_run.py --provider claude_code --db data/delphi_press.db
           ↓
    ClaudeCodeProvider (src/llm/providers.py)
           ↓  claude-agent-sdk (subprocess)
           ↓
    Claude Code CLI → Max подписка Anthropic
```

Каждый `LLMProvider.complete()` порождает отдельный subprocess к Claude Code CLI. Это выше оверхед на запрос, чем HTTP к OpenRouter, но биллинг нулевой.

## ClaudeCodeProvider (`src/llm/providers.py`)

```python
class ClaudeCodeProvider(LLMProvider):
    """Claude Code SDK provider — биллинг через Max подписку."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # claude-agent-sdk → subprocess Claude Code CLI
        # Возвращает текст + оценку токенов (cost_usd = 0.0)
        ...
```

Контракт тот же, что у `OpenRouterClient` — pipeline не знает, какой provider за ним стоит.

## Маршрутизация моделей (`CLAUDE_CODE_ASSIGNMENTS`)

Таблица в `src/llm/router.py` переопределяет `DEFAULT_ASSIGNMENTS`:

| Группа задач | В DEFAULT_ASSIGNMENTS | В CLAUDE_CODE_ASSIGNMENTS |
|---|---|---|
| Сбор новостей / события / кластеризация | `google/gemini-*-flash-*` | **`anthropic/claude-sonnet-4.6`** |
| Анализ траекторий / cross-impact | `anthropic/claude-opus-4.6` | `anthropic/claude-opus-4.6` |
| Все 5 персон (R1 + R2) | `anthropic/claude-opus-4.6` | `anthropic/claude-opus-4.6` |
| Mediator, framing, style, quality | `anthropic/claude-opus-4.6` | `anthropic/claude-opus-4.6` |
| Judge | `anthropic/claude-opus-4.6` | — (выполняется детерминированно) |

Правило построения: **Gemini-задачи → Sonnet 4.6, всё остальное → Opus 4.6**. `fallback_models=[]` — Claude Code SDK ретрится сам.

Код построения:

```python
CLAUDE_CODE_ASSIGNMENTS = {
    task: ModelAssignment(
        ...,
        primary_model=(
            "anthropic/claude-sonnet-4.6" if task in _GEMINI_TASKS else a.primary_model
        ),
        fallback_models=[],
    )
    for task, a in DEFAULT_ASSIGNMENTS.items()
}
```

## Как запустить

### Через predict skill (рекомендуется)

Открыть проект в Claude Code и написать на естественном языке:

```
Сделай прогноз для ТАСС на завтра
```

Skill распознаёт intent, парсит параметры (outlet, date), вызывает `scripts/dry_run.py` с `--provider claude_code`. Описание: `.claude/skills/predict/SKILL.md`.

### CLI напрямую

```bash
uv run python scripts/dry_run.py \
    --provider claude_code \
    --outlet "ТАСС" \
    --target-date 2026-04-19 \
    --db data/delphi_press.db \
    --event-threads 20
```

Требует установленного Claude Code CLI и активной Max-подписки.

### Просмотр результатов

```bash
uv run uvicorn src.main:app --port 8000
# → http://localhost:8000/results/{prediction_id}
```

## Отличия от OpenRouter-пути

| Параметр | OpenRouter (Web UI) | Claude Code mode |
|---|---|---|
| Биллинг | $5–15 за Opus-прогон | $0 (Max подписка) |
| Модели сбора | Gemini Flash Lite (дёшево) | **Sonnet 4.6** (дороже по подписке, но мощнее) |
| Латентность | HTTP к OpenRouter (~1с/запрос) | subprocess Claude Code CLI (~2–5с/запрос) |
| Parallel | до 20+ event threads | рекомендуется sequential или `max_concurrency=2` |
| Хранилище | SQLite на VPS | локальный `data/delphi_press.db` |
| Аутентификация | OpenRouter API key | `claude setup-token` (Max session) |
| Failure mode | OpenRouter 5xx → fallback-модели | CLI timeout/crash → retry SDK |

Всё остальное — тот же pipeline, те же агенты, те же промпты.

## Known gotchas

1. **Sequential mode для persona stages.** Пять персон в R1/R2 запускаются последовательно (а не параллельно), чтобы избежать thrashing SDK subprocess. `max_concurrency=2` работает приемлемо; при `4+` встречаются таймауты.
2. **Stage timeouts подняты до 1800s** в `scripts/dry_run.py` — sequential mode медленнее параллельного OpenRouter. Подробнее: CHANGELOG v0.9.9.
3. **Cost tracking возвращает 0.0.** Это ожидаемо — Max подписка не даёт per-call биллинг. Бюджетный трекер не срабатывает.
4. **Judge остаётся детерминированным.** Stage 6 не вызывает LLM даже в Claude Code mode — агрегация через market-weighted median.
5. **Claude Code CLI session timeout.** После ~6 часов idle сессия может истечь. Перезапустить через `claude setup-token`.
6. **Claude Code mode не параллелится на нескольких машинах.** Один user — одна подписка — одна машина в моменте.

## Ссылки

- `src/llm/providers.py` → `ClaudeCodeProvider`
- `src/llm/router.py` → `CLAUDE_CODE_ASSIGNMENTS`
- `.claude/skills/predict/SKILL.md` → executable контракт скилла
- `scripts/dry_run.py` → headless CLI entry point
- `docs-site/docs/architecture/llm.md` → общая LLM-инфраструктура
- `CHANGELOG.md` v0.9.8–v0.9.9 — история внедрения
