# Delphi Press

Веб-продукт прогнозирования заголовков СМИ. Мультиагентный Дельфи-пайплайн (5 персон, 2 раунда).

**Три режима:**
- **Web UI** — OpenRouter, пользователь вводит свой ключ, JWT. Web UI работает на VPS.
- **Claude Code mode** — predict skill, Max подписка, $0/прогноз. Полное описание: @docs-site/docs/architecture/claude-code-mode.md.
- **CLI** — `scripts/dry_run.py --provider claude_code`, headless-вариант Claude Code mode.

## Landmarks (файлы, о которых Claude должен знать)

- Orchestrator: `src/agents/orchestrator.py` — 9 стадий, 28 LLM-задач
- LLM providers: `src/llm/providers.py` → `OpenRouterClient`, `ClaudeCodeProvider`
- Routing: `src/llm/router.py` → `DEFAULT_ASSIGNMENTS`, `CLAUDE_CODE_ASSIGNMENTS`
- DB callback: `src/db/stage_persistence.py` — shared между worker и dry_run
- Pydantic schemas: `src/schemas/`
- Pipeline spec: @docs-site/docs/architecture/pipeline.md
- Predict skill: `.claude/skills/predict/SKILL.md`
- Dry run: `scripts/dry_run.py`

## Documentation — docs-site = SSOT

- **Start here (agent entry):** @docs-site/docs/for-agents.md
- Architecture: @docs-site/docs/architecture/pipeline.md · @docs-site/docs/architecture/llm.md · @docs-site/docs/architecture/claude-code-mode.md
- Methodology: @docs-site/docs/methodology/
- Glossary: @docs-site/docs/appendix/glossary.md
- ADRs (decision records): @docs-site/docs/adr/index.md
- Commands: @docs-site/docs/infrastructure/scripts.md
- Code style: @docs-site/docs/conventions/code-style.md
- Full nav: @docs-site/mkdocs.yml

Публичная выкладка: [delphi.antopkin.ru/docs/](https://delphi.antopkin.ru/docs/). Build: `cd docs-site && uv run mkdocs build --strict`.

## Agent memory (persists cross-session)

Помимо этого файла, Claude имеет доступ к `~/.claude/projects/-Users-user-sandbox-delphi-press/memory/MEMORY.md` — локальная, machine-only auto-memory (~30 entries). Содержит feedback-правила, project milestones, пользовательские предпочтения. **Не часть репо**, невидима коллабораторам. Управляется harness'ом автоматически.

## Commands (которые Claude не выведет сам)

```bash
npm run css:build                                       # собрать Tailwind
uv run uvicorn src.main:app --reload --port 8000       # dev-сервер
uv run arq src.worker.WorkerSettings                    # worker
uv run pytest tests/ -v                                 # тесты
ruff format src/ tests/ && ruff check src/ --fix       # линт
cd docs-site && uv run mkdocs build --strict           # собрать доки
docker compose up -d                                    # production
```

Детальный справочник всех скриптов: @docs-site/docs/infrastructure/scripts.md.

## Правила кода (TL;DR)

- **Async everywhere** (httpx, aiosqlite, ARQ)
- **Pydantic v2** для схем (`src/schemas/`)
- **AgentResult** — frozen dataclass; агенты не бросают исключения
- **Module-level docstring обязателен**: роль + `Спека: docs-site/...` + `Контракт:`
- **Absolute imports** от `src.`

Полная спецификация: @docs-site/docs/conventions/code-style.md.
Path-scoped правила: `.claude/rules/*.md` (`agents-llm.md`, `async-patterns.md`, `pydantic-schemas.md`, `testing.md`, `frontend-design.md`).

## Синхронизация документации

При изменении публичных контрактов:

- Новая Pydantic-схема → обновить `src/schemas/` docstring + если контракт меняется — страницу в `docs-site/docs/architecture/` или `api/`
- Новый агент / LLM-задача → @docs-site/docs/architecture/pipeline.md + @docs-site/docs/architecture/llm.md
- Архитектурное решение → новый ADR в @docs-site/docs/adr/
- Bug fix с выводом → @docs-site/docs/dead-ends/case-studies.md

Полный routing map: @docs-site/docs/conventions/contributing-docs.md.

## Frontend design (Impeccable)

20 design-скиллов активируются при работе в `src/web/` (стек: Tailwind v4 + fn-* components + Newsreader/Source Sans 3/JetBrains Mono). Первый запуск: `/teach-impeccable` → `.impeccable.md`. Список команд и активация — в `.claude/rules/frontend-design.md` (paths-scoped).

<!-- CLAUDE.md target: <=150 lines. Last review: 2026-04-18. Если при чтении возникает дублирование с docs-site — сокращать здесь, не там. -->
