---
title: "ADR-0009: docs-site/ — единственный источник истины для документации"
description: "Redesign документации: MkDocs-сайт как SSOT; CLAUDE.md как тонкий map; удаление дублирования; llms.txt для agent-first docs."
---

# ADR-0009: docs-site/ — единственный источник истины для документации

**Status:** Accepted · **Date:** 2026-04-18 · **Deciders:** @Antopkin

## Context

Документация Delphi Press росла органически за первые 12 версий. К апрелю 2026 существовало три параллельных источника:

1. **`docs-site/docs/`** — MkDocs-сайт на `delphi.antopkin.ru/docs/`, 29 страниц, build зелёный
2. **Корневые MD** — `CLAUDE.md` (166 строк), `README.md` (478 строк), `GLOSSARY.md`, `CHANGELOG.md`, `tasks/*`
3. **`docs/*.md`** — 16 архивных предреализационных спек + 6 research notes

Проблемы, которые реально фиксировались:

- **Версионный хаос:** 4 разных версии в активных файлах (`pyproject.toml: 0.1.0`, `src/config.py: 0.9.5`, `CLAUDE.md: 0.9.8`, `CHANGELOG: 0.9.9`); 4 разных счётчика тестов. `/api/v1/health` отдавал пользователям устаревшую версию.
- **Contradiction:** `appendix/prompts.md` утверждал «персоны на GPT-4o/Gemini/Llama», `architecture/llm.md` — «все Opus 4.6». Одно из двух — мусор.
- **Context loss в Claude Code:** агент не находил нужное, дублирование, ссылки на несуществующие пути, ~60 src/ docstrings ссылались на архивные `docs/NN-*.md`.
- **Нет entry point для агентов:** `index.md` был для людей-читателей; агент терялся в 29 страницах.

Исследование паттернов март-апрель 2026 (Anthropic, Mintlify, HumanLayer, мкдокс-плагины) показало консенсус: **тонкий `CLAUDE.md` + fat `docs-site` + `llms.txt`** — правильная архитектура для проектов, где главный читатель — Claude Code.

## Decision

**`docs-site/docs/` = единственный источник истины.** Всё остальное — тонкое, со ссылками сюда.

1. **Удалить архивные `docs/NN-*.md` + `tasks/research/*`** (~54 файла, 27К строк): miграция inline docstrings в `src/` через batch sed → `docs-site/...`, затем `git rm`.
2. **Сократить `CLAUDE.md`:** 166 → 78 строк. Только то, что агент не может получить из кода или docs-site: landmarks, команды-которые-не-угадать, signposts через `@path` imports.
3. **Сократить `README.md`:** 478 → 67 строк. GitHub landing page: пitch + 3 quick-start + ссылки в docs-site.
4. **Перенести `GLOSSARY.md`** → `docs-site/docs/appendix/glossary.md` через `git mv` (сохранить историю).
5. **Расширить `docs-site/`** новыми страницами под агентов: `for-agents.md` (entry point), `architecture/claude-code-mode.md`, `adr/`, `conventions/code-style.md`, `conventions/contributing-docs.md`.
6. **Добавить `mkdocs-llmstxt`** плагин → авто-генерация `/llms.txt` (slim индекс) и `/llms-full.txt` (полная выгрузка) при каждом build. Плюс `mkdocs-copy-to-llm` кнопка на страницах, `mkdocs-include-markdown-plugin` для одного канонического CHANGELOG.
7. **Единая версия через `src/__init__.py::__version__`** + `pyproject.toml dynamic` + `src/config.py` читает из `__version__`. Вся prose-версия в docs убирается — «см. CHANGELOG».
8. **ADR директория** — этот файл и другие 8 документируют архитектурные решения, которые раньше жили только в CHANGELOG или головах.
9. **YAML frontmatter** (title + description) на каждой docs-site странице — для поиска и будущего llms.txt description emission.

## Consequences

**Плюсы:**
- Один источник для каждого факта → zero drift risk
- CLAUDE.md 78 строк → каждая сессия Claude стартует быстрее и точнее
- llms.txt готов для внешних агентов (Cursor, Claude Code CLI, Windsurf)
- Новые контрибьюторы видят сайт, а не 30 файлов в корне

**Минусы:**
- Migration cost: ~20 часов работы через 8-фазный план
- Существующие внешние ссылки на корневые MD могли сломаться (редко)
- `tasks/todo.md` / `tasks/lessons.md` конвенция из глобального `~/.claude/CLAUDE.md` теперь не используется — заменена auto-memory + harness `TaskCreate`

**Когда пересмотреть:**
- Если docs-site build становится медленным (>30 сек) — смотреть на mkdocs-2.0 миграцию или уменьшение плагинов
- Если llms.txt перестанет быть полезным (маловероятно, эмerging standard консолидируется)
- Если появится multi-tenant с несколькими документированными проектами — monorepo docs pattern

## Alternatives considered

1. **Ничего не менять (статус кво)** — постепенно drift становится непреодолимым; context loss Claude Code нарастает. Отвергнуто: боль уже была заметна.
2. **CLAUDE.md как rich guide (300+ строк)** — делает каждую сессию Claude дороже; Anthropic явно рекомендует тонкий. Отвергнуто.
3. **Микс: `docs/` как SSOT для архитектуры, `docs-site/` только для публичной документации** — создаёт два одинаково «авторитетных» места; drift гарантирован. Отвергнуто.
4. **AGENTS.md + символлинк CLAUDE.md** — emerging cross-agent pattern. Для Claude-only проекта не даёт benefit сейчас; отложено на будущее, когда понадобится Cursor/Codex support.

## References

- План redesign: `~/.claude/plans/snazzy-imagining-dewdrop.md` (8 фаз)
- 8 исследовательских отчётов: `~/.claude/plans/snazzy-imagining-dewdrop-reports/{R1-R3, E1-E5}.md`
- Конвенции: [conventions/contributing-docs.md](../conventions/contributing-docs.md)
- Коммиты: `e86f156` (Phase A) → `9e0a34e` (frontmatter)
- Commit count: 7 (A, B, C+D, CI fix, E, F, frontmatter)
