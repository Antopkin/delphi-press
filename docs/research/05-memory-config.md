# Memory System и .claude/ конфигурация Claude Code

**Дата исследования:** 27 марта 2026
**Источники:** официальная документация Anthropic + community-публикации марта 2026

---

## Резюме

Claude Code не "обучается" — это re-reading system. Память = текстовые файлы, инжектируемые в контекст при старте. CLAUDE.md до 200 строк, MEMORY.md до 200 строк. Стратегия передачи контекста: CLAUDE.md (постоянные правила) + авто-память (паттерны) + `--continue`/`--resume` (возобновление сессий). settings.json — единственный механизм жёстких ограничений (в отличие от CLAUDE.md, который "советует").

---

## 1. Система памяти: re-reading, не обучение

**Источник:** [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory), [joseparreogarcia.substack.com — Claude Code memory explained](https://joseparreogarcia.substack.com/p/claude-code-memory-explained)

Каждая сессия = чистое окно. Память = инъекция текста при старте.

| Параметр | CLAUDE.md | Авто-память |
|---|---|---|
| Кто пишет | Разработчик | Claude |
| Содержание | Инструкции | Паттерны |
| Лимит | <200 строк для качества | 200 строк / 25KB MEMORY.md |
| Применение | Каждая сессия | Каждая сессия |

### Четыре типа записей авто-памяти

**Источник:** [Raj Rajhans — Claude Code's Memory Model, март 2026](https://rajrajhans.com/2026/03/claude-codes-memory-model/)

```yaml
---
name: [имя]
description: [одна строка для решений о релевантности]
type: [user/feedback/project/reference]
---
[содержание]
```

- **user** — роль, экспертиза, предпочтения
- **feedback** — коррекции И подтверждения (оба типа!)
- **project** — текущий контекст, дедлайны (намеренно устаревает)
- **reference** — указатели на ресурсы, не содержание

**Чего не сохранять:** паттерны кода (уже в коде), git-историю (уже в git), рецепты отладки (уже в docs).

---

## 2. Иерархия CLAUDE.md — 5 уровней

**Источник:** [code.claude.com/docs/en/settings](https://code.claude.com/docs/en/settings)

| Уровень | Расположение | Область | Git |
|---|---|---|---|
| Managed | `/Library/Application Support/ClaudeCode/CLAUDE.md` | Организация | IT/MDM |
| User | `~/.claude/CLAUDE.md` | Все проекты | Нет |
| User rules | `~/.claude/rules/` | Все проекты | Нет |
| Project | `./CLAUDE.md` или `./.claude/CLAUDE.md` | Команда | Да |
| Project rules | `./.claude/rules/` | Команда | Да |

- Поддиректорные файлы грузятся по требованию
- `.claude/rules/` — каждый .md загружается автоматически
- `@path/to/file` — импорт другого файла
- Path-scoped rules:
  ```yaml
  ---
  paths:
    - "src/agents/**/*.py"
  ---
  # Правила для агентов
  ```

### Что куда

- **Глобальный:** личные предпочтения, язык, workflow, hooks, MCP routing
- **Проектный:** команды сборки, стандарты кода, архитектурные решения
- **Rules/:** тематические правила (testing, api-design, security)

---

## 3. settings.json — жёсткие ограничения

**Источник:** [code.claude.com/docs/en/settings](https://code.claude.com/docs/en/settings), [eesel.ai — settings.json guide](https://www.eesel.ai/blog/settings-json-claude-code)

CLAUDE.md — инструкции (Claude "старается"). settings.json — техническое принуждение (выполняется всегда).

Иерархия: managed → CLI args → local → project → user.
- Массивы (permissions.allow/deny) **объединяются**
- Скалярные значения **заменяются** по приоритету

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(uv run *)",
      "Bash(pytest *)",
      "Bash(ruff *)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git status)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)"
    ]
  },
  "autoMemoryEnabled": true,
  "language": "russian",
  "plansDirectory": "./tasks/plans"
}
```

---

## 4. Передача контекста между сессиями

### Три стратегии

**Источник:** [claudefa.st/blog/guide/mechanics/session-memory](https://claudefa.st/blog/guide/mechanics/session-memory)

1. **CLAUDE.md** — постоянный контракт. Переживает `/compact`, грузится всегда.
2. **Resume:** `claude --continue` (последняя) или `--resume` (выбор). `/rename` для именования.
3. **Spec-файлы:** сессия-интервью → SPEC.md → чистая сессия для реализации.

### Компакция

- `/compact` — CLAUDE.md перечитывается с диска. Диалог не выживает.
- Кастомизация: `"When compacting, preserve modified files list and test commands"`

### Правило "двух провалов"

Claude ошибается дважды → `/clear` + новый промпт. Чистая сессия с улучшенным промптом лучше загрязнённой с исправлениями.

---

## 5. Организация .claude/

**Источник:** [blog.dailydoseofds.com — Anatomy of .claude/ Folder](https://blog.dailydoseofds.com/p/anatomy-of-the-claude-folder)

```
# Проектный (коммитится)
.claude/
├── CLAUDE.md
├── settings.json
├── settings.local.json      # gitignored
├── rules/
│   ├── code-style.md
│   ├── testing.md
│   └── security.md
├── agents/
│   └── agent-reviewer.md
└── skills/
    └── fix-issue/SKILL.md

# Глобальный
~/.claude/
├── CLAUDE.md
├── settings.json
├── rules/
├── agents/
├── skills/
└── projects/<project>/memory/
    ├── MEMORY.md              # Индекс
    └── *.md                   # Тематические файлы
```

---

## Рекомендации для Foresighting News

### 1. `.claude/settings.json` с защитой .env (высокий)

Сейчас .env не защищён на уровне permissions. Hook блокирует правку, но не чтение.

### 2. `.claude/rules/` — тематические файлы (высокий)

```
.claude/rules/
├── async-patterns.md      # async, httpx, aiosqlite, ARQ
├── pydantic-schemas.md    # Pydantic v2, structured output
├── llm-layer.md           # AgentResult, cost tracking
└── testing.md             # pytest, fixtures
```

### 3. Именованные сессии (средний)

```bash
/rename collectors-pipeline
/rename delphi-agents
/rename frontend-ui
```
Возобновлять через `claude --resume`.

### 4. Agent-reviewer (средний)

```yaml
# .claude/agents/agent-reviewer.md
---
name: agent-reviewer
description: Reviews LLM agent code for correctness and cost efficiency
tools: Read, Grep, Glob
model: sonnet
---
Review: AgentResult pattern, cost tracking, Pydantic parsing, async correctness.
```

### 5. Обновить авто-память с frontmatter (низкий)

Добавить `type:` к каждой записи для лучшей фильтрации релевантности.

---

## Источники

1. [Memory — Claude Code Docs](https://code.claude.com/docs/en/memory)
2. [Settings — Claude Code Docs](https://code.claude.com/docs/en/settings)
3. [Best Practices — Claude Code Docs](https://code.claude.com/docs/en/best-practices)
4. [Memory Model — Raj Rajhans, март 2026](https://rajrajhans.com/2026/03/claude-codes-memory-model/)
5. [Hooks Guide — SmartScope, March 2026](https://smartscope.blog/en/generative-ai/claude/claude-code-hooks-guide/)
6. [Memory Management — Data Science Collective](https://medium.com/data-science-collective/claude-code-memory-management-the-complete-guide-2026-b0df6300c4e8)
7. [.claude/ Folder — Avi Chawla](https://blog.dailydoseofds.com/p/anatomy-of-the-claude-folder)
8. [Memory Explained — Jose Parro Garcia](https://joseparreogarcia.substack.com/p/claude-code-memory-explained)
9. [Session Memory — claudefa.st](https://claudefa.st/blog/guide/mechanics/session-memory)
10. [settings.json Guide — eesel.ai](https://www.eesel.ai/blog/settings-json-claude-code)
