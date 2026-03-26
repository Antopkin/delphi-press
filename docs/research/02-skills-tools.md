# Skills, MCP Серверы и Hooks для Claude Code — Март 2026

**Дата исследования:** 27 марта 2026
**Источники:** официальная документация Anthropic + community-публикации марта 2026

---

## Резюме

Экосистема Claude Code: Skills (SKILL.md) для переиспользуемых инструкций, Hooks (24 события) для детерминированной автоматизации, MCP серверы для интеграции с внешними инструментами. Community: 1300+ skills, 50+ MCP серверов. Для Foresighting News приоритетны: SQLite MCP, Context7 MCP, PostToolUse hook для ruff, GitHub Actions `@claude`.

---

## 1. Skills: SKILL.md

**Источник:** [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)

`.claude/commands/` объединён со Skills. Файл `.claude/skills/<name>/SKILL.md` создаёт `/slash-command`.

**Поля фронтматтера:**

| Поле | Описание |
|------|----------|
| `name` | Имя команды (строчные, дефисы) |
| `description` | Подсказка для автоактивации |
| `disable-model-invocation: true` | Только ручной вызов |
| `allowed-tools` | Ограничить инструменты |
| `context: fork` | Запустить в subagent |
| `model` | Переопределить модель |

**Bundled skills:** `/batch`, `/claude-api`, `/debug`, `/loop`, `/simplify`

```yaml
---
name: run-tests
description: Запуск тестов проекта
disable-model-invocation: true
allowed-tools: Bash
---
Запусти: `uv run pytest tests/ -v`
Покажи только FAILED с трейсбеком.
```

---

## 2. Community Skills

**Источники:** [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code), [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit), [sickn33/antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills)

| Репозиторий | Контент |
|-------------|---------|
| `hesreallyhim/awesome-claude-code` | Curated реестр: skills, hooks, MCP |
| `rohitg00/awesome-claude-code-toolkit` | 135 агентов, 35 skills, 42 команды, 19 hooks |
| `sickn33/antigravity-awesome-skills` | 1304+ skills + installer CLI |

Примечательные: Trail of Bits Security Skills (12+), Fullstack Dev Skills (65), RIPER Workflow.

---

## 3. MCP серверы для Python-разработки

**Источники:** [mcpcat.io](https://mcpcat.io/guides/best-mcp-servers-for-claude-code/), [claudefa.st](https://claudefa.st/blog/tools/mcp-extensions/best-addons), [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp)

MCP Tool Search — lazy loading, снижение расхода контекста до 95%.

```bash
claude mcp add <name> -- <command>                  # stdio
claude mcp add --transport http <name> <url>        # HTTP
claude mcp add --scope project <name> -- <command>  # для проекта
```

**Топ серверы:**

| Сервер | Назначение | Установка |
|--------|------------|-----------|
| **SQLite** | Запросы к БД | `claude mcp add sqlite -- npx @modelcontextprotocol/server-sqlite ./db.sqlite` |
| **Context7** | Актуальная документация | `claude mcp add --transport http context7 https://mcp.context7.com/mcp` |
| **GitHub** | PRs, Issues, CI/CD | `claude mcp add --transport http github https://api.githubcopilot.com/mcp/` |
| **Sequential Thinking** | Многошаговое рассуждение | `claude mcp add seq-think npx -- -y @modelcontextprotocol/server-sequential-thinking` |
| **Playwright** | Browser automation | `claude mcp add playwright npx -- @playwright/mcp@latest` |
| **Fetch** | Загрузка веб-страниц | `claude mcp add fetch -- npx @modelcontextprotocol/server-fetch` |
| **Memory** | Персистентная память | `claude mcp add memory -- npx @modelcontextprotocol/server-memory` |

**Проектный `.mcp.json`:**

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-sqlite", "./data/foresighting.db"]
    },
    "context7": {
      "transport": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

---

## 4. Hooks: 24 события жизненного цикла

**Источники:** [code.claude.com/docs/en/hooks-guide](https://code.claude.com/docs/en/hooks-guide), [smartscope.blog — March 2026](https://smartscope.blog/en/generative-ai/claude/claude-code-hooks-guide/)

Три типа обработчиков: `command` (shell), `prompt` (LLM), `agent` (subagent).

**Ключевые события:**

| Событие | Когда | Блокируемый |
|---------|-------|-------------|
| `PreToolUse` | До инструмента | Да (exit 2) |
| `PostToolUse` | После инструмента | Нет |
| `Stop` | Завершение ответа | Нет |
| `SessionStart` | Начало сессии | Нет |
| `PreCompact` / `PostCompact` | Компакция | Нет |
| `SubagentStart` / `SubagentStop` | Lifecycle subagent | Нет |

**Коды выхода:** `0` = продолжить, `2` = заблокировать, другие = ошибка.

**Пример конфигурации для Python-проекта:**

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "FILE=$(jq -r '.tool_input.file_path // empty'); echo \"$FILE\" | grep -q '\\.py$' && uv run ruff format \"$FILE\" && uv run ruff check --fix \"$FILE\" || true"
      }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "CMD=$(jq -r '.tool_input.command'); echo \"$CMD\" | grep -qE 'rm -rf|DROP TABLE|git push --force' && { echo 'Blocked' >&2; exit 2; } || exit 0"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "osascript -e 'display notification \"Задача выполнена\" with title \"Claude Code\"'",
        "async": true
      }]
    }]
  }
}
```

---

## 5. IDE интеграции

**Источники:** [code.claude.com/docs/en/vs-code](https://code.claude.com/docs/en/vs-code), [JetBrains Marketplace](https://plugins.jetbrains.com/plugin/27310-claude-code-beta-)

- **VS Code** (рекомендован): нативный GUI, `@-mention` файлов, auto-accept правок
- **JetBrains** (Beta): CLI в терминале + нативный diff-viewer
- **Community:** `claude-code.nvim`, `claude-code.el`

---

## 6. GitHub Actions и CI/CD

**Источники:** [code.claude.com/docs/en/github-actions](https://code.claude.com/docs/en/github-actions), [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action)

`claude-code-action@v1` — официальный GitHub Action (6.3k+ stars).

```yaml
name: Claude Review
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: "Проверь PR: типизация, Pydantic, async/await, AgentResult pattern."
          claude_args: "--max-turns 5 --model claude-sonnet-4-6"
```

Быстрая настройка: `/install-github-app` в Claude Code CLI.

---

## Рекомендации для Foresighting News

1. **SQLite MCP** (высокий): `claude mcp add --scope project sqlite -- npx @modelcontextprotocol/server-sqlite ./data/foresighting.db`
2. **Context7 MCP** (высокий): актуальные доки FastAPI/Pydantic v2/ARQ
3. **Укрепить hooks**: `SessionStart` для реинжекции стека после compaction, `"async": true` для Stop
4. **Проектные skills**: `run-tests`, `new-agent` (шаблон по спеке из docs/), `check-costs`
5. **GitHub Actions** (низкий для соло): автоматический review на PR

---

## Источники

1. [Hooks Guide — Claude Code Docs](https://code.claude.com/docs/en/hooks-guide)
2. [Skills — Claude Code Docs](https://code.claude.com/docs/en/skills)
3. [MCP — Claude Code Docs](https://code.claude.com/docs/en/mcp)
4. [GitHub Actions — Claude Code Docs](https://code.claude.com/docs/en/github-actions)
5. [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
6. [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit)
7. [sickn33/antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills)
8. [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action)
9. [MCPcat — Best MCP Servers](https://mcpcat.io/guides/best-mcp-servers-for-claude-code/)
10. [Claudefa.st — 50+ MCP Servers](https://claudefa.st/blog/tools/mcp-extensions/best-addons)
11. [Hooks Guide — SmartScope, March 2026](https://smartscope.blog/en/generative-ai/claude/claude-code-hooks-guide/)
12. [VS Code — Claude Code Docs](https://code.claude.com/docs/en/vs-code)
13. [JetBrains Plugin](https://plugins.jetbrains.com/plugin/27310-claude-code-beta-)
