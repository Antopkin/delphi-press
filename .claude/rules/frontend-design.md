---
paths:
  - "src/web/**"
  - "docs-site/docs/frontend/**"
---

# Frontend design system — Impeccable

Проект использует [Impeccable](https://github.com/pbakaus/impeccable) — систему дизайн-скиллов для Claude Code (Apache 2.0). 20 скиллов вендорятся в `.claude/skills/`.

## Первый запуск

```
/teach-impeccable
```

Собирает дизайн-контекст проекта интервью-образом, результат сохраняется в `.impeccable.md` (gitignored). Запускать один раз при onboarding.

## Основной скилл

`/frontend-design` — активируется при работе с `src/web/`. Содержит 7 справочных модулей: типографика, цвет, пространство, анимация, взаимодействие, адаптивность, UX-тексты.

## Стиринг-команды (20 скиллов)

| Категория | Команды |
|---|---|
| Аудит и ревью | `/audit`, `/critique`, `/polish` |
| Типографика и цвет | `/typeset`, `/colorize` |
| Лейаут и пространство | `/arrange`, `/adapt` |
| Выразительность | `/bolder`, `/quieter`, `/delight` |
| Движение и взаимодействие | `/animate`, `/onboard` |
| Оптимизация и упрощение | `/optimize`, `/harden`, `/distill`, `/clarify` |
| Рефакторинг | `/extract`, `/normalize` |
| Продвинутое | `/overdrive` |
| Настройка | `/teach-impeccable` |

## Стек

- **CSS**: Tailwind CSS v4.2.2 через PostCSS build (`@theme` config)
- **JS components**: 17 JS-referenced `fn-*` components
- **Typography**: Newsreader / Source Sans 3 / JetBrains Mono (Google Fonts)
- **Icons**: встроенные SVG (не иконочный шрифт)

Полная документация UI: @docs-site/docs/frontend/web-ui.md.

## Когда активировать

Этот rule loaded автоматически через `paths:` frontmatter — при чтении любого файла в `src/web/` или `docs-site/docs/frontend/`. Не требует ручного импорта из CLAUDE.md.

## Attribution

Impeccable © Paul Bakaus, Apache 2.0. Вендорится в `.claude/skills/{audit,critique,polish,typeset,colorize,arrange,adapt,bolder,quieter,delight,animate,onboard,optimize,harden,distill,clarify,extract,normalize,overdrive,teach-impeccable}/`.
