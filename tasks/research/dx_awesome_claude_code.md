# Экосистема Claude Code — awesome-claude-code и инструменты

> Research date: 2026-04-05

## Источники

1. [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) — 21 600 stars
2. [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit) — 135 агентов, 176+ плагинов
3. [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) — 130+ субагентов
4. [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — 16 000 stars
5. [SuperClaude-Org/SuperClaude_Framework](https://github.com/SuperClaude-Org/SuperClaude_Framework) — 30 команд
6. [carlrannaberg/claudekit](https://github.com/carlrannaberg/claudekit) — хуки + команды + субагенты
7. [trailofbits/skills](https://github.com/trailofbits/skills) — 41 security skill
8. [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) — эталонные MCP
9. [github/github-mcp-server](https://github.com/github/github-mcp-server) — официальный GitHub MCP
10. [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp) — Sentry MCP

---

## Категоризированный список инструментов

### Skills

| Название | Описание | Ссылка |
|----------|----------|--------|
| Trail of Bits Security Skills (41) | Security audit, CodeQL/Semgrep, supply chain | [trailofbits/skills](https://github.com/trailofbits/skills) |
| SuperClaude (30 команд) | Полный SDLC: research, implement, test, pm | [SuperClaude-Org](https://github.com/SuperClaude-Org/SuperClaude_Framework) |
| claudekit code-review | 6 параллельных агентов ревью | [claudekit](https://github.com/carlrannaberg/claudekit) |
| Context Engineering Kit | Минимальный token footprint | awesome-cc |
| VoltAgent субагенты (130+) | 10 категорий: core dev, infra, security, data, DX | [VoltAgent](https://github.com/VoltAgent/awesome-claude-code-subagents) |

### MCP серверы

| MCP сервер | Категория | Описание |
|------------|-----------|----------|
| GitHub MCP (официальный) | Git/Code | PRs, issues, CI/CD, OAuth scope filtering |
| Git MCP (reference) | Git/Code | Локальные git-операции (12 инструментов) |
| SQLite MCP | Database | Управление SQLite: таблицы, схемы, CRUD |
| PostgreSQL MCP | Database | Natural language запросы |
| Memory MCP (knowledge graph) | Memory | Персистентная память: entities, relations |
| Sentry MCP | Monitoring | Error tracking, stack traces, Seer analysis |
| Docker MCP | Infrastructure | Управление контейнерами, images, volumes |
| Context7 MCP | Documentation | Official docs lookup в реальном времени |
| Sequential Thinking MCP | Reasoning | Multi-step reasoning через цепочки |

### Plugins (official ecosystem)

| Плагин | Назначение |
|--------|-----------|
| code-review | Архитектура, безопасность, производительность |
| test-writer-fixer | Автосоздание тестов (Pytest) |
| ship | End-to-end PR: lint → test → review → deploy |
| commit | Smart git commits (conventional format) |
| changelog-generator | Release notes из коммитов |
| perf | Анализ производительности |
| debugger | Advanced debugging |

### Фреймворки

| Фреймворк | Описание |
|-----------|----------|
| SuperClaude | 30 команд, 20 персон, 8 MCP |
| claudekit | Хуки + команды + субагенты |
| Claude Squad | Несколько агентов в изолированных worktrees |
| Claude Task Master | Task management для AI-driven dev |

---

## Top-5 must-have для Delphi Press

| # | Инструмент | Тип | Зачем нужен | Ссылка |
|---|-----------|-----|-------------|--------|
| 1 | **Sentry MCP** | MCP | Production мониторинг без SSH. Claude читает stack traces и предлагает фиксы | [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp) |
| 2 | **GitHub MCP** | MCP | PRs, issues, CI статусы без переключения контекста. OAuth безопаснее PAT | [github/github-mcp-server](https://github.com/github/github-mcp-server) |
| 3 | **Memory MCP** | MCP | Knowledge graph между сессиями: архитектурные решения, pipeline gotchas | [modelcontextprotocol/servers/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) |
| 4 | **Trail of Bits Security Skills** | Skills | 41 плагин: static analysis, supply chain, insecure defaults | [trailofbits/skills](https://github.com/trailofbits/skills) |
| 5 | **claudekit хуки** | Framework | typecheck + lint + test при каждом изменении .py | [claudekit](https://github.com/carlrannaberg/claudekit) |

---

## Что мы уже используем

### Skills (27)
- 20 Impeccable design skills
- `/predict` (Дельфи-пайплайн, 5 субагентов)
- `/triage-issue`, `/ubiquitous-language`, `/request-refactor-plan`

### MCP серверы (7)
jina, exa, yandex-search, playwright, paper-search, zotero, transcript

### Hooks (6)
bash safety, file protection, TDD warning, auto-format, notifications (Stop/SubagentStop/PreCompact)

### Rules (4)
agents-llm.md, async-patterns.md, pydantic-schemas.md, testing.md

---

## Пробелы

1. **MCP мониторинга** — нет Sentry/Datadog. Production без прямой связи с системой ошибок.
2. **GitHub MCP** — git через Bash, но GitHub MCP добавляет структурированный доступ к PRs/issues.
3. **Персистентная память через граф** — MEMORY.md работает, Memory MCP добавит полнотекстовый поиск.
4. **Проверка типов при изменениях** — auto-format есть, mypy/pyright на каждое изменение нет.
5. **Security skills** — audit ручной, Trail of Bits автоматизирует.

---

## Реестры MCP-серверов

| Ресурс | Серверов | Особенности |
|--------|----------|-------------|
| [Smithery.ai](https://smithery.ai/) | 7 300+ | CLI-установка, хостинг |
| [Docker MCP Catalog](https://hub.docker.com/mcp) | 270+ | Изолированные контейнеры |
| [MCP Registry (Anthropic)](https://registry.modelcontextprotocol.io) | официальный | Верифицированные серверы |
| [claudemarketplaces.com](https://claudemarketplaces.com/) | 770+ MCP | Community voting |
