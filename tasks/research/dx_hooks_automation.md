# Хуки Claude Code — продвинутые паттерны

> Research date: 2026-04-05
> Источники: Официальная документация Claude Code, GitHub community, real-world examples

## Резюме

Хуки Claude Code — детерминированные события, срабатывающие в определённых точках жизненного цикла. Они **гарантируют автоматизацию** (в отличие от CLAUDE.md инструкций). Доступно **26 событий**, **4 типа** хуков (command, http, prompt, agent). Текущая конфигурация Delphi Press — базовый уровень (safety, formatting). Рекомендуется 8-12 дополнительных хуков.

---

## 1. Полный справочник Hook Events (26 событий)

| № | Event | Когда | Может блокировать | Matcher |
|---|-------|-------|------------------|---------|
| 1 | `SessionStart` | Начало сессии | Нет | `startup`, `resume`, `clear`, `compact` |
| 2 | `InstructionsLoaded` | CLAUDE.md загружен | Нет | `session_start`, `nested_traversal` |
| 3 | `UserPromptSubmit` | Ввод prompt | Да | (нет matcher) |
| 4 | **`PreToolUse`** | ДО tool call | **Да** | Tool name: `Bash`, `Edit\|Write`, `mcp__.*` |
| 5 | `PermissionRequest` | Permission dialog | Да | Tool name |
| 6 | `PermissionDenied` | Auto mode отклонил | Да | Tool name |
| 7 | `PostToolUse` | ПОСЛЕ tool call | Нет | Tool name |
| 8 | `PostToolUseFailure` | Tool failed | Нет | Tool name |
| 9 | `Notification` | Claude needs input | Нет | `permission_prompt`, `idle_prompt` |
| 10 | `SubagentStart` | Субагент запущен | Нет | `Explore`, `Plan` |
| 11 | `SubagentStop` | Субагент завершился | Нет | Agent type |
| 12 | `TaskCreated` | TaskCreate вызван | Да | (нет matcher) |
| 13 | `TaskCompleted` | Task завершена | Да | (нет matcher) |
| 14 | `Stop` | Claude finish | Да | (нет matcher) |
| 15 | `StopFailure` | Stop из-за API error | Нет | `rate_limit`, `auth_failed` |
| 16 | `TeammateIdle` | Agent team idle | Да | (нет matcher) |
| 17 | `ConfigChange` | Settings изменены | Да | `user_settings`, `project_settings` |
| 18 | `CwdChanged` | `cd` выполнена | Нет | (нет matcher) |
| 19 | `FileChanged` | Watched файл изменился | Нет | `.envrc`, `.env`, `*.md` |
| 20 | `WorktreeCreate` | Git worktree создан | Да | (нет matcher) |
| 21 | `WorktreeRemove` | Git worktree удалён | Нет | (нет matcher) |
| 22 | `PreCompact` | ДО context compaction | Нет | `manual`, `auto` |
| 23 | `PostCompact` | ПОСЛЕ compaction | Нет | `manual`, `auto` |
| 24 | `Elicitation` | MCP запрашивает input | Да | MCP server name |
| 25 | `ElicitationResult` | Ответ на elicitation | Нет | MCP server name |
| 26 | `SessionEnd` | Сессия завершается | Нет | `clear`, `resume`, `logout` |

**Критические для safety:** PreToolUse (только оно может блокировать tool calls)
**Для automation:** PostToolUse, Stop, ConfigChange, FileChanged
**Для integration:** HTTP hooks, Notification

---

## 2. Hook Types (4 типа)

| Тип | Описание | Когда использовать |
|-----|----------|-------------------|
| **command** | Shell script stdin/stdout/exit code | Safety, formatting, logging. Fast, deterministic, no LLM cost |
| **http** | POST JSON на URL → HTTP response | External services (Slack, Telegram, audit) |
| **prompt** | Single LLM call (Haiku default) | Yes/no decisions |
| **agent** | Subagent с tool access (60s, 50t) | Complex verification, file reading, test running |

---

## 3. Текущая конфигурация Delphi Press (аудит)

| Хук | Назначение | Статус | Комментарий |
|-----|-----------|--------|-------------|
| PreToolUse/Bash safety | rm, git push --force, sudo | ✅ Хорошо | Regex хрупкий, нужна валидация |
| PreToolUse/Edit protect | .env, .git/, poetry.lock | ✅ Хорошо | Добавить uv.lock |
| PreToolUse/TDD warning | test_*.py warning | ⚠️ Warning only | OK для learning |
| PostToolUse/Auto-format | ruff format Python | ✅ Хорошо | Добавить eslint для JS |
| Notification/macOS | afplay notifications | ✅ Хорошо | Добавить Telegram option |

**Пробелы:**
- ❌ Auto-testing before Stop
- ❌ Cost tracking
- ❌ Git workflow (lint before commit)
- ❌ Doc sync validation
- ❌ API contract verification

---

## 4. Рекомендуемые хуки (12 штук, приоритизировано)

### P0: Критические (1-2 часа)

#### P0.1: Expanded Bash Safety

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/bash_safety.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Скрипт `.claude/hooks/bash_safety.sh`:
```bash
#!/bin/bash
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command')
SESSION=$(echo "$INPUT" | jq -r '.session_id')

# TIER 1: ALWAYS BLOCK
if echo "$CMD" | grep -qE '(rm\s+-rf|git\s+push\s+(--force|-f).*(main|master|prod)|dd\s+if=|mkfs)'; then
  echo "BLOCKED: Dangerous command" >&2
  echo "SESSION=${SESSION:0:8} BLOCKED=$CMD TIME=$(date -u +%s)" >> ~/.claude/safety-audit.log
  exit 2
fi

exit 0
```

#### P0.2: Protected Files Expansion

Добавить `uv.lock`, `config.local` к защищённым файлам.

---

### P1: Важные (1-2 дня)

#### P1.1: Auto-Test on Stop (agent-based)

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "agent",
            "prompt": "Run pytest tests/ -v. If fails, return {\"ok\": false, \"reason\": \"X tests failed\"}. If pass, return {\"ok\": true}.",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

Гарантия: 1324 тестов passed перед завершением.

#### P1.2: Doc Sync Validation

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/doc_sync_check.sh",
            "if": "Edit(src/schemas/*.py)"
          }
        ]
      }
    ]
  }
}
```

#### P1.3: Cost Tracking

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/cost_logger.sh"
          }
        ]
      }
    ]
  }
}
```

#### P1.4: Lint Before Commit

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/lint_before_commit.sh",
            "if": "Bash(git commit *)"
          }
        ]
      }
    ]
  }
}
```

---

### P2: Удобство (nice-to-have)

#### P2.1: Direnv Integration

```json
{
  "hooks": {
    "CwdChanged": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "if command -v direnv &> /dev/null; then direnv export bash >> \"$CLAUDE_ENV_FILE\"; fi"
          }
        ]
      }
    ]
  }
}
```

#### P2.2: Telegram Notifications

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/telegram_notify.sh"
          }
        ]
      }
    ]
  }
}
```

---

### P3: Advanced (power users)

#### P3.1: Breaking Change Detection

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "agent",
            "prompt": "Check git diff for breaking API changes. Return {\"ok\": false, \"reason\": \"Breaking change: X\"} if found.",
            "if": "Bash(git commit *)"
          }
        ]
      }
    ]
  }
}
```

#### P3.2: Budget Alert (OpenRouter)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/budget_check.sh"
          }
        ]
      }
    ]
  }
}
```

---

## 5. Hook JSON Input/Output

### Input (stdin)

```json
{
  "session_id": "abc123",
  "cwd": "/Users/user/project",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": { "command": "npm test" }
}
```

### Output (exit code + JSON)

```bash
exit 0      # Allow (JSON на stdout парсится)
exit 2      # Block (stderr → Claude feedback)
```

---

## 6. Best Practices

### Scope (где разместить)

| Location | Scope | Shareable | Примеры |
|----------|-------|-----------|---------|
| `~/.claude/settings.json` | User-wide | Нет | Global safety |
| `.claude/settings.json` | Project | Да (git) | Project-specific |
| `.claude/settings.local.json` | Project (gitignored) | Нет | Secrets, tokens |
| `.claude/hooks/*.sh` | Scripts | Да (git) | Reusable logic |

**Рекомендация для Delphi Press:**
- **Global**: Bash safety, notifications
- **Project**: Auto-format, test, doc-sync
- **Local**: OPENROUTER_API_KEY, personal prefs

### Рекомендуемая структура

```
.claude/
├── settings.json
├── settings.local.json
└── hooks/
    ├── bash_safety.sh
    ├── protect_files.sh
    ├── doc_sync_check.sh
    ├── cost_logger.sh
    └── lint_before_commit.sh
```

### Common Mistakes

- ❌ Hook outputs extra text (breaks JSON) → используй stderr для логов
- ❌ Script not executable → `chmod +x .claude/hooks/*.sh`
- ❌ jq not installed → `brew install jq`
- ❌ Mix exit codes and JSON

---

## 7. Источники

- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Awesome Claude Code](https://github.com/hesreallyhim/awesome-claude-code)
- [3 Claude Code Hooks That Save Hours (gist)](https://gist.github.com/NulightJens/6d7315edcc07e03ff055c3b9b3a47224)
- [Claude Code Hooks: Complete Guide with 20+ Examples (DEV)](https://dev.to/lukaszfryc/claude-code-hooks-complete-guide-with-20-ready-to-use-examples-2026-dcg)
- [Hooks for Automated Quality Checks (Luiz Tanure)](https://www.letanure.dev/blog/2025-08-06--claude-code-part-8-hooks-automated-quality-checks)

---

## Выводы для Delphi Press

| Приоритет | Хуки | Effort |
|-----------|------|--------|
| P0 | Expanded bash safety, protected files | 2-3 часа |
| P1 | Auto-test on Stop, doc sync, cost tracking, lint before commit | 1-2 дня |
| P2 | Direnv, Telegram notifications | пол-дня |
| P3 | Breaking change detection, budget alert | 1 день |
