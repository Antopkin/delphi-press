# For Agents — start here

Агент читает эту страницу первой, чтобы сориентироваться. Укороченный обзор Delphi Press под контекст-бюджет.

## Что это в 5 предложений

1. Delphi Press прогнозирует заголовки СМИ для заданной целевой даты.
2. Мультиагентный пайплайн в 9 стадиях: сбор → анализ → Delphi R1 → Mediator → Delphi R2 → Judge → Framing → Generation → QualityGate.
3. Три режима исполнения: Web UI (OpenRouter, $5–15), Claude Code mode (Max подписка, $0), CLI (headless Claude Code mode).
4. Все 5 экспертных персон используют Claude Opus 4.6; разнообразие — через промпты и когнитивные смещения, не через модели.
5. Inverse problem («wisdom of the informed»): профилируем 470M+ исторических ставок Polymarket, агрегируем только информированных игроков — BSS +0.196 vs. сырые рынки.

## Landmarks — файлы, которые нужно знать

| Что | Файл |
|---|---|
| Orchestrator (9 стадий) | `src/agents/orchestrator.py` |
| LLM provider (OpenRouter + Claude Code) | `src/llm/providers.py` |
| Routing (CLAUDE_CODE_ASSIGNMENTS) | `src/llm/router.py` |
| DB incremental callback | `src/db/stage_persistence.py` |
| Pipeline spec | [architecture/pipeline.md](architecture/pipeline.md) |
| Pydantic schemas | `src/schemas/` |
| Predict skill (NL trigger) | `.claude/skills/predict/SKILL.md` |
| Dry run (CLI entry) | `scripts/dry_run.py` |
| Agents | `src/agents/` (collectors, analysts, forecasters, generators) |
| LLM prompts | `src/llm/prompts/` |

## Где что искать в документации

| Вопрос | Страница |
|---|---|
| «Как устроен pipeline?» | [architecture/pipeline.md](architecture/pipeline.md) |
| «Какая модель на какой задаче?» | [architecture/llm.md](architecture/llm.md) |
| «Что такое Claude Code mode?» | [architecture/claude-code-mode.md](architecture/claude-code-mode.md) |
| «Как работают раунды Дельфи?» | [delphi-method/delphi-rounds.md](delphi-method/delphi-rounds.md) |
| «Что значит "inverse problem"?» | [methodology/superforecasters.md](methodology/superforecasters.md) + [polymarket/inverse.md](polymarket/inverse.md) |
| «Как читается Brier Score / BSS?» | [evaluation/metrics.md](evaluation/metrics.md) |
| «Что такое `медиация` / `нить` / `фрейминг`?» | [appendix/glossary.md](appendix/glossary.md) |
| «Что уже сломалось и как?» | [dead-ends/case-studies.md](dead-ends/case-studies.md) + [appendix/gotchas.md](appendix/gotchas.md) |
| «Почему было принято решение X?» | [adr/index.md](adr/index.md) |
| «Какие команды для запуска?» | [infrastructure/scripts.md](infrastructure/scripts.md) |
| «Какая REST-схема?» | [api/reference.md](api/reference.md) |

## Conventions (TL;DR)

- **Async everywhere** (`httpx.AsyncClient`, `aiosqlite`, ARQ)
- **Pydantic v2** для всех схем агентов в `src/schemas/`
- **`AgentResult`** — frozen dataclass: `{success, data, cost_usd, tokens_in/out, duration_ms, error}`
- **Module-level docstring обязателен**: роль + `Спека: docs-site/...` + `Контракт: Вход/Выход`
- **Absolute imports** от `src.`: `from src.schemas.prediction import PredictionRequest`
- Детальнее: [conventions/code-style.md](conventions/code-style.md)

## Быстрые команды

```bash
npm run css:build                                       # собрать Tailwind
uv run uvicorn src.main:app --reload --port 8000       # dev-сервер
uv run arq src.worker.WorkerSettings                    # worker
uv run pytest tests/ -v                                 # тесты
ruff format src/ tests/ && ruff check src/ --fix       # линт
cd docs-site && uv run mkdocs build --strict           # собрать доки
```

Полный справочник: [infrastructure/scripts.md](infrastructure/scripts.md).

## Куда писать новый контекст

| Что | Куда |
|---|---|
| Архитектурное решение | новый [ADR](adr/index.md) |
| Новый модуль / стадия pipeline | обновить [architecture/pipeline.md](architecture/pipeline.md) + inline docstring |
| Нестандартная ошибка, которую словили | [dead-ends/case-studies.md](dead-ends/case-studies.md) |
| Новый доменный термин | [appendix/glossary.md](appendix/glossary.md) |
| Правило, которое Claude должен знать в конкретной директории | `.claude/rules/*.md` с `paths:` frontmatter |
| Команды, которые Claude не выведет сам | `CLAUDE.md` (коротко) + [infrastructure/scripts.md](infrastructure/scripts.md) (детально) |

Детальнее: [conventions/contributing-docs.md](conventions/contributing-docs.md).
