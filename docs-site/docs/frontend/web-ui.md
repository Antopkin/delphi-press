# Web UI Documentation

> **Реализация**: `src/web/router.py`, `src/web/templates/*.html`, `src/web/static/js/*.js`  
> **Спека**: `docs/09-frontend.md`

Веб-интерфейс Delphi Press — это однопаршиновое приложение на Jinja2 + Tailwind CSS v4 + Vanilla JS (ES2022). Все маршруты переходят в отдельные HTML-страницы (no SPA), каждая с собственным набором скриптов.

## Архитектура маршрутизации

### HTML-маршруты

Все маршруты определены в `src/web/router.py` и возвращают полные HTML-страницы:

| Маршрут | Метод | Аутентификация | Описание |
|---------|-------|---|---|
| `/` | GET | Нет | Главная страница с формой прогноза + примеры прогнозов |
| `/predict/{prediction_id}` | GET | Нет* | Страница прогресса (SSE) или автоматический переход на результаты |
| `/results/{prediction_id}` | GET | Нет* | Завершённые результаты с карточками заголовков + timeline |
| `/markets` | GET | Нет | Дашборд сигналов Polymarket (informed consensus) |
| `/about` | GET | Нет | Методология, 5 персон Дельфи, этапы пайплайна |
| `/login` | GET / POST | Нет | Форма входа + обработка (устанавливает JWT-cookie) |
| `/register` | GET / POST | Нет | Форма регистрации + автоматический вход |
| `/logout` | POST | Необходимо | Удаляет cookie, перенаправляет на `/` |
| `/settings` | GET | Необходимо | Управление API-ключами (таблица + форма добавления) |

**\* Нет аутентификации требуется, но проверяется право доступа:**
- Если `prediction.user_id is None` → доступно всем (анонимные прогнозы)
- Если `user is None` → доступно (обратная совместимость)
- Если `prediction.user_id != user.id` → 403 Forbidden (доступ только владельцу)

### API-маршруты (фронтенд использует)

| Endpoint | Метод | Использование | Response |
|----------|-------|---|----------|
| `/api/v1/outlets?q=QUERY` | GET | Автодополнение выбора издания | `{ items: [{ name, language, ... }] }` |
| `/api/v1/predictions` | POST | Создание прогноза | `{ id, status, outlet_resolved, outlet_language, ... }` |
| `/api/v1/predictions/{id}/stream` | GET (SSE) | Прогресс в реальном времени | `{ stage, message, progress, elapsed_ms, cost_usd }` |
| `/api/v1/predictions/{id}` | GET | Статус + данные для fallback-восстановления | `{ id, status, outlet_name, target_date, headlines, ... }` |
| `/api/v1/keys` | POST | Добавить API-ключ | `{ id, provider, label, is_active }` |
| `/api/v1/keys/{id}` | DELETE | Удалить ключ | 204 No Content |
| `/api/v1/keys/{id}/validate` | POST | Проверить валидность | `{ valid, message }` |

---

## Иерархия шаблонов

### Базовый шаблон

**`src/web/templates/base.html`** — главный макет, который расширяют все страницы:

```jinja2
{% extends "base.html" %}
{% block title %}...{% endblock %}
{% block content %}...{% endblock %}
{% block extra_js %}...{% endblock %}
```

**Основные компоненты base.html:**

1. **Head-секция:**
   - Google Fonts: Newsreader (заголовки), Source Sans 3 (текст), JetBrains Mono (код)
   - Tailwind CSS (скомпилированный в `static/css/tailwind.css`)
   - KaTeX для рендеринга формул (CDN)
   - Mermaid для диаграмм (CDN)

2. **Navigation (`<nav class="max-w-5xl mx-auto">`):**
   - Desktop nav: горизонтальное меню (скрыто на мобильных)
   - Mobile nav: CSS `<details>` гамбургер (работает без JS)
   - Активные ссылки подсвечиваются (green primary color)
   - Кнопка выхода (POST `/logout`, требует CSRF-token)

3. **Main content (`<main class="max-w-5xl animate-fade-in-up">`):**
   - Контейнер 5xl (960px max-width)
   - Fade-in-up анимация при загрузке

4. **Footer (`<footer>`):**
   - Copyright, дисклеймер о исследовательском характере
   - Ссылки на GitHub и Telegram (@Antopkin)

### Страница-специфичные шаблоны

#### `/` — Главная (`index.html`)

Структура:
- **Hero section:** "Что напишут СМИ завтра?" + описание
- **How it works:** 3-шаговая схема (1. Выберите СМИ → 2. Укажите дату → 3. Получите прогноз)
- **Prediction form:**
  - Поле `outlet` с автодополнением (dropdown)
  - Поле `outlet_url` (видно, если издание не найдено в каталоге)
  - Поле `target_date` (date picker, от завтра до +7 дней)
  - Поле `api_key` (пароль, опциональное; используется, если нет сохранённых ключей)
  - Выбор режима (Light ~$0.20–0.30 vs Opus ~$7–10)
  - Кнопка "Прогнозировать"
  - Область ошибок (скрыта по умолчанию)
- **Showcase predictions:** таблица 5 публичных прогнозов (`is_public = True`)
- **My predictions:** таблица пользовательских прогнозов (только для авторизованных)

**JS-скрипт:** `form.js` (загружается в `{% block extra_js %}`)

---

#### `/predict/{id}` — Прогресс (v0.9.6) (`progress.html`)

**Новое в v0.9.6:** CSS-счётчики для серифных номеров, мерцающая анимация активного шага, группировка этапов по фазам.

Структура:
- **Hero header:**
  - Подзаголовок: "Формируем прогноз" (small, primary, uppercase, fade-in-up)
  - h1: название издания (4xl/5xl responsive, fade-in-up с delay)
  - Целевая дата (text-lg, text-muted, fade-in-up с delay)

- **Progress bar:**
  - `<progress>` элемент с встроенным gradient shimmer (CSS animation)
  - `.fn-progress-meta`: процент (%) + elapsed time (HH:MM:SS) в tabular numerals

- **Two-column layout (`grid-cols-1 lg:grid-cols-[1fr_320px]`):**

  **Левая колонка: Step list**
  - Container: `bg-surface-1 border border-border rounded-lg p-6`
  - `<ul id="step-list" class="fn-timeline" data-stagger>`
  - **Три фазы:**
    1. **Сбор данных** (`fn-step-phase`):
       - Собираем новости (collection)
       - Выявляем ключевые события (event_identification)
    2. **Экспертный анализ** (`fn-step-phase`):
       - Анализируем траектории событий (trajectory)
       - Экспертная панель: раунд 1 (delphi_r1)
       - Экспертная панель: раунд 2 (delphi_r2)
       - Формируем консенсус (consensus)
    3. **Генерация** (`fn-step-phase`):
       - Анализируем стиль издания (framing)
       - Генерируем заголовки (generation)
       - Проверяем качество (quality_gate)

  - **Каждый шаг (`.fn-step`):**
    - `data-stage="..."` (для SSE matching)
    - `fn-step-icon`: CSS counter (`counter(step)`) — серифный номер Newsreader
    - `fn-step-content`: сильный текст (заголовок) + small описание + `fn-step-detail` (инлайн детали из SSE)
    - `fn-step-duration`: shrink-0 (появляется когда step.duration_ms заполнен)
    - Состояния: `fn-step--pending` (○) → `fn-step--active` (мерцание shimmer) → `fn-step--done` (● с scale-in)

  **Правая колонка (desktop `hidden lg:block`):**
  - `sticky top-6` — прикрепляется к верху при скролле
  - `#narrative-area`: `bg-surface-1 border border-border rounded-lg p-6` (hidden по умолчанию)
    - h3: "Сейчас происходит" (xs, semibold, uppercase)
    - `#narrative-message`: serif font-heading, italic, text-lg
  - На мобильных: `#narrative-area-mobile` (под шагами, text-center)

- **Info banner:**
  - "Формирование займет 30–40 минут. Пожалуйста, не перезагружайте страницу."
  - border-l-4 border-primary/40, bg-primary/5

- **Stall warning** (`#stall-warning`, скрыта по умолчанию):
  - Появляется если нет SSE-событий > 120s
  - border-l-4 border-amber-400, bg-amber-50 dark

- **Error section** (`#error-section`, скрыта по умолчанию):
  - border-l-4 border-confidence-speculative, bg-confidence-speculative/10
  - h3: "Произошла ошибка"
  - Кнопка "Попробовать снова" (ссылка на `/`)

**Логика переходов:**
- Если прогноз уже завершён → 302 redirect на `/results/{id}`
- Если ещё в процессе → показать прогресс-страницу

**CSS-счётчики:**
```css
.fn-timeline {
  counter-reset: step;
}
.fn-step[data-stage] {
  counter-increment: step;
}
.fn-step--pending .fn-step-icon::before,
.fn-step--active .fn-step-icon::before {
  content: counter(step);  /* 1, 2, 3, ... в Newsreader serif */
}
.fn-step--done .fn-step-icon::before {
  content: "";  /* скрывает число, показывает только точку */
  animation: scale-in 300ms;
}
```

**Анимации:**
- `animate-fade-in-up [animation-delay:100ms]` — cascade для header элементов
- `.fn-step--active`: `background: linear-gradient(shimmer)` + `animation: shimmer 2.5s` — мерцание через active step
- `.fn-step--done .fn-step-icon::before`: `animation: scale-in 300ms` — появление checkmark-точки
- `[data-stagger]`: `animation-delay: calc(var(--fn-stagger-i) * 80ms)` — cascade для шагов

**JS-скрипт:** `progress.js` (SSE-подключение + UI-обновления)

---

#### `/results/{id}` — Результаты (v0.9.6) (`results.html`)

**Новое в v0.9.6:** Единообразный стиль всех headline cards (без первой-карточки особой), metadata reorganization, reasoning как blockquote.

Структура:
- **Header:**
  - h1: "Прогноз для {{ prediction.outlet_name }}" (4xl/5xl, fade-in-up)
  - Meta chips (flex flex-wrap gap-2):
    - Дата: "{{ prediction.target_date.strftime('%d.%m.%Y') }}"
    - Длительность: "{{ total_duration_ms / 1000 }}с"
    - Стоимость: "${{ total_llm_cost_usd | round(2) }}"
    - Preset: "light" или "full" (primary/10 если full, else surface-1)

- **Section 1: Headline Cards** (`data-stagger`):
  - Каждая карточка: `partials/headline_card.html`
  - Структура карточки (`.fn-headline-card`):
    - **Header:**
      - Row 1: category (xs, uppercase) + confidence badge (цвет-кодированный: 80%+ зелёный, 60-79% синий, и т.д.)
      - Row 2: rank numeral (text-2xl serif, text-muted/30, shrink-0) + headline (text-xl/2xl serif)
    - **Body:**
      - First paragraph preview (text-muted, 0.95rem, max-w-prose)
      - `partials/reasoning_block.html` (expandable с reasoning, evidence_chain, agent_agreement, dissenting_views)

- **Section 2: Timeline** (если `predicted_timeline` существует):
  - h2: "Timeline событий"
  - Horizon band: "1-2 дня (оперативный режим)" / "3-4 дня (смешанный)" / "5-7 дней (структурный)"
  - `.fn-timeline` (как на progress page, но с `fn-step--done`):
    - Icon: номер (1, 2, 3, ...)
    - **Content:**
      - Prediction text (strong)
      - Metadata: predicted_date, probability badge, uncertainty (±дни), wild_card flag
      - Reasoning (expandable details)
      - Causal dependencies (xs, if present)

- **Section 2.5: Market Signals** (если `matched_markets` present):
  - `partials/market_signal.html` (см. ниже)

- **Section 3: How We Predicted**:
  - h2: "Как мы прогнозировали"
  - **Pipeline config grid** (grid-cols-2 md:grid-cols-4):
    - Количество событий (max_event_threads)
    - Количество экспертов (delphi_agents)
    - Количество раундов (delphi_rounds)
    - Количество заголовков (headlines.length)
  - **Expert consensus:**
    - Консенсус (5/5): green dot
    - Большинство (4/5): blue dot
    - Разделились (3/2): yellow dot
  - **Pipeline steps** (accordion, `fn-reasoning-block`):
    - Таблица: agent_name, duration_ms, llm_cost_usd
  - **Delphi personas** (accordion):
    - Описание 5 экспертов, количество раундов

- **Action button:** "Новый прогноз" (ссылка на `/`, button primary)

**JS-скрипт:** `results.js` (accordion для reasoning-блоков)

---

#### `/markets` — Market Dashboard (v0.9.6) (`markets.html`)

**Новое в v0.9.6:** Полный дашборд сигналов Polymarket с informed consensus.

Дашборд скрыт из основной навигации (доступен по прямой ссылке).

Структура:
- **Hero section:**
  - h1: "Сигналы prediction markets" (text-2xl)
  - Описание: "Informed consensus vs рыночная цена. Анализ основан на профилировании участников Polymarket по точности их исторических прогнозов."

- **Stats bar** (`grid grid-cols-2 sm:grid-cols-4` с `summary`):
  - Профилировано трейдеров (profiled_users)
  - Informed (top 20%)
  - Median Brier Score
  - Активные сигналы (markets.length)

- **Error state** (если `error`):
  - "Не удалось загрузить данные рынков"
  - Может быть: файл профилей не загружен, API недоступен

- **Empty state** (если нет рынков и нет ошибки):
  - "Нет активных рынков с informed consensus"
  - "Рынки появятся, когда в них будут участвовать профилированные трейдеры"

- **Fallback banner** (если есть рынки но нет informed данных):
  - "Среди текущих трейдеров нет профилированных. Показаны топ рынки по объёму торгов."

- **Market cards** (`data-stagger`):
  - Container: `bg-surface-0 border border-border rounded-lg p-5`
  - **Row 1: Title + categories:**
    - h3: ссылка на Polymarket (`https://polymarket.com/event/{{ m.slug }}`)
    - Categories chips (xs, bg-surface-1)
    - Delta badge (если has_informed): `&Delta; {{ delta_pct }}%` (красный если >10%, жёлтый если >5%, и т.д.)

  - **Row 2: Probability bars + sparkline:**
    - Рыночная цена (raw_probability): прогресс-бар text-muted/40
    - Informed consensus (если has_informed): прогресс-бар primary color
    - Sparkline (если price_history.length > 1): Chart.js canvas (120x48)

  - **Row 3: Metadata chips:**
    - Informed бетторов (если has_informed)
    - Всего бетторов
    - Coverage % (если has_informed)
    - Confidence % (если has_informed, цвет-кодированный)
    - Объём ($)

  - **Row 4: Details accordion** (если has_informed):
    - Parametric probability (%)
    - Модель
    - Доминирующий кластер
    - Ликвидность ($)
    - Дата закрытия
    - Трейдеров всего / informed

- **Disclaimer:**
  - "Данные обновляются каждые 15 минут. Informed consensus вычисляется на основе точности (Brier Score) исторических прогнозов трейдеров. Это исследовательский инструмент, не финансовая рекомендация."

**Кэширование:**
- TTL 15 минут (`_CACHE_TTL = 900`)
- Кэш в памяти MarketSignalService (`self._cache: tuple[float, list[MarketCard]]`)
- Персистентное хранилище: Parquet профилей бетторов (загружается при startup)

**API-интеграция:**
- `PolymarketClient.fetch_markets()` — Gamma API (активные рынки)
- `PolymarketClient.fetch_trades_batch(condition_ids)` — Data API (сделки для каждого рынка)
- `compute_informed_signal()` — вычисление informed consensus по профилям

**Загрузка на `/` и `/results`:**
- Если market_service инициализирован и есть headlines: поиск relевантных рынков
- Нечёткое совпадение (fuzzy_match_to_market) между текстом заголовков и вопросами Polymarket
- Максимум 5 рынков на страницу результатов

**JS-скрипт:** `markets.js` (Chart.js sparklines, hover effects)

---

#### Showcase (публичные прогнозы)

Прогнозы отмечаются флагом `is_public = True` в модели `Prediction`:

```python
is_public: Mapped[bool] = mapped_column(
    Boolean, default=False, server_default="0", nullable=False
)
```

Использование:
- На `/` (главная): таблица "Примеры прогнозов" (`repo.get_showcase(limit=5)`)
- На `/results/{id}` (если matched_markets, может быть использовано для сравнения)
- API: `PredictionRepository.get_showcase()` — выбирает `is_public = True` в порядке убывания `created_at`

Как прогноз становится публичным:
- Вручную — администратор устанавливает `is_public = True` в БД (v0.9.6 нет UI для этого)
- Или в будущем — API флаг при создании (требует расширения формы)

---

#### `/login` — Вход (`login.html`)

Структура:
- **Centred form** (max-width 28rem):
  - Поле `email` (type="email", required, autocomplete="email")
  - Поле `password` (type="password", required, minlength="8")
  - Hidden field `next` (перенаправление после входа, по умолчанию `/`)
  - Кнопка "Войти"
  - Ошибка (если неверны credentials)
  - Ссылка "Зарегистрироваться"

**Логика:**
- POST `/login` с `email`, `password`, `next`
- Если успех → set JWT-cookie (HttpOnly, SameSite=Lax, max_age=7 дней) + redirect на `next`
- Если ошибка → show error, остаться на /login

**Query params:**
- `?next=/settings` — перенаправить на `/settings` после входа
- `?error=...` — показать текст ошибки

---

#### `/register` — Регистрация (`register.html`)

Структура:
- **Same as login:** email, password, кнопка "Зарегистрироваться"
- **Validation:**
  - Пароль >= 8 символов
  - Email unique (IntegrityError → show error)

**Логика:**
- POST `/register` с `email`, `password`
- Если успех → создать пользователя, set JWT-cookie + redirect `/`
- Если ошибка → show error

---

#### `/settings` — Настройки (`settings.html`)

Требует аутентификации (redirect `/login?next=/settings` если не авторизован).

Структура:
- **Existing keys table:**
  - Столбцы: провайдер, метка (label), статус (активен/неактивен/повреждён), действия
  - Кнопки: "Проверить" (POST validate), "Удалить" (DELETE)
  - Результат validation (зелёный/красный текст)
- **Add key form:**
  - `provider` (select, только "OpenRouter")
  - `api_key` (type="password", minlength="10")
  - `label` (опциональный, maxlength="100")
  - Кнопка "Добавить"
  - Success/error сообщения

**JS-скрипт:** `settings.js` (add/delete/validate логика)

---

#### `/about` — Методология (`about.html`)

Структура:
- **Intro:** что такое Дельфи, 5 персон, 2 раунда
- **Personas section:** 5 карточек с персонами (icon, name, role, description)
- **Pipeline section:** детальное описание 9 этапов
- **Methodology deep-dive:** как работает консенсус, weighting, framing
- **References:** документы, статьи

**JS-скрипт:** `reveal.js` (scroll-reveal для элементов с `data-reveal`)

---

## Сценарии аутентификации

### Регистрация → Автовход

```
1. GET /register → форма
2. POST /register (email, password)
   ├─ Валидация (пароль >= 8, email unique)
   ├─ Hash пароля (bcrypt async)
   ├─ Создать пользователя (UUID)
   └─ Create JWT token
3. Set cookie (HttpOnly, 7 дней)
4. 302 redirect /
```

### Вход

```
1. GET /login?next=/settings → форма
2. POST /login (email, password, next)
   ├─ Найти пользователя по email
   ├─ Verify пароль (bcrypt async)
   ├─ Create JWT token
   └─ Set cookie
3. 302 redirect на next (с security check)
```

### Выход

```
1. POST /logout (POST-only, чтобы избежать prefetch-abuse)
2. Delete cookie (access_token)
3. 302 redirect /
```

### Использование токена

- **Хранение:** HttpOnly cookie `access_token`
- **Передача:** Автоматически на same-origin fetch-запросах (`credentials: "same-origin"`)
- **Проверка:** `get_current_user` dependency (из `src/api/dependencies.py`)

---

## JavaScript модули

### `form.js` — Prediction form on `/`

**Задачи:**
1. **Autocomplete (outlet field):**
   - Debounce 300ms на input
   - GET `/api/v1/outlets?q=...` при ≥2 символов
   - Dropdown с результатами
   - Keyboard nav (arrow up/down, enter, escape)
   - Если нет результатов → show "Издание не в каталоге" + reveal URL field

2. **Preset card selection:**
   - Клик на карточку → toggle `fn-preset-card--selected` класс
   - Light vs Opus выбор

3. **Date validation:**
   - Browser-native min/max validation
   - Custom validity message если дата в прошлом

4. **Form submission:**
   - POST `/api/v1/predictions` (JSON)
   - Payload: `{ outlet, target_date, preset, api_key?, outlet_url? }`
   - Disable кнопка + `aria-busy="true"`
   - Если `outlet_resolved === false` → show warning 2s потом redirect
   - Else → 302 redirect на `/predict/{id}`

**DOM IDs:**
- `#prediction-form`, `#outlet`, `#outlet-suggestions`, `#target_date`, `#outlet-url-group`, `#outlet_url`, `#api_key`, `#submit-btn`, `#form-error`

---

### `progress.js` — SSE progress on `/predict/{id}` (v0.9.6)

**Инициализация:**
1. Parse config из `<script id="progress-config" type="application/json">`
2. Fetch REST `/api/v1/predictions/{id}` для state-restore после refresh
3. Connect SSE на `/api/v1/predictions/{id}/stream`

**SSE event handling:**
- Event format: `{ stage, message, progress, detail, elapsed_ms, cost_usd }`
- Update `<progress value=...>` (0–100%)
- Update step icons (pending → active → done)
- Update `#narrative-area` (right sidebar desktop) и `#narrative-area-mobile` (below steps)
- Track duration per stage (in stageStartTimes map)

**Stage progression:**
```javascript
const STAGES = [
  'collection',
  'event_identification',
  'trajectory',
  'delphi_r1',
  'delphi_r2',
  'consensus',
  'framing',
  'generation',
  'quality_gate'
];
const STAGE_PROGRESS = {
  'collection': 5,
  'event_identification': 20,
  'trajectory': 30,
  'delphi_r1': 40,
  'delphi_r2': 55,
  'consensus': 70,
  'framing': 80,
  'generation': 88,
  'quality_gate': 95
};
```

**Step state transitions:**
- Update step: `.fn-step--pending` → `.fn-step--active` → `.fn-step--done`
- Pending: circle icon `○` (CSS counter номер)
- Active: gradient shimmer background + animate-shimmer
- Done: circle icon заменяется точкой с scale-in анимацией

**Detail inline updates:**
- `.fn-step-detail` (inside `.fn-step-content`) заполняется из SSE `detail` поля
- `.fn-step-duration` (shrink-0) заполняется и показывается (fade-in) когда duration_ms известна

**Narrative sidebar:**
- Desktop: `#narrative-area` (sticky top-6)
- Mobile: `#narrative-area-mobile` (text-center)
- Заполняется из SSE `message` поля
- Fade-in при обновлении

**Completion:**
- SSE event `stage: "completed"` → 1.5-second delay → redirect `/results/{id}`

**Error handling:**
- SSE event `stage: "failed"` → show `#error-section`, close connection
- Stall detection — отключено в текущей версии (функция `checkStall()` — no-op)
- Network error (SSE drops) → fallback to polling `/api/v1/predictions/{id}` every 5s

**DOM IDs:**
- `#progress-bar`, `#progress-percent`, `#progress-elapsed`
- `#step-list`, `.fn-step[data-stage]`
- `#narrative-area`, `#narrative-message`
- `#narrative-area-mobile`, `#narrative-message-mobile`
- `#error-section`, `#error-message`
- `#stall-warning`, `#stall-message`

---

### `results.js` — Accordion on `/results/{id}`

**Задачи:**
1. **Reasoning block accordion:**
   - Селект все `[data-stagger] .fn-reasoning-block` (reasoning-блоки внутри headline cards)
   - При открытии одного `<details>` → закрыть остальные в той же секции
   - Другие `<details>` (в методологии, market signals) остаются независимыми

**Логика:** один открытый reasoning-блок за раз в headline section, улучшает UX на мобильных.

---

### `settings.js` — API key management on `/settings`

**Задачи:**

1. **Add key form:**
   - POST `/api/v1/keys` (JSON): `{ provider, api_key, label }`
   - Validate: api_key >= 10 символов
   - Show success/error
   - On success: reload страница через 800ms

2. **Delete key button:**
   - Confirm() перед удалением
   - DELETE `/api/v1/keys/{id}`
   - On success: reload

3. **Validate key button:**
   - POST `/api/v1/keys/{id}/validate`
   - Show result (green "Ключ валиден" или red "Ключ невалиден")

**DOM selectors:**
- `#add-key-form`, `#add-key-btn`, `#add-key-error`, `#add-key-success`
- `.fn-delete-btn[data-key-id]`, `.fn-validate-btn[data-key-id]`, `.fn-validate-result[data-key-id]`

---

### `markets.js` — Chart.js sparklines on `/markets`

**Задачи:**
1. Найти все `canvas.fn-sparkline` с атрибутом `data-prices`
2. Parse JSON array из data-prices
3. Создать Chart.js sparkline (no axes, no legend)
4. Render историю цен как мини-линейный график

---

### `reveal.js` — Scroll reveal on `/about`

**Задачи:**
1. Найти все элементы с атрибутом `data-reveal`
2. IntersectionObserver (threshold 0.1) — при входе в viewport
3. Добавить класс `fn-revealed`
4. CSS правило: `.fn-revealed { animation: fn-fade-in ... }`

---

## Дизайн-система

### Цветовая палитра (Tailwind + OKLCH)

**Confidence levels** (для уровней уверенности):
- `bg-confidence-very-high` — зелёный (80–100%)
- `bg-confidence-high` — синий (60–79%)
- `bg-confidence-moderate` — жёлтый/оранжевый (40–59%)
- `bg-confidence-low` — оранжевый (20–39%)
- `bg-confidence-speculative` — красный (0–19%)

**Surfaces & Text:**
- `bg-surface-0`, `bg-surface-1`, `bg-surface-2` — фон (светлые серые)
- `text-text`, `text-text-heading`, `text-text-muted` — текст
- `border-border` — граница

**Primary:**
- `bg-primary`, `text-primary` — основной цвет (синий)

### Компоненты (`fn-*` классы)

| Компонент | Класс | Назначение |
|-----------|-------|-----------|
| Автодополнение | `.fn-autocomplete-dropdown`, `.fn-autocomplete-active` | Dropdown list |
| Карточка заголовка | `.fn-headline-card` | Разделитель-секция (bottom border, padding) |
| Reasoning блок | `.fn-reasoning-block`, `.fn-reasoning-animated` | `<details>` + animate |
| Шаг | `.fn-step`, `.fn-step--{pending,active,done}`, `.fn-step--stalled` | Timeline шаг |
| Фаза | `.fn-step-phase` | Заголовок группы шагов |
| Timeline | `.fn-timeline` | Вертикальная линия с шагами |
| Preset карточка | `.fn-preset-card`, `.fn-preset-card--selected` | Выбор режима |
| Progress meta | `.fn-progress-meta` | Процент + elapsed time |
| Sparkline | `.fn-sparkline` | Chart.js мини-график |

### Анимации

- `animate-fade-in` — opacity 0→1 (300ms)
- `animate-fade-in-up` — opacity + translateY (500ms)
- `animate-fade-in-up [animation-delay:100ms]` — cascade delay
- `animate-slide-in-left` — translateX слева
- `animate-scale-in` — scale + fade (300ms, для checkmark точек)
- `animate-shimmer` — gradient-position animation (2s, для active steps и progress bar)
- `animate-pulse-opacity` — opacity pulsation (1.5s)
- `animate-shake` — shake effect (400ms)

**Stagger детей:**
```html
<div data-stagger>
  <div style="--fn-stagger-i: 0">item 1</div>
  <div style="--fn-stagger-i: 1">item 2</div>
  <div style="--fn-stagger-i: 2">item 3</div>
</div>
```
CSS: `animation-delay: calc(var(--fn-stagger-i) * 80ms)`

---

## Обработка ошибок

### На форме (`/`)

```javascript
showError("Укажите название СМИ");  // показать ошибку
showError("");                       // скрыть ошибку
```

### На странице прогресса (`/predict`)

- SSE `stage: "failed"` → show `#error-section`
- Stall warning (> 120s) → show `#stall-warning`, add `.fn-step--stalled` to active step
- Network error (SSE drops) → fallback to polling

### На странице результатов (`/results`)

- Если прогноз не завершён → show progress page (redirect)
- 403 если не owner → HTTPException (FastAPI)

### На странице настроек (`/settings`)

- Защита: require `get_current_user` → redirect `/login?next=/settings`
- Ошибки API добавления ключа → show `#add-key-error`
- Success → show `#add-key-success` + reload

---

## Безопасность

### CSRF Protection

- Все POST-формы содержат hidden field: `<input type="hidden" name="csrf_token" value="{{ request.state.csrf_token | default('') }}">`
- Генерируется middleware (смотри `src/api/middleware.py`)

### JWT в HttpOnly Cookie

- Set-Cookie: `access_token=...; HttpOnly; SameSite=Lax; Secure (только https)`
- Immune to XSS (JS не может читать)
- Automatic передача на same-origin fetch (`credentials: "same-origin"`)

### Ownership Check

```python
def _check_prediction_ownership(prediction: Prediction, user: User | None) -> None:
    # prediction.user_id is None → all can access (anonymous)
    # user is None → all can access (backward compat)
    # prediction.user_id != user.id → 403 Forbidden
```

### Open Redirect Prevention

```python
def _safe_redirect_url(url: str) -> str:
    # Only allows relative paths starting with /
    # Rejects //, newlines, absolute URLs
    if not url or not url.startswith("/") or url.startswith("//") or "\n" in url:
        return "/"
    return url
```

---

## Производительность

### Asset loading

- **CSS:** `link rel="stylesheet" href="...?v={{ app_version }}"` — cache busting
- **JS:** `<script src="...?v={{ app_version }}"></script>` — lazy loading (only when needed)
- **Fonts:** Google Fonts с `font-display: swap` (текст показывается сразу)

### Page speed

- Page load: ~1.3–1.5s (Lighthouse slow 3G)
- No frameworks, Vanilla JS only
- CSS: Tailwind utility + 17 `fn-*` компонентов (PurgeCSS очищает неиспользуемые)

### Network

- Form submission: fetch (не form submit) для better UX
- SSE: persistent connection для real-time прогресса
- Fallback polling: если SSE drops, переключиться на REST polling
- Market data: 15-minute cache in-memory (MarketSignalService)

---

## Локальная разработка

### Watch CSS changes

```bash
npm run css:dev  # Tailwind watch mode: input.css → tailwind.css
```

### Run dev server

```bash
uv run uvicorn src.main:app --reload --port 8000
```

### Test in browser

```
http://localhost:8000/
http://localhost:8000/login
http://localhost:8000/settings  # requires auth
http://localhost:8000/markets   # market dashboard
http://localhost:8000/predict/{id}  # progress page (with running prediction)
http://localhost:8000/results/{id}  # results page
```

---

## Файловая структура

```
src/web/
├── router.py                          # FastAPI маршруты (GET/POST)
├── market_service.py                  # MarketSignalService (informed consensus)
├── templates/
│   ├── base.html                      # Базовый макет
│   ├── index.html                     # Главная
│   ├── progress.html                  # Прогресс (SSE, v0.9.6)
│   ├── results.html                   # Результаты (v0.9.6)
│   ├── markets.html                   # Market dashboard (v0.9.6)
│   ├── about.html                     # Методология
│   ├── login.html                     # Вход
│   ├── register.html                  # Регистрация
│   ├── settings.html                  # Настройки (API-ключи)
│   └── partials/
│       ├── headline_card.html         # Карточка заголовка (unified)
│       ├── reasoning_block.html       # Reasoning блок (aккордион)
│       └── market_signal.html         # Polymarket сигналы (matched markets)
└── static/
    ├── css/
    │   ├── input.css                  # Tailwind source + @theme
    │   └── tailwind.css               # Compiled (committed)
    ├── js/
    │   ├── form.js                    # Autocomplete + submit
    │   ├── progress.js                # SSE + progress tracking (v0.9.6)
    │   ├── results.js                 # Accordion reasoning-blocks
    │   ├── settings.js                # Add/delete/validate keys
    │   ├── markets.js                 # Sparklines + market interactions (v0.9.6)
    │   └── reveal.js                  # Scroll-reveal animations
    ├── img/
    │   └── favicon.svg
    └── ...
```

---

## Часто задаваемые вопросы

### Как добавить новый маршрут?

1. Добавить функцию в `src/web/router.py`:
   ```python
   @router.get("/new-page", response_class=HTMLResponse)
   async def new_page(request: Request):
       return templates.TemplateResponse(request, "new-page.html", {...})
   ```

2. Создать шаблон `src/web/templates/new-page.html`:
   ```jinja2
   {% extends "base.html" %}
   {% block title %}New Page{% endblock %}
   {% block content %}...{% endblock %}
   ```

3. (опционально) Добавить JS в `src/web/static/js/new-page.js`

### Как проверить авторизацию?

```python
from src.api.dependencies import get_current_user

@router.get("/protected")
async def protected_page(user: User | None = Depends(get_current_user)):
    if user is None:
        return RedirectResponse(url="/login?next=/protected")
    # ...
```

### Как отправить данные на сервер?

```javascript
// Fetch с JWT-cookie (автоматически)
await fetch("/api/v1/...", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "same-origin",  // Передаёт JWT-cookie
  body: JSON.stringify({...})
});
```

### Как добавить анимацию?

```html
<div class="animate-fade-in-up [animation-delay:100ms]">...</div>
```

CSS уже определён в `input.css` (`@keyframes fn-fade-in-up`).

### Как добавить CSS-счётчик (как на progress page)?

```html
<ul class="fn-timeline">
  <li class="fn-step fn-step--done">
    <span class="fn-step-icon"></span>
    <!-- номер будет из counter(step) через ::before -->
  </li>
</ul>
```

CSS:
```css
.fn-timeline {
  counter-reset: step;
}
.fn-step[data-stage] {
  counter-increment: step;
}
.fn-step-icon::before {
  content: counter(step);  /* 1, 2, 3, ... */
}
```

---

## Тестирование

### Unit-тесты маршрутов

```bash
pytest tests/test_web/ -v
```

Проверяются:
- Status codes (200, 302, 403)
- Context variables (шаблон передал правильные переменные)
- Redirect logic (auth, completion)

### Manual testing

1. **Regression на главной:** заполнить форму, отправить, проверить прогресс
2. **Auth flow:** register → login → settings → logout
3. **Progress page:** открыть /predict/{id}, проверить SSE, narrative updates, stagger animation
4. **Results page:** проверить headline cards, timeline, reasoning blocks, market signals
5. **Markets dashboard:** открыть /markets, проверить informed consensus, sparklines
6. **Ownership:** создать прогноз, потом попробовать доступ с другого пользователя (403)
7. **Mobile:** открыть на мобильнике, проверить responsive design + hamburger nav + narrative mirror

---

## Дополнительное чтение

- **Frontend spec:** `docs/09-frontend.md` — полная дизайн-система (OKLCH, spacing, motion)
- **Backend routes:** `docs/08-api-backend.md` — REST API контракт
- **Architecture:** `docs/architecture.md` — общая архитектура пайплайна
- **Inverse module:** `docs/*/polymarket_inverse_problem.md` — Polymarket analysis, bettor profiling, informed consensus
- **Market service:** `src/web/market_service.py` — сервис для загрузки и кэширования рыночных сигналов
