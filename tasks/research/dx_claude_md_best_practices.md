# CLAUDE.md Best Practices 2026

> Research date: 2026-04-05
> Контекст: Delphi Press v0.9.5 — production Python проект, 233 файла, 1324 теста, solo developer

## Источники

1. [Anthropic Official: How Claude remembers your project (Memory)](https://code.claude.com/docs/en/memory) — официальная документация, апрель 2026
2. [Anthropic Official: Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices) — официальное руководство
3. [ArthurClune/claude-md-examples: python-CLAUDE.md](https://github.com/ArthurClune/claude-md-examples/blob/main/python-CLAUDE.md) — образец Python-проекта
4. [discus0434/python-template-for-claude-code: CLAUDE.md](https://github.com/discus0434/python-template-for-claude-code/blob/main/CLAUDE.md) — Python 3.12+ шаблон с TDD
5. [minimaxir: CLAUDE.md — Agent Guidelines for Python Code Quality](https://gist.github.com/minimaxir/c274d7cc12f683d93df2b1cc5bab853c) — Python code quality gist
6. [rohitg00/awesome-claude-code-toolkit: python-project.md template](https://github.com/rohitg00/awesome-claude-code-toolkit/blob/main/templates/claude-md/python-project.md) — ETL/FastAPI production template
7. [dev.to: How to Hyper-Optimise Claude Code](https://dev.to/andrei_nita/how-to-hyper-optimise-claude-code-the-complete-engineering-guide-1eh3) — <200 lines, progressive disclosure
8. [alexop.dev: Claude Code Customization Guide](https://alexop.dev/posts/claude-code-customization-guide-claudemd-skills-subagents/) — separation of concerns framework
9. [genaiunplugged.substack.com: What Goes in CLAUDE.md](https://genaiunplugged.substack.com/p/claude-code-skills-commands-hooks-agents) — CLAUDE.md vs skills vs hooks vs agents
10. [ranthebuilder.cloud: Lessons From Real Projects](https://ranthebuilder.cloud/blog/claude-code-best-practices-lessons-from-real-projects/) — 3 production projects analysis
11. [claudefa.st: Context Window Optimization](https://claudefa.st/blog/guide/mechanics/context-management) — token management
12. [mcpcat.io: Managing Claude Code Context](https://mcpcat.io/guides/managing-claude-code-context/) — context buffer management

---

## Ключевые находки

### Finding 1: Официальный лимит — 200 строк, за пределами правила теряются

**Источник**: Anthropic официальная документация (code.claude.com/docs/en/memory), апрель 2026.

Антропик явно устанавливает: _"Target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence."_ Механизм потери — не технический лимит, а когнитивный: CLAUDE.md загружается как часть контекстного окна (user message после system prompt), и при превышении плотности инструкций Claude начинает пропускать правила в середине файла.

Тест из практики (dev.to): файл 847 токенов vs монолитная документация — разница 92% по эффективности использования контекста (89% vs 7.4%).

Текущий CLAUDE.md Delphi Press: ~123 строки — **в пределах лимита**, но есть секции с низкой плотностью ROI.

### Finding 2: Separation of concerns — четыре слоя, каждый со своей ответственностью

**Источник**: alexop.dev, genaiunplugged.substack.com, code.claude.com/docs/en/best-practices.

Официальная формула (2026): _"CLAUDE.md is for memory, skills for routines, hooks for guarantees, agents for delegation."_

| Слой | Тип | Когда загружается | Надёжность |
|------|-----|-------------------|------------|
| **CLAUDE.md** | Правила + архитектура | Каждая сессия | Вероятностная (~70%) |
| **`.claude/rules/*.md`** | Правила по path-паттернам | При работе с matching файлами | Вероятностная |
| **Skills** | Повторяемые воркфлоу | По требованию / авто-триггер | Вероятностная |
| **Hooks** | Критические запреты | Детерминированно, всегда | 100% (exit code 2) |
| **Agents** | Специализированные субагенты | Явная делегация | Изолированный контекст |

**Вывод**: правила безопасности (никогда не делай X) должны быть в hooks, не в CLAUDE.md.

### Finding 3: `@import` синтаксис — способ сохранить лаконичность без потери информации

**Источник**: code.claude.com/docs/en/memory (официально), dev.to (практика).

CLAUDE.md поддерживает `@path/to/file` синтаксис — файл раскрывается и загружается вместе с CLAUDE.md в контекст. Это позволяет держать CLAUDE.md как оглавление, вынося детали:

```markdown
# Project Overview
...

# Code Standards
@.claude/rules/code-style.md

# API Contracts
@docs/api-contracts.md
```

Ключевое отличие `@import` от `.claude/rules/`: импорты загружаются **всегда** (вместе с CLAUDE.md), rules — только при работе с matching файлами. Для Delphi Press правила async/pydantic уже правильно вынесены в `.claude/rules/` с path-scoping — это **уже соответствует best practice**.

### Finding 4: Что включать vs исключать — официальная таблица Anthropic

**Источник**: code.claude.com/docs/en/best-practices (официально), 2026.

| Включать | Исключать |
|----------|-----------|
| Bash-команды, которые Claude не угадает | Всё, что Claude выводит из кода сам |
| Правила стиля, отличные от дефолтных | Стандартные языковые конвенции |
| Инструкции для тестирования | Детальную API-документацию (давать ссылку) |
| Репо-этикет (naming branches, PR conventions) | Часто меняющуюся информацию |
| Архитектурные решения, специфичные для проекта | Длинные объяснения и туториалы |
| Gotchas и неочевидное поведение | File-by-file описания кодовой базы |
| Env vars, необходимые для разработки | Самоочевидные практики ("пиши чистый код") |

**Anti-pattern**: "self-evident practices" — правила вроде "Use type hints" и "Use async for I/O" в Python 3.12 FastAPI проекте 2026 года — это то, что Claude знает по умолчанию. Их наличие занимает токены без добавления ценности.

### Finding 5: `.claude/rules/` с path-scoping — официальный механизм для больших проектов

**Источник**: code.claude.com/docs/en/memory (официально), апрель 2026.

Anthropic в 2026 официально рекомендует `.claude/rules/` для организации инструкций в крупных проектах. Rules с YAML frontmatter `paths:` загружаются **только** когда Claude работает с matching файлами.

**Delphi Press уже использует этот паттерн** (4 rules файла: async-patterns, pydantic-schemas, agents-llm, testing). Это соответствует современным best practices.

### Finding 6: HTML-комментарии в CLAUDE.md не попадают в контекст

**Источник**: code.claude.com/docs/en/memory (официально), 2026.

Малоизвестная возможность: `<!-- maintainer notes -->` в CLAUDE.md **стрипаются** перед инъекцией в контекст. Позволяет оставлять заметки для разработчика, не тратя токены.

### Finding 7: CLAUDE.md загружается как user message, не как system prompt

**Источник**: code.claude.com/docs/en/memory (официально).

Критическое понимание: _"CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself."_ Это объясняет, почему правила соблюдаются ~70% времени, а не 100%. Для 100% соблюдения критических правил нужны hooks (`settings.json`).

---

## Сравнительная таблица

| Аспект | Наш CLAUDE.md | Best Practice | Оценка | Рекомендация |
|--------|---------------|---------------|--------|--------------|
| **Размер** | ~123 строки | <200 строк | ✅ Хорошо | Следить за ростом |
| **Секция правил кода** | В CLAUDE.md (8 пунктов) | Стандартные конвенции — убрать, специфичные — оставить | ⚠️ Частично | Убрать "async everywhere", "type hints" — Claude знает это для FastAPI/Python 3.12 |
| **Path-scoped rules** | 4 файла в `.claude/rules/` | Рекомендовано официально | ✅ Best practice | Уже реализовано |
| **Навигация по документации** | 10 ссылок в секции | Поддерживается, но можно через `@import` | ✅ Хорошо | Рассмотреть `@docs-nav.md` для разгрузки |
| **Дизайн-система (Impeccable)** | Таблица 20 команд в CLAUDE.md | Skill-specific → в skill, не CLAUDE.md | ⚠️ Оверфит | Вынести в `.claude/skills/impeccable/SKILL.md` |
| **E2E dry run примеры** | В CLAUDE.md (10 строк) | Команды с аргументами — уместны | ✅ Хорошо | Оставить |
| **IP адрес сервера** | В CLAUDE.md | Часто меняющаяся информация — исключить | ⚠️ Anti-pattern | Перенести в `CLAUDE.local.md` (gitignore) |
| **Доменный глоссарий** | Ссылка на `GLOSSARY.md` | Правильно — ссылка, не копия | ✅ Best practice | Оставить |
| **Separation of concerns** | CLAUDE.md + rules + skills + hooks | Четыре слоя, каждый со своей ответственностью | ✅ Хорошо | Проверить что в hooks есть критические запреты |
| **Синхронизация документации** | Инструкция в CLAUDE.md | Workflow инструкции → skill | ⚠️ Возможно улучшить | Рассмотреть skill `sync-docs` |
| **`@import` синтаксис** | Не используется | Поддерживается, снижает объём CLAUDE.md | 🔵 Нейтрально | Применить для навигации по документации |
| **HTML-комментарии** | Не используются | Бесплатные заметки для разработчика | 🔵 Нейтрально | Использовать для TODO/maintainer notes |
| **Версия и счётчик тестов** | `v0.9.5. Тесты: 1324` | Часто меняющаяся информация | ⚠️ Anti-pattern | Убрать или автоматизировать |

---

## Конкретные рекомендации

### 1. Удалить самоочевидные правила кода (экономия ~5 строк, снижение шума)

Из секции "Правила кода" убрать следующие пункты — Claude знает их для FastAPI/Python 3.12 проекта без напоминания:
- `Async everywhere: все I/O — async` (уже есть в `.claude/rules/async-patterns.md`)
- `Type hints: все функции типизированы` (стандарт Python 3.12)
- `Pydantic schemas` (уже есть в `.claude/rules/pydantic-schemas.md`)
- `Structured output` (следствие из pydantic-schemas rule)

**Оставить**: `Error handling: AgentResult(success=False)`, `Cost tracking`, `Imports: абсолютные от src.`, `Docstrings: Google-style + module-level docstring обязателен` — это проектная специфика, которую Claude не угадает.

### 2. Вынести таблицу Impeccable в отдельный skill (экономия ~20 строк)

Секция "Дизайн-система (Impeccable)" с таблицей 20 команд загружается в каждую сессию, включая backend-задачи, которые никогда не касаются фронтенда. В CLAUDE.md оставить только одну строку:
```markdown
**Дизайн-система**: Impeccable (`.claude/skills/`). При работе с `src/web/` — skill активируется автоматически.
```

### 3. Перенести серверные реквизиты в `CLAUDE.local.md`

IP `213.165.220.144`, `deploy@...` — это "часто меняющаяся информация, специфичная для конкретного разработчика". По официальной рекомендации такое идёт в `CLAUDE.local.md` (добавить в `.gitignore`).

### 4. Убрать версию и счётчик тестов из CLAUDE.md

`v0.9.5. Тесты: 1324` — это "часто меняющаяся информация". После каждого коммита она устаревает. Версия есть в `pyproject.toml`, количество тестов — в CI.

### 5. Применить `@import` для секции навигации документации

Вынести навигацию в `.claude/docs-nav.md` и сослаться через `@.claude/docs-nav.md`.

### 6. Добавить HTML-комментарии для maintainer notes

Использовать `<!-- -->` для заметок, которые нужны разработчику, но не нужны Claude.

### 7. Проверить hooks на полноту критических запретов

Убедиться, что правила вида "НИКОГДА не делай X" реализованы как hooks, а не как строки в CLAUDE.md.

### 8. Добавить path-scoped rule для frontend

Создать `.claude/rules/frontend.md` с path-scope на `src/web/**`.

### 9. Рассмотреть skill `sync-docs` для документационного workflow

Секция "Синхронизация документации" — pattern для skill, не для CLAUDE.md.

### 10. Регулярный аудит: тест каждого правила

Раз в квартал: "Если удалить эту строку — Claude начнёт делать ошибки?" Если нет — удалить.

---

## Итоговая оценка

**Оценка**: CLAUDE.md соответствует best practices на ~75%. При применении рекомендаций 1–4 файл сократится до ~95 строк с улучшенным соотношением сигнал/шум.

**Три самых высокоприоритетных изменения:**
1. Убрать правила, дублирующие rules-файлы (async, type hints, pydantic)
2. Вынести таблицу Impeccable в skill (20 строк экономии)
3. Перенести IP сервера и счётчик тестов в CLAUDE.local.md
