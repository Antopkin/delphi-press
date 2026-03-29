# 09 -- Frontend: Architecture & Design System

> Реализуемые файлы: `src/web/templates/*.html`, `src/web/static/css/input.css`, `src/web/static/js/*.js`, `src/web/router.py`
> Зависимости: Tailwind CSS v4.2.2 (PostCSS build), Google Fonts, Vanilla JS (ES2022), Jinja2 3.1+, FastAPI

---

## 1. Принципы дизайна

Фронтенд строится на шести ключевых принципах:

1. **Grandmother-friendly** — интерфейс понятен без инструкций, без специальных знаний ИТ
2. **Utility-first CSS** — Tailwind CSS генерирует классы из конфига; JS-referenced компоненты в `@layer components`
3. **Progressive enhancement** — сайт работает без JS; скрипты добавляют полировку (автодополнение, анимации, SSE)
4. **Mobile-first** — все страницы адаптивны; брейкпойнты в Tailwind config
5. **CSS-first config** — дизайн-токены (цвета, spacing, motion) в `@theme` директиве `input.css`
6. **One-request-one-screen** — нет SPA; каждый роут = отдельная HTML-страница с SSR

---

## 2. Файловая структура

```
src/web/
├── router.py                    # FastAPI маршруты (GET/POST для всех страниц)
├── templates/
│   ├── base.html               # Базовый шаблон (nav, footer, blocks)
│   ├── index.html              # Главная: форма + недавние прогнозы
│   ├── progress.html           # Прогресс-страница с SSE-потоком
│   ├── results.html            # Результаты с карточками заголовков
│   ├── about.html              # Методология + 5 персон + этапы
│   ├── login.html              # Форма входа
│   ├── settings.html           # Управление API-ключами
│   └── partials/
│       ├── headline_card.html  # Карточка с заголовком (hero/secondary)
│       └── reasoning_block.html # Расширяемый блок с обоснованием
└── static/
    ├── css/
    │   ├── input.css           # Tailwind source + @theme дизайн-токены
    │   └── tailwind.css        # Compiled output (committed)
    └── js/
        ├── form.js             # Автодополнение + отправка формы
        ├── progress.js         # SSE + обновление UI прогресса
        ├── results.js          # Аккордион расширяемых блоков
        ├── settings.js         # Валидация/добавление/удаление ключей
        └── reveal.js           # Scroll-reveal анимации
```

---

## 3. Наследование шаблонов

Все страницы наследуют `base.html`:

```
base.html
├── block: title
├── block: extra_head (для <script>, <link>)
├── block: content (страница-специфично)
└── block: extra_js (страница-специфично)
```

**Главные блоки в base.html:**
- `<nav class="fn-nav">` — навигация с мобильным гамбургером
- `<main class="container">` — контейнер контента (max-width ~960px)
- `<footer class="fn-footer">` — подвал с копирайтом

Шаблоны без JavaScript: `index.html`, `about.html`, `login.html`, `settings.html` (JS после загрузки).
Шаблоны, требующие JS: `progress.html` (SSE), `results.html` (accordion).

---

## 4. Дизайн-система

### 4.1 Типографика

Подключаются через Google Fonts с `font-display: swap` для быстрой загрузки:

| Стиль | Font Stack | Использование |
|-------|-----------|---|
| Headings | Newsreader 400/600/700 | `h1`, `h2`, `h3`, `.fn-*-heading` |
| Body | Source Sans 3 400/600/700 | Основной текст, интерфейс |
| Mono | JetBrains Mono 400/600 | `<code>`, `<pre>`, моно-цифры |

**Type scale (perfect fourth, 1.333):**

| Класс | Размер | Использование |
|-------|--------|---|
| `--fn-text-xs` | 0.75rem (12px) | Подписи, метаинформация |
| `--fn-text-sm` | 0.875rem (14px) | Вторичный UI |
| `--fn-text-base` | 1rem (16px) | Основной текст |
| `--fn-text-lg` | 1.333rem (21px) | Подзаголовки |
| `--fn-text-xl` | 1.777rem (28px) | Заголовки секций |
| `--fn-text-2xl` | 2.369rem (38px) | Заголовки страниц |

### 4.2 Цветовая палитра

Все цвета в OKLCH (современный формат с лучшей перцепцией). Fallback hex-значения для старых браузеров.

**Поверхности (синеватые нейтралы, hue 250):**

| Переменная | OKLCH | Назначение |
|-----------|------|-----------|
| `--fn-surface-0` | oklch(99% 0.005 250) | Фон страницы |
| `--fn-surface-1` | oklch(96.5% 0.008 250) | Фон карточек |
| `--fn-surface-2` | oklch(93% 0.010 250) | Фон при hover |
| `--fn-border` | oklch(88% 0.012 250) | Границы |

**Текст:**

| Переменная | OKLCH | Назначение |
|-----------|------|-----------|
| `--fn-text` | oklch(20% 0.015 250) | Основной текст |
| `--fn-text-heading` | oklch(15% 0.020 250) | Заголовки |
| `--fn-text-muted` | oklch(55% 0.015 250) | Вторичный текст |

**Confidence levels (5 уровней):**

| Уровень | OKLCH | Hex Fallback | Диапазон |
|--------|------|-------------|---------|
| Very high | oklch(58% 0.17 145) | #16a34a | 80-100% |
| High | oklch(55% 0.20 250) | #2563eb | 60-79% |
| Moderate | oklch(62% 0.18 75) | #d97706 | 40-59% |
| Low | oklch(58% 0.19 45) | #ea580c | 20-39% |
| Speculative | oklch(52% 0.20 25) | #dc2626 | 0-19% |

**Step states:**

- `--fn-step-done`: oklch(58% 0.17 145) — зелёный
- `--fn-step-active`: oklch(55% 0.20 250) — синий
- `--fn-step-pending`: oklch(65% 0.015 250) — серый

### 4.3 Spacing scale (4pt base)

| Переменная | Значение | px | Использование |
|-----------|----------|-----|---|
| `--fn-space-1` | 0.25rem | 4px | Микро-отступы |
| `--fn-space-2` | 0.5rem | 8px | Компактные промежутки |
| `--fn-space-3` | 0.75rem | 12px | Малые отступы |
| `--fn-space-4` | 1rem | 16px | Стандартные отступы |
| `--fn-space-6` | 1.5rem | 24px | Секция-внутри отступы |
| `--fn-space-8` | 2rem | 32px | Большие отступы |
| `--fn-space-12` | 3rem | 48px | Между секциями |
| `--fn-space-16` | 4rem | 64px | Крупные пробелы |
| `--fn-space-24` | 6rem | 96px | Максимальные промежутки |

### 4.4 Motion

**Easing functions:**

- `--fn-ease-out-quart`: cubic-bezier(0.25, 1, 0.5, 1) — быстрый выход
- `--fn-ease-out-expo`: cubic-bezier(0.16, 1, 0.3, 1) — экспоненциальный выход
- `--fn-ease-in-quart`: cubic-bezier(0.7, 0, 0.84, 0) — быстрый вход
- `--fn-ease-in-out`: cubic-bezier(0.65, 0, 0.35, 1) — плавный вход/выход

**Duration scale:**

- `--fn-duration-instant`: 100ms
- `--fn-duration-fast`: 200ms
- `--fn-duration-normal`: 300ms
- `--fn-duration-slow`: 500ms

**Respects `prefers-reduced-motion`**: все длительности обнуляются если пользователь включил режим.

### 4.5 Радиусы

| Переменная | Значение |
|-----------|----------|
| `--fn-radius-sm` | 0.25rem |
| `--fn-radius-md` | 0.5rem |
| `--fn-radius-lg` | 0.75rem |
| `--fn-radius-full` | 9999px |

---

## 5. Компонентная библиотека

Все кастомные компоненты имеют префикс `fn-` и определены в `input.css` (`@layer components`). Полный список (~60 классов):

| Компонент | CSS-класс | Шаблон | Назначение |
|-----------|-----------|--------|-----------|
| Автодополнение | `.fn-autocomplete-wrapper` | `index.html` | Обёртка для input + выпадающий список |
| Бейджик | `.fn-badge`, `.fn-badge--{success,info,danger,very-high,high,...}` | Везде | Статус, уровень уверенности |
| Карточка заголовка | `.fn-headline-card`, `.fn-headline-card--{hero,secondary}` | `results.html` | Заголовок, уверенность, обоснование |
| Блок обоснования | `.fn-reasoning-block` | `headline_card.html` | Расширяемый `<details>` с аргументами |
| Чип | `.fn-meta-chip` | `results.html` | Дата, время, стоимость |
| Точка уверенности | `.fn-confidence-dot--{very-high,high,...}` | `headline_card.html` | Цветной круг перед %  |
| Категория | `.fn-category`, `.fn-small-caps` | `headline_card.html` | Малые капители |
| Шаг | `.fn-step`, `.fn-step--{pending,active,done}` | `progress.html` | Элемент шкалы прогресса |
| Timeline | `.fn-timeline`, `.fn-step-list` | `progress.html` | Вертикальная линия + шаги |
| Flow-диаграмма | `.fn-steps-flow`, `.fn-flow-step`, `.fn-flow-connector` | `index.html` | "Как это работает" 1-2-3 |
| Повествование | `.fn-narrative`, `.fn-narrative-serif` | `progress.html` | Блок с текстом на serif шрифте |
| Ошибка | `.fn-error-card`, `.fn-error-entrance` | `progress.html` | Карточка с ошибкой + анимация |
| Прогресс-бар | `<progress id="progress-bar">` | `progress.html` | Встроенный HTML5 элемент |
| Лого | `.fn-logo` | `base.html` | Заголовок навигации |
| Навигация | `.fn-nav`, `.fn-desktop-nav`, `.fn-mobile-nav` | `base.html` | Адаптивная навбар с гамбургером |
| Подвал | `.fn-footer`, `.fn-footer-grid` | `base.html` | Низ страницы с инфо |
| Герой | `.fn-hero` | `index.html` | Заголовок + подзаголовок главной |
| Форма-ошибка | `.fn-form-error` | `index.html`, `login.html` | Показ ошибок валидации |
| Preset-карточка | `.fn-preset-card`, `.fn-preset-card--selected` | `index.html` | Выбор режима (Light/Standard/Full) |
| Персона | `.fn-persona`, `.fn-persona-grid` | `about.html` | Card с иконкой и описанием |
| Pull-цитата | `.fn-pull-quote` | `about.html` | Большая цитата |
| Auth-секция | `.fn-auth-section`, `.fn-auth-logo` | `login.html` | Центрированная форма |
| Согласие экспертов | `.fn-agreement-indicator`, `.fn-agreement--{consensus,majority,split}` | `headline_card.html` | Консенсус vs расхождения |
| Диссент | `.fn-dissent-item` | `headline_card.html` | Доп. строка с мнением меньшинства |

---

## 6. CSS-архитектура

### Структура `input.css` (Tailwind CSS v4):

**Основные слои:**

1. **@theme directive** — CSS-переменные дизайн-системы (цвета OKLCH, spacing, motion, radius, fonts)
2. **@layer components** — 17 JS-referenced `fn-*` классов (nav, footer, cards, badges, forms и т.д.)
3. **@tailwindcss/forms** — базовые стили форм (input, button, select)
4. **Tailwind utilities** — автоматически генерируются из config

**Компиляция:**

```bash
npm run css:build   # Production: input.css → tailwind.css (minified)
npm run css:dev     # Development: input.css → tailwind.css (watch mode)
```

**Docker:** `css-builder` stage компилирует CSS при сборке образа.

**Дизайн-токены в @theme:**
- Цветовая палитра (OKLCH синеватые нейтралы + confidence levels)
- Spacing scale (4pt base: 0.25rem–6rem)
- Motion: easing functions, duration scale
- Радиусы: sm, md, lg, full
- Fonts: Newsreader (headings), Source Sans 3 (body), JetBrains Mono (code)
- Брейкпойнты: мобильный-first (sm: 576px, md: 768px)

**Соглашение о классах:**
- `fn-` префикс для 17 JS-referenced компонентов (сохранены как `@layer components`)
- BEM-подобные модификаторы: `fn-badge--success`, `fn-step--done`, `fn-preset-card--selected`
- Для ARIA-состояний: `aria-busy="true"` стилизуется через `button[aria-busy="true"]`
- Остальное: Tailwind utility classes (например, `flex`, `gap-4`, `rounded-md`)

---

## 7. JavaScript-модули

Все скрипты — Vanilla ES2022 в IIFE-обёртке с `"use strict"`.

| Модуль | Страница | Задача | API endpoints | Key DOM IDs |
|--------|----------|--------|------------|------------|
| `form.js` | index.html | Автодополнение (catalog + DB) + отправка формы. Показывает "Издание не найдено" hint при пустых результатах, 2s warning при unresolved outlet перед redirect. | GET `/api/v1/outlets?q=...`, POST `/api/v1/predictions` | `#prediction-form`, `#outlet`, `#outlet-suggestions`, `#target_date`, `#submit-btn` |
| `progress.js` | progress.html | SSE-поток, обновление шагов, redirect | GET `/api/v1/predictions/{id}/stream` (EventSource) | `#progress-bar`, `#progress-percent`, `#step-list`, `#narrative-area` |
| `results.js` | results.html | Аккордион reasoning-блоков | Нет | `.fn-reasoning-block` (details) |
| `settings.js` | settings.html | Валидация, добавление, удаление ключей | POST/DELETE `/api/v1/keys` | `#add-key-form`, `.fn-delete-btn`, `.fn-validate-btn` |
| `reveal.js` | about.html | Scroll-reveal при входе в viewport | Нет | `[data-reveal]` |

**Общие JS-паттерны:**
- Переменная на `querySelector`/`getElementById` в начале каждого модуля
- Early return если элемента нет на странице
- Fetch с `credentials: "same-origin"` для автоматической передачи JWT-cookie
- `aria-busy="true"` на кнопках во время async операций
- `hidden` атрибут вместо `display: none` для показа/скрытия

---

## 8. Система анимаций

### Keyframes (в `input.css` @theme):

- `fn-fade-in` — opacity 0→1
- `fn-fade-in-up` — transform + opacity (снизу вверх)
- `fn-slide-in-left` — translateX снизу слева
- `fn-scale-in` — scale 0.9→1
- `fn-shimmer` — gradient animation (loading)
- `fn-pulse` — opacity pulsing
- `fn-shake` — small horizontal shake (error)

**Scroll-reveal механизм:**
- Элементы с `data-reveal` наблюдаются через `IntersectionObserver`
- При попадании в viewport (threshold 0.1) добавляется класс `fn-revealed`
- CSS правило `.fn-revealed { animation: fn-fade-in ... }`

**Stagger (каскадная анимация):**
- Родитель: `data-stagger`
- Дети: `--fn-stagger-i: 0`, `--fn-stagger-i: 1`, и т.д.
- CSS: `animation-delay: calc(var(--fn-stagger-i) * 100ms)`

**Microinteractions:**
- Button hover: `transform: scale(0.98)` (press effect)
- Link hover: underline scaleX animation
- Preset cards: border highlight on `:has(input:checked)`

---

## 9. Frontend-Backend контракт

### 9.1 HTML-маршруты (из `router.py`):

| Route | Method | Роль | Параметры |
|-------|--------|------|-----------|
| `/` | GET | Landing: форма + недавние прогнозы | Нет |
| `/predict/{id}` | GET | Прогресс-страница (SSE) или redirect на results | `id` (UUID) |
| `/results/{id}` | GET | Готовые результаты с карточками | `id` (UUID) |
| `/about` | GET | Методология, 5 персон, этапы | Нет |
| `/login` | GET/POST | Форма/обработка входа | POST: `email`, `password`, `next` |
| `/register` | GET/POST | Форма/обработка регистрации | POST: `email`, `password` |
| `/logout` | GET | Удалить JWT-cookie, redirect / | Нет |
| `/settings` | GET | Управление API-ключами (требует auth) | Нет |

### 9.2 REST API endpoints (использование во фронтенде):

| Endpoint | Method | Использование | Response |
|----------|--------|---|----------|
| `/api/v1/outlets?q=QUERY` | GET | Autocomplete на главной (catalog + DB) | `{ items: [{ name, normalized_name, language, website_url, ... }] }` |
| `/api/v1/predictions` | POST | Создание прогноза + outlet resolution | `{ id, status, outlet, target_date, outlet_resolved, outlet_language, outlet_url }` |
| `/api/v1/predictions/{id}/stream` | GET (SSE) | Прогресс в реальном времени | `{ stage, message, progress, elapsed_ms }` |
| `/api/v1/predictions/{id}` | GET | Статус прогноза (fallback при разрыве SSE) | `{ id, status, ... }` |
| `/api/v1/keys` | POST | Добавить API-ключ | `{ id, provider, label, is_active }` |
| `/api/v1/keys/{id}` | DELETE | Удалить ключ | 204 No Content |
| `/api/v1/keys/{id}/validate` | POST | Проверить валидность ключа | `{ valid, message }` |

### 9.3 SSE-формат (progress.js):

```json
{
  "stage": "collection",
  "message": "Загружаем новости...",
  "progress": 0.15,
  "detail": "Собираем RSS-фиды из 3 источников",
  "elapsed_ms": 2500,
  "cost_usd": 0.04
}
```

Специальные значения `stage`:
- `"completed"` — перенаправить на `/results/{id}`
- `"failed"` — показать ошибку, закрыть соединение

### 9.4 Авторизация (JWT в HttpOnly cookie):

- `POST /login` или `POST /register` → сервер устанавливает cookie `access_token` (HttpOnly, SameSite=Lax)
- `GET /settings` → проверка `current_user` через dependency injection
- Fetch-запросы: `credentials: "same-origin"` автоматически отправляет cookie
- `GET /logout` → удаление cookie, redirect на `/`

---

## 10. Accessibility

- **Focus ring**: `:focus-visible { outline: 2px solid #2563eb }` (не скрыт для клавиатуры)
- **ARIA-busy**: `button[aria-busy="true"]` получает opacity 0.6, disabled=true
- **Semantic HTML**: `<button>`, `<nav>`, `<footer>`, `<article>`, `<details>` — всё по спеке
- **Keyboard nav**:
  - Форма: Enter в dropdown выбирает, Tab/Shift+Tab между полями
  - Settings: Tab для фокуса на кнопок, Space/Enter для действия
  - Hamburger nav: CSS-only `<details>`, work без JS
- **Reduced motion**: `@media (prefers-reduced-motion: reduce)` обнуляет все `--fn-duration-*`
- **Language**: `<html lang="ru">` для скринридеров

---

## 11. Performance

- **Fonts**: Google Fonts с `font-display: swap` (текст показывается сразу, шрифт подгружается асинхронно)
- **CSS**: 1 файл (`tailwind.css`), minified, оптимизирован PurgeCSS (только используемые классы)
- **JS**: 5 модулей по 2-8KB каждый; отсутствует на некоторых страницах
- **No frameworks**: Vanilla JS, Tailwind CSS build (не CDN) → контролируемый размер
- **CSS hamburger**: `<details>` работает без JS
- **GPU animations**: только `transform` и `opacity` (трансформы GPU-ускорены)
- **Page load**: ~1.3–1.5s на медленном 3G

---

## 12. Тестирование фронтенда

**Unit тесты**: `tests/test_web/` (~29 тестов)

- Проверка маршрутов (`GET /`, `POST /login`, и т.д.)
- Валидация контекста шаблона (переменные, объекты)
- SSE-формат и правильность stage-переходов
- Redirect-логика (auth, завершение)

**Инструменты:**
- `pytest` для тестирования маршрутов
- Mocklocation для fake SSE
- No Selenium/Playwright (фокус на серверной части)

---

## 13. Структура результирующей страницы

Пример структуры после полного рендера `results.html`:

```html
<article class="fn-headline-card fn-headline-card--hero">
  <header>
    <div class="fn-headline-header">
      <span class="fn-rank-serif">#1</span>
      <span class="fn-badge fn-badge--very-high">
        <span class="fn-confidence-dot fn-confidence-dot--very-high"></span>
        87% -- Очень высокая
      </span>
      <span class="fn-category fn-small-caps">Politics</span>
    </div>
  </header>
  <h3 class="fn-headline-text">{{ headline_text }}</h3>
  <p class="fn-first-paragraph">{{ first_paragraph }}</p>
  <p class="fn-reasoning-summary"><small><em>{{ reasoning }}</em></small></p>
  {% include "partials/reasoning_block.html" %}
</article>
```

Каждая карточка заголовка содержит:
- Ранг (1, 2, 3, ...)
- Badge с уровнем уверенности + цветная точка
- Категория в small caps
- Основной текст заголовка (serif, крупный)
- Первый абзац (readable width ~65ch)
- Краткое обоснование
- Расширяемый блок с полным обоснованием (аккордион)

---

## 14. Добавление нового компонента

**Шаги:**

1. Добавить новый CSS-класс в `input.css` (`@layer components`) с префиксом `fn-`
2. Определить базовый стиль + все модификаторы (например, `fn-badge--success`)
3. Добавить в таблицу компонентов (раздел 5)
4. Создать шаблон-пример в нужном `.html`-файле
5. При наличии интерактивности: добавить JS в соответствующий модуль
6. Обновить этот документ (раздел 5, 7, и т.д.)

---

## 15. Развёртывание

Фронтенд развёртывается вместе с бэком:
- Шаблоны загружаются из `src/web/templates/`
- CSS компилируется в `src/web/static/css/tailwind.css` (committed в repo)
- JS загружается с `{{ url_for('static', path='js/form.js') }}?v={{ app_version }}`
- **Cache-busting**: все static URLs содержат `?v={{ app_version }}` (Jinja2 global из `Settings.app_version`). nginx: `Cache-Control: public` + `expires 7d`. При обновлении версии браузеры загружают свежие файлы.
- Docker: `css-builder` stage выполняет `npm run css:build` при сборке образа

**Локальная разработка:**

```bash
npm install                    # Установить зависимости (package.json)
npm run css:dev               # Watch mode: input.css → tailwind.css при изменении
uv run uvicorn src.main:app   # Dev сервер (потребляет tailwind.css)
```

---

**Дальнейшее изучение:**
Для подробного понимания макета и поведения читайте исходные файлы в `src/web/`. Каждый шаблон хорошо аннотирован комментариями. CSS разбит на 18 секций с полной документацией.
