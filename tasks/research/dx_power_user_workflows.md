# Workflow паттерны Power Users Claude Code

> Research date: 2026-04-05
> Источники: 18 материалов (InfoQ, Sanity.io, Addy Osmani, Boris Cherny, HN, DEV Community, GitHub)

## Executive Summary

Power users с��роят работу вокруг трёх принципов: **Structure > Prompting**, **Memory > Intelligence**, **Verification > Confidence**. Ключевые паттерны: plan-first, трёхслойная память (CLAUDE.md + today.md + skills), ��ара��лельные сессии через worktrees + tmux, hooks как детерминированная автоматизация. Boris Cherny (создатель Claude Code): 5 локальных + 5-10 ��далённых инстансов, `/commit-push-pr` десятки раз в день, CLAUDE.md в 2500 токенов.

---

## Источники

1. [My Claude Code Setup — Pedro Santanna](https://psantanna.com/claude-code-my-workflow/workflow-guide.html)
2. [Inside the Workflow of Claude Code's Creator — InfoQ](https://www.infoq.com/news/2026/01/claude-code-creator-workflow/)
3. [First Attempt Will Be 95% Garbage — Sanity.io](https://www.sanity.io/blog/first-attempt-will-be-95-garbage)
4. [Lessons from Using Claude Code — Tim Hopper](https://tdhopper.com/blog/lessons-from-using-claude-code-effectively/)
5. [Best Practices: Lessons From Real Projects — Ran The Builder](https://ranthebuilder.cloud/blog/claude-code-best-practices-lessons-from-real-projects/)
6. [My LLM Coding Workflow 2026 — Addy Osmani](https://addyosmani.com/blog/ai-coding-workflow/)
7. [Claude Code Workflow Template — runesleo](https://github.com/runesleo/claude-code-workflow)
8. [Claude Code for Advanced Users — Cuttlesoft](https://cuttlesoft.com/blog/2026/02/03/claude-code-for-advanced-users/)
9. [LLM Codegen Parallelization with Worktrees — DEV](https://dev.to/skeptrune/llm-codegen-go-brrr-parallelization-with-git-worktrees-and-tmux-2gop)

---

## Каталог паттернов (20)

### Session Management

**1. Plan-First**: Plan Mode (`Shift+Tab` x2) обязателен для задач 3+ шагов. Claude анализирует кодовую базу в read-only, строит план. Boris Cherny: *"The most common failure mode ��� solving the wrong problem in a fragile order."*

**2. Трёхслойная память (Hot/Warm/Cold)**: Hot = CLAUDE.md + `today.md` (загружается всегда). Warm = `@docs/architecture.md`, skills (on-demand). Cold = архивные решения (по запросу). *"Structure > Prompting. Memory > Intelligence."*

**3. Параллельные сессии (Worktrees + tmux)**: Несколько Claude Code инстансов в изолированных git worktrees. Boris Cherny: 5 локальных + 5-10 удалённых. Стоимость линейна (5 агентов = 5x).

**4. Session Naming + Resume**: Семантические имена (`delphi-quality-gate-debug`). `claude --continue` / `claude --resume`. `/compact` при 60-70% контекста.

**5. Hard Session Cap**: Лимит ~50K токенов. При контекст��ом выгорани�� (дублирование функций, галлюцинация путей) → `/clear` + новая сессия с брифингом и�� `today.md`.

### Task Decomposition

**6. Три попытки**: П��рвая попытка ~5% годного, вторая ~50%, третья — рабочий прототип. Не выбрасывать первую — она раскрывает constraints.

**7. Specification-First ("15-минутный waterfall")**: Перед кодом — итеративный диалог для спеки. Addy Osmani: *"Like doing a waterfall in 15 minutes."*

**8. SSOT-декомпозиция**: Каждый тип информации — одно место. В CLAUDE.md только `@file` ссылки, не копии.

**9. Subagent-Per-Concern**: Каждый subagent = один домен. Research-агент не знает про код. Предотвращает context cross-contamination.

### Quality Assurance

**10. Verification-Driven Development**: Дать Claude способ верифицировать вывод → качес��во 2-3x. Boris Cherny: *"The single most impactful strategy."* Claude не объявляет задачу done без запуска verification.

**11. Claude Reviews First**: Два прохода: (1) Claude проверяет — тесты, баги. (2) Человек — maintainability, security, бизнес-логика.

**12. Quality Gates через Hooks**: Hooks = детерминированная автоматизация. PostToolUse `ruff format`, Stop hook — тесты. *"Hooks turn polite suggestions into guaranteed actions."*

### Context Optimization

**13. Context Budget Audit**: MCP ��отребляют 8-30% контекста. Оптимум: 3-6 MCP. CLAUDE.md ≤200 строк. Убирать дефолтные правила ("type hints" — Claude знает это).

**14. Skills для domain knowledge**: CLAUDE.md = operating manual (всегда). Skills = domain encyclopedia (по вызову). Экономия контекста при backend-сессиях.

**15. Model Routing**: Opus — critical logic. Sonnet — daily dev. Haiku — boilerplate. Boris Cherny: только Opus с thinking — "меньше ошибок, меньше steering, чистый результат быстрее."

### Automation

**16. Custom Slash Commands**: Каждая повторяющаяся последовательность → `.claude/commands/`. Boris Cherny использует `/commit-push-pr` десятки раз в день.

**17. AI_DOCS/**: Machine-readable документация для быстрого `@`-импорта. Pipeline overview, agent contracts, DB schema, common gotchas.

**18. "Sunday Rule"**: Meta-work (правка CLAUDE.md, hooks) только в designated slot. Остальные дни — shipping.

**19. Tribal Knowledge → Docs**: Каждое испр��вленное недоразумение Claude → правило в CLAUDE.md. Каждый dead-end → `case-studies.md`. Каждый incident → `gotchas.md`.

**20. Multi-Model Cross-Verification**: Сложные задачи через несколько моделей параллельно. Расхождения = сигнал неоднозначности.

---

## Top-5 для немедленного внедрения

### 1. Verification-Driven Development (Паттерн 10) ��� КРИТИЧНО

Добавить в CLAUDE.md:
```markdown
## Verification Rule
После каждого изменения pipeline:
uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 5
Задача не завершен�� до прочтения вывода.
```
**Эффект**: снижение production-регрессий на 50%+.

### 2. today.md как Hot State (Паттерн 2+8) — ВЫСОКИЙ

1. Создать `tasks/today.md`: текущая задача, последний dry_run, следующий шаг, вопросы
2. В CLAUDE.md: `@tasks/today.md` и `@tasks/lessons.md`
3. Stop hook: напоминание обновить today.md

**Эффект**: 5-10 мин экономии на каждом старте сессии.

### 3. Subagent-Per-Stage для отладки (Паттерн 9) — ВЫСОКИЙ

При диагностике pipeline: отдельный `claude` ��ля каждой подозрительной стадии с минимальным контекстом (код стадии + тесты + schema).
**Эффект**: time-to-diagnosis 30 → 10 минут.

### 4. Custom Command /dry-run-smoke (Паттерн 16) — БЫСТРЫЙ

`.claude/commands/dry-run-smoke.md` — 5 минут на создание, ежедневная экономия.

### 5. @tasks/lessons.md import (Паттерн 19) — БЫСТРЫЙ

��дна строка в CLAUDE.md замыкает self-improvement loop. Повторяемые ошибки исчезнут через 2-3 сессии.

---

## Common Mistakes

| Антипаттерн | Решение |
|---|---|
| Kitchen Sink Session — несвязанные задачи | `/clear` между задачами |
| CLAUDE.md > 200 строк | Прунить; только project-specific |
| Blind Trust — деплой AI-кода без ревью | Не мержить код, который нельзя объяснить |
| Correction Loop (>2 попыток) | `/clear` + переписа��ь промпт |
| Ожидание perfect output сразу | Планировать 3 итерации |
| Пропуск Plan Mode | Plan Mode для задач 3+ шагов |
| MCP overload (>6 серверов) | Максимум 3-6 активных |
| Done без verification | Verification rule в CLAUDE.md |
| Vague prompts ("исправь это") | Файл, строка, current vs desired |
| Meta-work в середине задачи | Sunday Rule |

---

## Claude Code vs конкуренты

| Критерий | Claude Code | Cursor | GitHub Copilot |
|---|---|---|---|
| Тип | Terminal CLI agent | AI-native IDE | Multi-IDE extension |
| Context | 1M (Opus 4.6) | 256K | Varies |
| Autocomplete | Нет | Да (72%) | Да |
| Сила | Deep reasoning, CLI, long-context | Daily editing, IDE UX | Teams, price |
| SWE-bench | 80.8% | ~49% | ~55% |
| Цена | $20-200/мес | $20-40/мес | $10-39/мес |

**Практика**: бол��шинство совмещают Claude Code (сложное) + Cursor (повседневное) ≈ $40-50/мес.

---

## Mental Models

- **"Junior Developer Who Doesn't Learn"** (Quigley) — детачмент от ко��а; легче удалять плохое
- **"Structure > Prompting"** (runesleo) — 1 час ��а today.md экономит часы steering/неделю
- **"Commits as Save Points"** (Osmani) — commit после каждой task; checkpoint для экспериментов
- **"Human = Senior Engineer"** (Osmani) — AI ускоряет; человек р��шает
- **"Recover Faster"** (Hopper) �� скорость цикла важнее точности первой попытки
