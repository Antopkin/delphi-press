# Управление контекстом в Claude Code

> Research date: 2026-04-05
> Контекст: Delphi Press v0.9.5, 233 Python файла, 1M context (Opus 4.6)

## Источники

1. [Claude Code Context Window Documentation](https://code.claude.com/docs/en/context-window.md)
2. [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices.md)
3. [Memory and Rules (CLAUDE.md)](https://code.claude.com/docs/en/memory.md)
4. [Skills Documentation](https://code.claude.com/docs/en/skills.md)
5. [Subagents Guide](https://code.claude.com/docs/en/sub-agents.md)
6. [Cost Management](https://code.claude.com/docs/en/costs.md)
7. [How Claude Code Works](https://code.claude.com/docs/en/how-claude-code-works.md)
8. [Claude Code 1M Context Window Guide (2026)](https://claudefa.st/blog/guide/mechanics/1m-context-ga)
9. [Worktree Isolation Best Practices](https://claudefa.st/blog/guide/development/worktree-guide)
10. [GitHub: claude-context MCP](https://github.com/zilliztech/claude-context)
11. [GitHub: claude-ignore PreToolUse Hook](https://github.com/li-zhixin/claude-ignore)

---

## Архитектура контекста

### Что загружается и когда

| Слой | Когда загружается | Размер (tokens) | Контроль |
|------|-------------------|-----------------|----------|
| System prompt | Всегда, при старте | ~5K | Нет |
| CLAUDE.md (project) | Всегда, при старте | ~1-2K | Да (размер файла) |
| CLAUDE.md (global) | Всегда, при старте | ~1-2K | Да |
| `.claude/rules/*.md` | При работе с matching файлами | ~0.5-1K каждый | Да (path-scoping) |
| Memory (MEMORY.md) | Всегда | ~0.5K (индекс) | Да |
| Skills | По запросу/авто-триггер | 1-5K каждый | Да |
| Tool results | При каждом tool call | Варьируется | Частично |
| Conversation history | Накапливается | Растёт | /clear, compaction |

### Context window reality (1M)

- 1M tokens = ~830K usable (после system overhead)
- Auto-compaction: срабатывает при 90%+ заполнении
- При compaction сохраняется: CLAUDE.md, последние сообщения, критический контекст
- Теряется: детали ранних tool calls, промежуточные результаты

---

## .claudeignore для Delphi Press

Файл `.claudeignore` контролирует, какие файлы Claude Code не будет читать/индексировать. Рекомендуемый файл:

```
# Lock files (большие, бесполезные для контекста)
uv.lock
package-lock.json

# Build artifacts
__pycache__/
*.pyc
.ruff_cache/
node_modules/
src/web/static/css/tailwind.css

# Data (большие, не нужны в контексте)
data/
*.parquet
*.sqlite
*.db

# Docker
.docker/

# Docs build output
docs-site/site/

# Environment
.env
.env.*

# Git
.git/

# IDE
.vscode/
.idea/

# Archives (исторические спеки)
docs/*.md
```

**Важно**: `docs/*.md` исключены потому что это архивные спеки с баннерами. Актуальная документация в `docs-site/docs/` — она НЕ исключается.

---

## Rules — текущее состояние и рекомендации

### Текущие 4 файла

| Файл | Path scope | Размер | Оценка |
|------|-----------|--------|--------|
| `agents-llm.md` | `src/agents/**`, `src/llm/**` | ~30 строк | ✅ Хорошо |
| `async-patterns.md` | `src/**/*.py` | ~20 строк | ✅ Хорошо |
| `pydantic-schemas.md` | `src/schemas/**` | ~25 строк | ✅ Хорошо |
| `testing.md` | `tests/**` | ~20 строк | ✅ Хорошо |

### Рекомендации по расширению

Добавить 2 новых rules файла:

**`.claude/rules/frontend.md`:**
```markdown
---
paths:
  - "src/web/**/*.html"
  - "src/web/**/*.js"
  - "src/web/static/**"
---
# Frontend Rules
- Tailwind CSS v4 (@theme config, не v3)
- Компоненты: fn-* prefix
- JS: нативный ES modules
- Шрифты: Newsreader, Source Sans 3, JetBrains Mono
```

**`.claude/rules/deployment.md`:**
```markdown
---
paths:
  - "docker-compose.yml"
  - "Dockerfile"
  - "scripts/deploy.sh"
  - "nginx/**"
---
# Deployment Rules
- Always `docker compose down && up -d` (never --no-deps)
- DuckDB memory limit: 2GB max on 8GB server
- docs_data volume: remove explicitly to pick up new docs
```

---

## CLAUDE.md — оптимизация

### Что убрать (экономия ~25 строк)

1. **Таблица Impeccable (20 команд)** — загружается в каждую сессию, но нужна только при frontend. Вынести в skill.
2. **Правила, дублирующие rules** — async, type hints, pydantic (уже в .claude/rules/)
3. **Версия и тесты** (`v0.9.5. Тесты: 1324`) — устаревают после каждого коммита
4. **IP сервера** — в CLAUDE.local.md

### Что добавить

Секция "Context Strategy":
```markdown
## Context Strategy
- Для исследований → субагенты (Explore, research-analyst)
- Для фронтенда → /frontend-design skill (не загружать при backend)
- Для длинных сессий → /clear между несвязанными задачами
- Для параллельной работы → worktrees (isolation: "worktree")
```

---

## Subagent Delegation Playbook

### Когда основная сессия

- Простые правки (1-3 файла)
- Работа с знакомым кодом
- Коммиты, деплой
- Быстрые вопросы

### Когда субагент

| Задача | Тип субагента | Почему |
|--------|--------------|--------|
| Исследование кодовой базы | Explore | Не загрязняет основной контекст |
| Web research | research-analyst | Результаты WebSearch/WebFetch большие |
| Планирование | Plan | Изолированный контекст для анализа |
| Code review | code-reviewer | Читает много файлов |
| Тестирование | test-runner (custom) | Вывод pytest длинный |
| Frontend design | frontend-developer | Свой набор skills и reference |
| Security audit | security-engineer | Много grepping и analysis |

### Паттерн: Delegation Chain

```
Основная сессия (координация)
  ├── Explore agent → "найди все endpoints в src/api/"
  ├── Plan agent → "спланируй рефакторинг"
  └── code-reviewer → "проверь PR перед мёржем"
```

**Правило**: если задача требует чтения >10 файлов → делегируй субагенту.

---

## Compaction Survival Guide

### Что сохраняется при compaction

- CLAUDE.md (всегда перезагружается)
- Последние ~5 сообщений
- Активные task descriptions
- Plan file (если есть)

### Что теряется

- Детали ранних tool calls
- Содержимое прочитанных файлов
- Промежуточные результаты поиска
- Контекст из субагентов (возвращается только summary)

### Стратегии минимизации потерь

1. **Записывай важное в tasks**: `TaskCreate` для промежуточных результатов
2. **Используй plan mode**: план сохраняется в файле, переживает compaction
3. **Memory для cross-session**: ключевые решения → memory records
4. **Субагенты для "грязной работы"**: Explore, Research → длинные tool outputs не попадают в основной контекст
5. **/clear между несвязанными задачами**: сброс контекста лучше, чем compaction

### Pre-Compaction Hook

Текущий хук (`PreCompact`) играет уведомление. Можно расширить:
```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Context compacting. Saving state...' >&2; date >> ~/.claude/compaction-log.txt"
          }
        ]
      }
    ]
  }
}
```

---

## Worktrees — когда использовать

### Когда worktree

- Задача требует экспериментов с кодом (может не пригодиться)
- Параллельная работа над несвязанными фичами
- Code review с checkout другой ветки
- Длинные задачи (6+ часов)

### Когда НЕ worktree

- Простые правки в 1-3 файлах
- Работа в рамках текущей ветки
- Задачи, зависящие от текущего состояния git

### Использование

```
Agent(isolation="worktree", prompt="...")
```

Worktree создаёт временную копию репозитория. Если агент внёс изменения — возвращается путь и ветка. Если нет — worktree автоматически удаляется.

---

## Метрики контекста

### Мониторинг

- `/context` — показывает текущее использование context window
- Compaction count за сессию — индикатор "грязности" работы
- Количество tool calls — коррелирует с потреблением контекста

### Оптимальная сессия

- 1 задача = 1 сессия (или /clear между задачами)
- <50 tool calls для одной задачи
- 0-1 compaction за сессию
- Субагенты для research/exploration

---

## Конкретный план для Delphi Press

### Quick Wins (1-2 часа)

1. ✅ Создать `.claudeignore` (см. шаблон выше)
2. ✅ Добавить `.claude/rules/frontend.md` с path-scoping
3. ✅ Добавить секцию "Context Strategy" в CLAUDE.md
4. ✅ Начать использовать `/clear` между несвязанными задачами

### Medium Term (1 день)

5. Вынести Impeccable таблицу из CLAUDE.md в skill
6. Добавить `.claude/rules/deployment.md`
7. Расширить PreCompact hook для логирования

### Strategic

8. Настроить subagent delegation patterns в команде
9. Документировать context management practices в CONTRIBUTING.md
