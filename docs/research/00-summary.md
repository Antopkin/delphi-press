# Сводка: Best Practices Claude Code для Delphi Press

**Дата:** 27 марта 2026
**Подробности:** 01-workflows.md, 02-skills-tools.md, 03-documentation.md, 04-architecture.md, 05-memory-config.md

---

## Ключевые выводы

1. **Одна сессия = один модуль.** Контекст деградирует через ~90 мин. `/compact` каждые 25-30 мин. `/clear` при переключении между модулями.

2. **CLAUDE.md < 200 строк.** Каждая строка: "без неё Claude ошибётся?" — если нет, удалить. Детали — в `.claude/rules/` с path-scoping.

3. **Тесты-контракты ДО реализации.** Карта тестов снижает регрессии на 72% (TDAD, arxiv, март 2026). Pydantic-схемы тестировать первыми.

4. **Google-style docstrings + module-level docstrings.** Двойной интерфейс: человек + LLM. Ссылка на спеку в module docstring.

5. **settings.json > CLAUDE.md для ограничений.** CLAUDE.md "советует", settings.json принуждает. Защита .env через `permissions.deny`.

6. **Spec drift — главный риск.** PR-правило: меняешь контракт (Pydantic-схема, сигнатура) → обнови `docs/*.md`.

7. **Protocol > ABC** для DI в Python. Мок LLM без наследования. Unit-тесты мгновенные и бесплатные.

8. **Custom asyncio orchestrator** — правильный выбор. LangGraph/CrewAI избыточны для детерминированного пайплайна.

---

## Action Items для Foresighting News

### Сделать ДО начала имплементации

| # | Действие | Приоритет | Файл |
|---|----------|-----------|------|
| 1 | Создать `.claude/settings.json` с `permissions.deny` для `.env` | Высокий | 05 |
| 2 | Создать `.claude/rules/` (4 файла: async, pydantic, llm, testing) | Высокий | 04, 05 |
| 3 | Добавить SQLite MCP сервер | Высокий | 02 |
| 4 | Добавить Context7 MCP для актуальных доков FastAPI/Pydantic | Высокий | 02 |
| 5 | Написать тесты-контракты для всех Pydantic-схем | Высокий | 04 |
| 6 | Создать HANDOVER.md (шаблон для межсессионных переключений) | Средний | 03 |
| 7 | Добавить в CLAUDE.md навигацию "src/* → docs/*" | Средний | 03 |
| 8 | Добавить в CLAUDE.md формат docstrings (Google-style) | Средний | 03 |

### Сделать при начале каждой сессии

| # | Действие | Источник |
|---|----------|----------|
| 1 | `/rename <module-name>` — именование сессии | 01 |
| 2 | Прочитать спеку модуля из `docs/` | 04 |
| 3 | Обновить HANDOVER.md из предыдущей сессии | 03 |
| 4 | Написать 2-3 теста (Red Phase) до реализации | 04 |
| 5 | Промпт: "Реализуй X по docs/Y. Тесты: tests/Z. Начни с чтения." | 01 |

### Сделать в ходе реализации

| # | Действие | Источник |
|---|----------|----------|
| 1 | `/compact` каждые 25-30 мин | 01 |
| 2 | Субагенты для параллельных коллекторов (Stage 1) | 01 |
| 3 | Git worktrees для frontend + backend параллельно | 01 |
| 4 | Module-level docstrings со ссылкой на спеку | 03 |
| 5 | Inline-комментарии: только "почему" (архитектурные решения) | 03 |
| 6 | PR-правило: меняешь контракт → обнови спеку | 03 |

### Опционально (если хватит времени)

| # | Действие | Приоритет |
|---|----------|-----------|
| 1 | Создать skill `/new-agent` (шаблон по спеке) | Средний |
| 2 | Создать `.claude/agents/agent-reviewer.md` | Средний |
| 3 | Создать `.claude/agents/cost-auditor.md` (model: haiku) | Средний |
| 4 | GitHub Actions `claude-code-action@v1` для code review | Низкий |
| 5 | `CLAUDE_CODE_TASK_LIST_ID=foresighting-news` для общих задач | Низкий |

---

## Конкретные конфигурации для немедленного применения

### `.claude/settings.json`

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(uv run *)",
      "Bash(pytest *)",
      "Bash(ruff *)",
      "Bash(docker compose *)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git status)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)"
    ]
  },
  "autoMemoryEnabled": true,
  "language": "russian"
}
```

### MCP серверы

```bash
# SQLite для работы с БД
claude mcp add --scope project sqlite -- npx @modelcontextprotocol/server-sqlite ./data/foresighting.db

# Context7 для актуальных доков
claude mcp add --transport http context7 https://mcp.context7.com/mcp
```

### Дополнение CLAUDE.md

```markdown
## Навигация по спекам

- src/agents/* → docs/02-agents-core.md, 03-collectors.md, 04-analysts.md
- src/agents/forecasters/* → docs/05-delphi-pipeline.md
- src/llm/* → docs/07-llm-layer.md
- src/api/*, src/db/* → docs/08-api-backend.md
- src/schemas/* → соответствующие спеки по модулю

## Формат docstrings

Google-style. Module-level docstring обязателен (стадия, спека, контракт).
```

### Последовательность сессий

```
Сессия 1:  src/schemas/ + src/config.py       # /rename foresighting-schemas
Сессия 2:  src/llm/                            # /rename foresighting-llm
Сессия 3:  src/agents/base.py + registry       # /rename foresighting-agents-core
Сессия 4:  src/agents/collectors/              # /rename foresighting-collectors
Сессия 5:  src/agents/analysts/                # /rename foresighting-analysts
Сессия 6:  src/agents/forecasters/             # /rename foresighting-delphi
Сессия 7:  src/agents/generators/              # /rename foresighting-generators
Сессия 8:  src/data_sources/                   # /rename foresighting-datasources
Сессия 9:  src/api/ + src/db/                  # /rename foresighting-api
Сессия 10: src/web/                            # /rename foresighting-frontend
Сессия 11: Docker + интеграция                 # /rename foresighting-deploy
```

---

## Источники (по файлам)

**01-workflows.md:** официальная документация Claude Code, claudefa.st, Builder.io, DataCamp
**02-skills-tools.md:** Claude Code Docs, awesome-claude-code, MCPcat, SmartScope
**03-documentation.md:** Arglee/Medium, Glean, Drew Breunig, J.D. Hodges
**04-architecture.md:** TDAD/arxiv, qaskills.sh, dasroot.net, onehorizon.ai
**05-memory-config.md:** Claude Code Docs, Raj Rajhans, eesel.ai, Avi Chawla
