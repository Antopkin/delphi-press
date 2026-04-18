---
title: "Contributing to documentation"
description: "Как писать и обновлять документацию Delphi Press."
---

# Contributing to documentation

Как писать и обновлять документацию Delphi Press.

## Правило single source of truth

**`docs-site/docs/` — единственный источник истины**. Все публичные факты о системе живут здесь. Корневые `CLAUDE.md`, `README.md`, `CHANGELOG.md` — тонкие, ссылаются сюда.

## Routing map (куда что писать)

| Что | Куда | Почему |
|---|---|---|
| Архитектурное решение «почему X, не Y» | [adr/](../adr/index.md) | Сохраняет контекст принятия; не привязано к коду |
| Новая стадия pipeline / агент | [architecture/pipeline.md](../architecture/pipeline.md) + inline docstring в `src/` | Один канон-обзор + контракт в коде |
| Новый Pydantic schema | inline docstring в `src/schemas/` + ссылка из `architecture/pipeline.md` | Docstring — источник; renders через mkdocstrings в будущем |
| LLM-задача (новый task в `DEFAULT_ASSIGNMENTS`) | [architecture/llm.md](../architecture/llm.md) | Единственная таблица всех 28 задач |
| Изменение промпта | `src/llm/prompts/` + краткое упоминание в [appendix/prompts.md](../appendix/prompts.md) | Код — SSOT; appendix — справочник |
| Новый доменный термин | [appendix/glossary.md](../appendix/glossary.md) | Один глоссарий, никаких inline определений |
| Нестандартная ошибка, которую словили | [dead-ends/case-studies.md](../dead-ends/case-studies.md) | Чтобы не решать заново |
| Операционное ограничение | [appendix/gotchas.md](../appendix/gotchas.md) | Короткий список известных «грабель» |
| Команда, которую Claude не выведет сам | `CLAUDE.md` (коротко) + [infrastructure/scripts.md](../infrastructure/scripts.md) (детально) | CLAUDE.md = быстрый доступ, scripts.md = справочник |
| Path-scoped правило для Claude Code | `.claude/rules/<name>.md` с `paths:` frontmatter | Нельзя раздувать CLAUDE.md |
| Roadmap / in-progress | [roadmap/tasks.md](../roadmap/tasks.md) | Один канон для статусов |

## Когда создавать ADR

ADR пишется, когда:

1. Решение затрагивает **≥2 модуля** и не сводится к локальному рефакторингу
2. Было рассмотрено **≥2 альтернативы**
3. Последствия заметны **>3 месяца** (не краткосрочный workaround)
4. Будущий читатель спросит «зачем это?» без ADR

Шаблон: см. любой из [adr/](../adr/index.md). Нумерация сквозная: `0006-*.md`, `0007-*.md`.

## CLAUDE.md не редактируется как обычный документ

`CLAUDE.md` попадает в контекст Claude **каждой сессии**. Это делает его дорогим:

- Target: **≤150 строк**
- Каждая строка должна экономить контекст агенту (landmark, команда, правило, `@`-импорт)
- Не дублировать docs-site — ссылаться через `@docs-site/...`
- Не копировать списки из `mkdocs.yml` или `SKILL.md`
- HTML-комментарии `<!-- -->` — для maintainer-заметок, они стрипаются Claude

Trigger для update:
- Агент повторно ошибается в конкретном контексте → добавить правило
- Новый landmark (крупный файл, который агент должен находить сразу)
- Изменение commands, которые Claude не угадает сам

## docs-site build

```bash
cd docs-site && uv run mkdocs build --strict
```

`--strict` падает при:
- Broken internal links
- Orphan pages (нет в nav)
- Missing nav targets

CI должен всегда запускать `--strict`. Dev: `mkdocs serve` для live preview.

## Новая страница — чеклист

1. Создать `docs-site/docs/<section>/<name>.md` с H1 в первой строке
2. Добавить в `docs-site/mkdocs.yml` → `nav:` под правильной секцией
3. Cross-link из смежных страниц (`see also:` footer или inline)
4. `mkdocs build --strict` → должно пройти
5. Если затрагивает агент/контракт — обновить `CLAUDE.md` landmarks (если добавлен важный файл)

## Удаление страницы

1. Проверить refs: `grep -r "pagename.md" docs-site/ src/`
2. Мигрировать или удалить refs
3. `git rm` файл
4. Удалить из `mkdocs.yml` nav
5. `mkdocs build --strict` → должно пройти

## Стиль

- **Язык**: русский для prose, английский для технических названий (названия классов, task IDs, параметры API)
- **Admonitions**: `!!! info`, `!!! note`, `!!! warning`, `!!! tip` для выделения
- **Code blocks**: всегда с language hint (` ```python `, ` ```bash `, ` ```yaml `)
- **Tables**: booktabs-style через pipe syntax
- **Headings**: H1 = title (одно на страницу), далее H2/H3; H4+ редко

## Анти-drift

- Не писать «Версия: X.Y.Z» / «N тестов» в prose — цифры устаревают за неделю. Ссылаться на CHANGELOG или «см. roadmap».
- Не дублировать `mkdocs.yml` nav внутри страниц
- Не копировать код из `src/` в docs — линковать `src/path/to/file.py` или выжимку
- Pruning: раз в квартал `mkdocs build --strict` + ручной аудит stale refs

## Pruning cadence

Event-driven, не scheduled:

- После релиза: проверить свежесть screenshots, version-mentioning prose
- После крупной фичи: убедиться, что ADR написан
- Когда Claude повторно ошибается: найти источник путаницы и зачистить
