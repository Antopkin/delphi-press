# Новые возм��жности Claude Code (Jan–Apr 2026)

> Дата: 2026-04-05. Источники: официальный changelog v2.1.0–v2.1.92, GitHub releases, Threads.

## Источники

1. [Changelog — Claude Code Docs](https://code.claude.com/docs/en/changelog)
2. [GitHub Releases: anthropics/claude-code](https://github.com/anthropics/claude-code/releases)
3. [Hooks Reference](https://code.claude.com/docs/en/hooks)
4. [Agent Teams](https://code.claude.com/docs/en/agent-teams)
5. [Claude Code Q1 2026 Roundup — MindStudio](https://www.mindstudio.ai/blog/claude-code-q1-2026-update-roundup)
6. [Every Claude Code Update March 2026 — Builder.io](https://www.builder.io/blog/claude-code-updates)
7. [Boris Cherny Threads: v2.1.0](https://www.threads.com/@boris_cherny/post/DTOyRyBD018/)

---

## Хронология (ключевые релизы)

| Дата | Версия | Фича | Релевантность |
|------|--------|------|---------------|
| 2026-01-07 | v2.1.0 | Hooks in frontmatter, skill hot reload, wildcard permissions | Высокая |
| 2026-02-19 | v2.1.49 | `--worktree` флаг, ConfigChange hook, MCP OAuth step-up | Высокая |
| 2026-02-20 | v2.1.50 | `isolation: worktree` для агентов, `claude agents` CLI | Высокая |
| 2026-02-26 | v2.1.59 | Auto-memory system, `/memory` management | Высокая |
| 2026-02-28 | v2.1.63 | `/batch` command, HTTP hooks | Высокая |
| 2026-03-04 | v2.1.68 | Opus 4.6 medium effort default, "ultrathink" keyword | Высокая |
| 2026-03-07 | v2.1.71 | `/loop` recurring commands, cron tools, voice STT Russian | Высокая |
| 2026-03-13 | v2.1.75 | **1M context Opus 4.6** | Уже используем |
| 2026-03-14 | v2.1.76 | MCP elicitation, PostCompact hook, worktree.sparsePaths | Высокая |
| 2026-03-17 | v2.1.77 | **64k/128k output tokens** Opus 4.6 | Высокая |
| 2026-03-25 | v2.1.83 | CwdChanged/FileChanged hooks, managed-settings.d/ | Средняя |
| 2026-03-26 | v2.1.85 | **Conditional hooks** (`if` fields) | Высокая |
| 2026-04-01 | v2.1.89 | PermissionDenied hook, named subagents | С��едняя |
| 2026-04-02 | v2.1.91 | **MCP result persistence** (500K chars) | Высокая |
| 2026-04-04 | v2.1.92 | Per-model cost breakdown, subagent bugfix | Высокая |

---

## Фичи высокой релевантности

### 1. Worktree-изоляция для субагентов

**v2.1.49–v2.1.50 (февраль 2026)**

Агенты получают изолированный git worktree. Активация: `isolation: worktree` в frontmatter или `claude --worktree`.

**Для Delphi Press:** `/predict` запускает 5 персон последовательно. С worktree — пара��лельно, каждый в изоляции. Потенциальный выигрыш: 5x на стадии генерации.

### 2. Agent Teams (experimental)

**v2.1.32+ (experimental)**

Принципиально новая архитектура: тиммейты общаются напрямую через mailbox, совместно управляют task list, каждый в 1M контексте. Требует: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

**Для Delphi Press:** Дельфи-пайплайн — ровно задача для agent teams: 5 персон + cross-persona обмен перед R2.

### 3. Conditional hooks (`if` field)

**v2.1.85 (март 2026)**

```json
{
  "if": "Edit(src/**/*.py)",
  "type": "command",
  "command": "ruff format ${file}"
}
```

Ху��и фильтруются ДО выполнения. Снижает overhead текущих 6 хуков.

### 4. Новые hook-��обытия (9 новых)

| Hook | Версия | Назначение |
|------|--------|-----------|
| ConfigChange | v2.1.49 | Изменение конфига |
| WorktreeCreate/Remove | v2.1.50 | Worktree lifecycle |
| InstructionsLoaded | v2.1.69 | CLAUDE.md загружен |
| PostCompact | v2.1.76 | После компакции |
| StopFailure | v2.1.78 | API-ошибка |
| CwdChanged | v2.1.83 | Смена директории |
| FileChanged | v2.1.83 | Файл изменён |
| TaskCreated | v2.1.84 | Задача создана |
| PermissionDenied | v2.1.89 | Auto-mode отклонил |

### 5. MCP result persistence (500K chars)

**v2.1.91 (апрель 2026)**

MCP-инструменты возвращают до 500K символов без усечения. Критично для больших схем и JSON.

### 6. Hooks in frontmatter

**v2.1.0 (ян��арь 2026)**

Хуки PreToolUse/PostToolUse/Stop прямо в SKILL.md. Scope-изоляция: работают только в рамках скилла.

**Для Delphi Press:** Добавить валидацию Pydantic-вывода в predict-скилле.

### 7. Auto-memory system

**v2.1.59 (февраль 2026)**

Автозапись предпочтений между сессиями. `/memory` для управления. `autoMemoryDirectory` для к��стомного расположения.

### 8. 64k/128k output tokens

**v2.1.77 (март 2026)**

Default 64k, max 128k для Opus 4.6. Снимает ограничения при длинных аналитических текстах.

### 9. Per-model cost breakdown

**v2.1.92 (апрель 2026)**

`/cost` показывает стоимость по моделям с cache-hit. Полезно для оценки стоимости predict-субагентов.

---

## Фичи средней релевантности

- **Scheduled Cloud Tasks** — задачи по расписанию на Anthropic-облаке (Pro/Max)
- **/loop command** (v2.1.71) — рекуррентные команды (`/loop 5m check deploy`)
- **Remote Control** (v2.1.69) — продолжение сессии с телефона/браузера
- **/batch** (v2.1.63) — 5-30 параллельных задач в worktrees
- **"ultrathink"** (v2.1.68) — максимальный effort на следующий turn
- **HTTP hooks** (v2.1.63) — POST JSON на URL вместо shell
- **Voice STT Russian** (v2.1.71) — голосовой ввод на русском
- **MCP Tool Search** — lazy loading при >10% context overhead

---

## Что уже используется

| Фича | Статус |
|------|--------|
| Skills (27) | ✅ |
| Hooks (6 events) | ✅ |
| Wildcard permissions | ✅ |
| Deny permissions | ✅ |
| Rules (4 файла) | ✅ |
| MCP серверы (7) | ✅ |
| Manual memory | ✅ |
| Opus 4.6 + 1M context | ✅ |
| Субагенты | ✅ |

## Что НЕ используется (но доступно)

- Conditional hooks (`if` field)
- Agent Teams
- Auto-memory system
- HTTP hooks
- Frontmatter hooks в скиллах
- `isolation: worktree`
- `/loop`, `/batch`, `/simplify`
- MCP Tool Search
- "ultrathink" keyword
- StopFailure/PostCompact/InstructionsLoaded hooks

---

## Рекомендации

### P1 — немедленно
1. **Conditional hooks** (`if`) — снизить overhead существующих хуков
2. **StopFailure hook** — обработка API-ошибок в predict
3. **"ultrathink"** в критичных промптах — нулевая стоимость, прирост качества

### P2 — текущий спринт
4. **`isolation: worktree`** в predict-субагентах — параллельность
5. **Frontmatter hooks** в predict SKILL.md — валидация вывода
6. **MCP Tool Search** (`ENABLE_TOOL_SEARCH=1`) — снижение контекста

### P3 — исследовать
7. **Agent Teams** — кандидат для переписи predict при стабилизации
8. **Scheduled Cloud Tasks** — авто dry_run по расписанию
9. **Auto-memory** — оценить совместимость с ручной memory
