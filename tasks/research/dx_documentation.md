# Документация и Knowledge Management

> Research date: 2026-04-05

## Источники

1. [Material for MkDocs — блог 2026](https://squidfunk.github.io/mkdocs-material/blog/archive/2026/)
2. [MkDocs 2.0 announcement](https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/)
3. [mkdocstrings-python](https://mkdocstrings.github.io/python/)
4. [mike — MkDocs versioning](https://github.com/jimporter/mike)
5. [ADR best practices — AWS](https://aws.amazon.com/blogs/architecture/master-architecture-decision-records-adrs-best-practices-for-effective-decision-making/)
6. [MADR — Markdown ADR](https://adr.github.io/madr/)
7. [interrogate — docstring coverage](https://interrogate.readthedocs.io/)
8. [Docent — Claude Code doc hook](https://github.com/sammcvicker/docent)
9. [git-cliff — changelog generator](https://git-cliff.org/)

---

## Текущее состояние (аудит)

### Что работает хорошо

- **28 страниц MkDocs Material** в 13 категориях — широкое покрытие
- **GLOSSARY.md** — 38 терминов, билингвальный, образцовый DDD
- **Dead Ends** — 21 case study, высокоценный knowledge asset
- **CHANGELOG.md** — Keep a Changelog, 19 версий, "Почему:" секции
- **Sync rule** в CLAUDE.md — "при изменении Pydantic-схемы → обновить docs-site"

### Gaps

| Gap | Описание |
|-----|----------|
| API Reference ручной | 728+ определений, docstrings не автоиндексированы |
| Нет versioned docs | Одна версия без версионирования |
| Нет ADR-журнала | Решения только через dead-ends и CHANGELOG |
| Нет doc coverage tracking | Неизвестно покрытие docstrings |
| CHANGELOG ручной | 57KB, трудоёмко |
| MkDocs 2.0 — нет migration plan | Breaking rewrite (февраль 2026) |

---

## MkDocs plugins — рекомендации

| Plugin | Назначение | Effort | Impact |
|--------|------------|--------|--------|
| **mkdocstrings[python]** | Автогенерация API docs из docstrings | 2-3ч | Высокий |
| **mike** | Versioned docs (v0.9/v1.0/latest) | 1-2ч | Средний (при release) |
| mkdocs-redirects | Редиректы при переименовании | Низкий | Средний |

### mkdocstrings — конфигурация

```yaml
# docs-site/mkdocs.yml
plugins:
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: google
            show_source: false
            show_root_heading: true
```

Использование:
```markdown
::: src.agents.orchestrator.Orchestrator
    options:
      members:
        - run_prediction
```

Проект уже использует Google-style docstrings — миграция нулевая.

---

## ADR workflow

### Формат: MADR

```markdown
# [short title]

## Context and Problem Statement
[...]

## Considered Options
* [option 1]
* [option 2]

## Decision Outcome
Chosen option: "[option 1]", because [justification].
```

### Структура

```
docs-site/docs/adr/
  0001-use-openrouter-instead-of-direct-api.md
  0002-sqlite-over-postgresql.md
  0003-arq-over-celery.md
  0004-polymarket-as-calibration-source.md
```

Добавить в `mkdocs.yml` nav.

---

## Автоматизация doc sync

### Текущий: ручное правило в CLAUDE.md

### Рекомендуемый: PostToolUse reminder hook

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "echo 'SCHEMA CHANGED: update docs-site/' >&2"
        }]
      }
    ]
  }
}
```

### Продвинутый: Docent pre-commit hook

[Docent](https://github.com/sammcvicker/docent) — при каждом `git commit` анализирует changes и обновляет docs через Claude Code CLI. Молодой инструмент, стабильность не подтверждена.

---

## Versioned docs (mike)

**Нужно ли сейчас:** Нет — до публичного v1.0.
**Когда:** При появлении внешних пользователей docs или при поддержке v0.9.x параллельно с v1.x.

---

## CHANGELOG автоматизация

**Рекомендация: гибридный подход**
1. Conventional commits (`feat:`, `fix:`, `docs:`)
2. `git-cliff` генерирует скелет нового раздела
3. Разработчик добавляет "Почему:" секции вручную

---

## Doc coverage

```toml
# pyproject.toml
[tool.interrogate]
ignore-init-method = true
ignore-magic = true
fail-under = 80
```

30 минут на внедрение. Принуждает к соблюдению текущего правила о docstrings.

---

## Рекомендации (приоритизированные)

| # | Рекомендация | Effort | Impact | Приоритет |
|---|-------------|--------|--------|-----------|
| 1 | mkdocstrings — автогенерация API docs | 2-3ч | Высокий | P1 |
| 2 | ADR журнал — 5-7 ретроспективных решений | 4-6ч | Высокий | P1 |
| 3 | interrogate в CI — doc coverage gate | 30мин | Средний | P2 |
| 4 | git-cliff + conventional commits | 2-3ч | Средний | P2 |
| 5 | mike versioning | 1-2ч | При v1.0 release | P3 |

### Мониторить: MkDocs 2.0

MkDocs 2.0 (февраль 2026) — breaking rewrite: TOML вместо YAML, нет плагинов, нет Material theme. Material рекомендует Zensical как замену. Действий сейчас не требует, но мониторить до v1.0.
