# Workflows для больших проектов в Claude Code

**Дата исследования:** 27 марта 2026
**Источники:** официальная документация Anthropic + сторонние публикации марта 2026

---

## Резюме

Claude Code в марте 2026 — агентная среда с 1M контекстным окном, нативными Tasks, Session Memory и Agent Teams. Ключевой принцип: контекстное окно — главный ресурс. Пять стратегий: (1) Plan Mode для исследования перед реализацией; (2) субагенты для разведки; (3) CLAUDE.md — кратко, только то, что Claude не выведет из кода; (4) Git worktrees для параллельной работы; (5) Tasks с персистентностью между сессиями.

---

## 1. Multi-session стратегии

### Session Memory — автоматическая память между сессиями

**Источник:** [claudefa.st/blog/guide/mechanics/session-memory](https://claudefa.st/blog/guide/mechanics/session-memory), [aitoolly.com — claude-mem plugin, 17 марта 2026](https://aitoolly.com/ai-news/article/2026-03-17-claude-mem-a-new-plugin-for-automated-coding-session-memory-and-context-injection-via-claude-code)

- Фоновая система, извлекает summary из разговора автоматически
- Первое извлечение ~10 000 токенов, далее каждые ~5 000 или 3 tool calls
- Хранится: `~/.claude/projects/<project-hash>/<session-id>/session-memory/summary.md`
- При старте сессии: "Recalled X memories", просмотр через `Ctrl+O`
- `/remember` — мост между авто и ручной памятью
- Доступно только на нативном API Anthropic (Pro/Max)

### `--continue` и `--resume` для возобновления сессий

**Источник:** [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices)

- `claude --continue` — последняя сессия с полной историей
- `claude --resume` — выбор из списка сессий
- `/rename` — именование сессий ("delphi-pipeline", "llm-layer")
- Совет: "Treat sessions like branches" — каждый workstream = своя сессия

### Нативные Tasks — персистентный task management

**Источник:** [claudefa.st/blog/guide/development/task-management](https://claudefa.st/blog/guide/development/task-management)

- С v2.1.16: `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`
- Персистируют в `~/.claude/tasks/`
- `CLAUDE_CODE_TASK_LIST_ID=foresighting-news` — общий список для нескольких сессий
- Поддержка зависимостей: `addBlockedBy`
- Статусы: `pending → in_progress → completed`
- Fallback: `plan.md` с чекбоксами ("Ralph Wiggum technique")

---

## 2. Управление контекстным окном

### 1M токенов — GA для Sonnet 4.6 и Opus 4.6

**Источник:** [claudefa.st/blog/guide/mechanics/1m-context-ga](https://claudefa.st/blog/guide/mechanics/1m-context-ga)

- Usable: ~830K токенов (буфер ~33K, компакция при ~83.5%)
- Рекомендация: держать сессию в пределах 60%
- `/cost` — снапшот потребления токенов
- 1M окно: устойчивое рассуждение через взаимосвязанные файлы
- Субагенты: истинно параллельные или изолированные задачи

### `/compact`, `/clear` и управление сжатием

**Источник:** [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices)

- `/clear` — полный сброс. Между несвязанными задачами
- `/compact <инструкции>` — сжатие с фокусом: `/compact Focus on the API changes`
- `Esc + Esc` / `/rewind` — перемотка к чекпоинту
- Кастомизация в CLAUDE.md: `"When compacting, preserve modified files list"`
- `/btw` — боковой вопрос без попадания в историю

**Паттерны ошибок:**
- "Kitchen sink session": переключился на другую задачу → засорение → `/clear`
- "Correcting over and over": Claude ошибается 2+ раз → `/clear` + новый промпт
- "Over-specified CLAUDE.md": слишком длинный → игнорирует половину

### Субагенты для сохранения контекста

- **Explore** (Haiku, read-only) — поиск по кодовой базе без загрязнения
- **Plan** (read-only) — исследование перед планом
- Паттерн: субагент читает файлы, возвращает summary → главный контекст чист

---

## 3. CLAUDE.md: лучшие практики

### Что включать / исключать

**Источник:** [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices), [builder.io/blog/claude-md-guide](https://www.builder.io/blog/claude-md-guide)

**Включать:**
- Bash-команды, которые Claude не угадает
- Правила стиля, отличающиеся от дефолтов
- Инструкции по тестированию
- Архитектурные решения
- Нетривиальные импорты

**Исключать:**
- То, что Claude выведет из кода
- Стандартные конвенции языка
- Детальную API-документацию (ссылку вместо копии)
- Часто меняющуюся информацию
- Файл-по-файлу описания

**Правило:** "Если убрать строку — Claude совершит ошибку?" Если нет — удалить.

### Иерархия — глобальный, проектный, подпапочный

**Источник:** [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

- `~/.claude/CLAUDE.md` — глобальный (все проекты)
- `./CLAUDE.md` — проектный (всегда при запуске)
- `./src/agents/CLAUDE.md` — по требованию при работе с файлами в директории
- `.claude/rules/` — каждый .md автоматически загружается
- Максимум ~200 строк на файл
- Синтаксис импортов: `@path/to/file`

### Skills как альтернатива для доменных знаний

- `.claude/skills/<name>/SKILL.md` — загружаются по требованию (не при каждой сессии)
- `disable-model-invocation: true` — только ручной вызов
- Идеальны для нечастых workflow (деплой, рефакторинг схем)

---

## 4. Оркестрация субагентов

### Субагенты vs Agent Teams

**Источник:** [code.claude.com/docs/en/agent-teams](https://code.claude.com/docs/en/agent-teams)

| Параметр | Субагенты | Agent Teams |
|---|---|---|
| Контекст | Собственное окно, результат в главный | Полностью независимы |
| Коммуникация | Только отчёт главному | Прямое общение |
| Координация | Главный управляет | Общий task list |
| Стоимость | Ниже | Выше (каждый = отдельный Claude) |

**Когда субагенты:** параллельные задачи с чёткими границами файлов.
**Когда Agent Teams:** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) research & review, конкурирующие гипотезы, кросс-слойные изменения.

### Кастомные субагенты — .claude/agents/

**Источник:** [code.claude.com/docs/en/sub-agents](https://code.claude.com/docs/en/sub-agents)

- `.claude/agents/<name>.md` (проектный) или `~/.claude/agents/` (глобальный)
- Поля: `name`, `description`, `tools`, `model`, `isolation`, `memory`, `maxTurns`
- `isolation: worktree` — временный Git worktree
- `memory: project` — персистентная память в `.claude/agent-memory/<name>/`
- Субагенты НЕ наследуют skills от родителя

### Git Worktrees

**Источник:** [claudefa.st/blog/guide/development/worktree-guide](https://claudefa.st/blog/guide/development/worktree-guide)

- `claude --worktree feature-auth` → `.claude/worktrees/feature-auth/`
- Три сессии = три ветки = нулевые конфликты
- `git worktree prune` — очистка
- Добавить в `.gitignore`: `.claude/worktrees/`

---

## 5. Plan Mode

### 4-фазный workflow

**Источник:** [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices)

1. **Explore** (Plan Mode): Claude читает файлы
2. **Plan** (Plan Mode): детальный план
3. **Implement** (Normal Mode): код + тесты
4. **Commit**: коммит + PR

- Вход: `Shift+Tab` дважды
- `Ctrl+G` — открыть план в редакторе
- Нужен для: рефакторинг нескольких файлов, архитектурные изменения, неопределённость
- Не нужен для: очевидные правки (описываются одним предложением)

### Верификация — главный рычаг качества

> "Include tests, screenshots, or expected outputs so Claude can check itself. This is the single highest-leverage thing you can do." — официальная документация

---

## Применимость к Foresighting News

1. **Именование сессий:** `/rename foresighting-llm`, `/rename foresighting-delphi` и т.д.
2. **Нативный Task list:** `export CLAUDE_CODE_TASK_LIST_ID=foresighting-news`
3. **Подпапочные CLAUDE.md:** `src/agents/CLAUDE.md`, `src/llm/CLAUDE.md`, `src/schemas/CLAUDE.md`
4. **Параллельные субагенты:** для Stage 1 (коллекторы) и Stage 4 (Delphi R1, 5 персон)
5. **Plan Mode:** обязательно для orchestrator.py, delphi.py, router.py
6. **Git Worktrees:** для параллельной работы frontend + backend
7. **Верификация:** каждый промпт включает `uv run pytest tests/... -v`
8. **Кастомный субагент:** `.claude/agents/cost-auditor.md` для мониторинга бюджета

---

## Источники

1. [Best Practices — Claude Code Docs](https://code.claude.com/docs/en/best-practices)
2. [Agent Teams — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
3. [Custom Subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
4. [Memory — Claude Code Docs](https://code.claude.com/docs/en/memory)
5. [Session Memory — claudefa.st](https://claudefa.st/blog/guide/mechanics/session-memory)
6. [Task Management — claudefa.st](https://claudefa.st/blog/guide/development/task-management)
7. [1M Context — claudefa.st](https://claudefa.st/blog/guide/mechanics/1m-context-ga)
8. [Worktrees — claudefa.st](https://claudefa.st/blog/guide/development/worktree-guide)
9. [claude-mem Plugin — AIToolly, 17.03.2026](https://aitoolly.com/ai-news/article/2026-03-17-claude-mem-a-new-plugin-for-automated-coding-session-memory-and-context-injection-via-claude-code)
10. [Anthropic Subagent + MCP — Winbuzzer, 24.03.2026](https://winbuzzer.com/2026/03/24/anthropic-claude-code-subagent-mcp-advanced-patterns-xcxwbn/)
11. [Agent Teams — Sean Kim, 05.03.2026](https://blog.imseankim.com/claude-code-team-mode-multi-agent-orchestration-march-2026/)
12. [CLAUDE.md Guide — Builder.io](https://www.builder.io/blog/claude-md-guide)
13. [Plan Mode — DataCamp](https://www.datacamp.com/tutorial/claude-code-plan-mode)
