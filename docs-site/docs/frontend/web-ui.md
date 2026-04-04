# Web UI Documentation

> **Реализация**: `src/web/router.py`, `src/web/templates/*.html`, `src/web/static/js/*.js`  
> **Спека**: `docs/09-frontend.md`

Веб-интерфейс Delphi Press — это однопаршиновое приложение на Jinja2 + Tailwind CSS v4 + Vanilla JS (ES2022). Все маршруты переходят в отдельные HTML-страницы (no SPA), каждая с собственным набором скриптов.

## Архитектура маршрутизации

### HTML-маршруты

Все маршруты определены в `src/web/router.py` и возвращают полные HTML-страницы:

| Маршрут | Метод | Аутентификация | Описание |
|---------|-------|---|---|
| `/` | GET | Нет | Главная страница с формой прогноза + недавние/примеры прогнозов |
| `/predict/{prediction_id}` | GET | Нет* | Страница прогресса (SSE) или автоматический переход на результаты |
| `/results/{prediction_id}` | GET | Нет* | Завершённые результаты с карточками заголовков + timeline |
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
- **Showcase predictions:** таблица 5 публичных прогнозов
- **My predictions:** таблица пользовательских прогнозов (только для авторизованных)

**JS-скрипт:** `form.js` (загружается в `{% block extra_js %}`)

---

#### `/predict/{id}` — Прогресс (`progress.html`)

Структура:
- **Header:** название издания, целевая дата, статус
- **Progress bar:** `<progress>` элемент + процент + elapsed time
- **Two-column layout:**
  - **Левая колонка:** список шагов (timeline с иконками)
    - Фаза 1: Сбор данных (collection, event_identification)
    - Фаза 2: Экспертный анализ (trajectory, delphi_r1, delphi_r2, consensus)
    - Фаза 3: Генерация (framing, generation, quality_gate)
    - Каждый шаг содержит описание, детали и duration
  - **Правая колонка (desktop):** "Сейчас происходит" — narrativeблок с текущей активностью
  - **Mobile:** narrative-блок под шагами
- **Info banner:** "Формирование займёт 30–40 минут, не перезагружайте"
- **Stall warning:** (скрыта, появляется если нет активности > 120s)
- **Error section:** (скрыта, появляется при failure)

**Логика перехода:**
- Если прогноз уже завершён → автоматический 302 redirect на `/results/{id}`
- Если ещё в процессе → показать прогресс-страницу

**JS-скрипт:** `progress.js` (SSE-подключение + UI-обновления)

---

#### `/results/{id}` — Результаты (`results.html`)

Структура:
- **Header:** название издания, дата, чипсы (duration, cost, preset)
- **Section 1: Headline Cards** (карточки заголовков):
  - Для каждого заголовка: `partials/headline_card.html`
  - Ранг (#1, #2, ...), badge уверенности, категория
  - Основной текст (serif, крупный), первый параграф, краткое обоснование
  - Расширяемый блок с полным reasoning (аккордион)
- **Section 2: Timeline** (events timeline):
  - Список ключевых событий с вероятностями
  - Каждое событие в `fn-step` с номером, описанием, датой, вероятностью
  - Опциональные детали: неопределённость (±дни), wild card flag, causal dependencies
  - Расширяемые reasoning-блоки
- **Section 2.5: Market Signals** (если есть):
  - `partials/market_signal.html` — соответствия Polymarket-рынков
- **Section 3: How We Predicted**:
  - **Pipeline config:** сетка 2x2 (события, эксперты, раунды, заголовки)
  - **Expert consensus:** консенсус/большинство/разделились (с color dots)
  - **Pipeline steps:** аккордион с таблицей всех этапов (agent_name, duration, cost)
  - **Delphi personas:** аккордион с описанием 5 экспертов
- **Action button:** "Новый прогноз" (ссылка на `/`)

**JS-скрипт:** `results.js` (accordion для reasoning-блоков)

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

### `progress.js` — SSE progress on `/predict/{id}`

**Задачи:**
1. **Initialization:**
   - Parse config из `<script id="progress-config" type="application/json">`
   - Fetch REST `/api/v1/predictions/{id}` для state-restore после refresh
   - Connect SSE на `/api/v1/predictions/{id}/stream`

2. **SSE event handling:**
   - Event format: `{ stage, message, progress, detail, elapsed_ms, cost_usd }`
   - Update progress bar (0–100%)
   - Update step icons (pending → active → done)
   - Update narrative area (right sidebar desktop, below steps on mobile)
   - Track duration per stage (in stageStartTimes)

3. **Stage progression:**
   - STAGES ordered list: collection → event_identification → trajectory → delphi_r1 → delphi_r2 → consensus → framing → generation → quality_gate
   - STAGE_PROGRESS map (5%, 20%, 30%, ..., 95%)
   - Update step status: circle ○ → filled ● → checkmark ✓

4. **Completion:**
   - SSE event `stage: "completed"` → 3-second delay → 302 redirect `/results/{id}`

5. **Error handling:**
   - SSE event `stage: "failed"` → show error section, close connection
   - Stall detection (>120s no event) → show warning banner
   - Network error (SSE drops) → fallback to polling `/api/v1/predictions/{id}` every 5s

**DOM IDs:**
- `#progress-bar`, `#progress-percent`, `#progress-elapsed`, `#step-list`, `#narrative-area`, `#narrative-message`, `#narrative-area-mobile`, `#narrative-message-mobile`, `#error-section`, `#error-message`, `#stall-warning`, `#stall-message`

**Data attributes:**
- `<li data-stage="collection">` — каждый шаг должен иметь дата-атрибут

---

### `results.js` — Accordion on `/results/{id}`

**Задачи:**
1. **Reasoning block accordion:**
   - Селект все `[data-stagger] .fn-reasoning-block` (reasoning-блоки внутри headline cards)
   - При открытии одного `<details>` → закрыть остальные в той же секции
   - Другие `<details>` (в методологии) остаются независимыми

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
| Автодополнение | `.fn-autocomplete-wrapper`, `.fn-autocomplete-dropdown`, `.fn-autocomplete-active` | Dropdown list |
| Бейджик | `.fn-badge`, `.fn-badge--{success,info,danger}` | Статус, уровень |
| Карточка заголовка | `.fn-headline-card`, `.fn-headline-card--{hero,secondary}` | Карточка с заголовком |
| Reasoning блок | `.fn-reasoning-block`, `.fn-reasoning-animated` | `<details>` + animate |
| Чип | `.fn-meta-chip` | Дата, время, стоимость |
| Шаг | `.fn-step`, `.fn-step--{pending,active,done}` | Timeline шаг |
| Timeline | `.fn-timeline`, `.fn-step-list` | Вертикальная линия |
| Preset карточка | `.fn-preset-card`, `.fn-preset-card--selected` | Выбор режима |

### Анимации

- `animate-fade-in` — opacity 0→1
- `animate-fade-in-up` — opacity + translateY
- `animate-fade-in-up [animation-delay:100ms]` — cascade delay

---

## Обработка ошибок

### На форме (`/`)

```javascript
showError("Укажите название СМИ");  // показать ошибку
showError("");                       // скрыть ошибку
```

### На странице прогресса (`/predict`)

- SSE `stage: "failed"` → show `#error-section`
- Stall warning (> 120s) → show `#stall-warning`
- Network error → fallback to polling

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

- Page load: ~1.3–1.5s (Lighthouse медленный 3G)
- No frameworks, Vanilla JS only
- CSS: Tailwind utility + 17 `fn-*` компонентов (PurgeCSS очищает неиспользуемые)

### Network

- Form submission: fetch (не form submit) для better UX
- SSE: persistent connection для real-time прогресса
- Fallback polling: если SSE drops, переключиться на REST polling

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
```

---

## Файловая структура

```
src/web/
├── router.py                          # FastAPI маршруты (GET/POST)
├── templates/
│   ├── base.html                      # Базовый макет
│   ├── index.html                     # Главная
│   ├── progress.html                  # Прогресс (SSE)
│   ├── results.html                   # Результаты
│   ├── about.html                     # Методология
│   ├── login.html                     # Вход
│   ├── register.html                  # Регистрация
│   ├── settings.html                  # Настройки (API-ключи)
│   └── partials/
│       ├── headline_card.html         # Карточка заголовка
│       ├── reasoning_block.html       # Reasoning блок (аккордион)
│       └── market_signal.html         # Polymarket сигналы
└── static/
    ├── css/
    │   ├── input.css                  # Tailwind source + @theme
    │   └── tailwind.css               # Compiled (committed)
    ├── js/
    │   ├── form.js                    # Autocomplete + submit
    │   ├── progress.js                # SSE + progress tracking
    │   ├── results.js                 # Accordion reasoning-blocks
    │   ├── settings.js                # Add/delete/validate keys
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
3. **Ownership:** создать прогноз, потом попробовать доступ с другого пользователя (403)
4. **Mobile:** открыть на мобильнике, проверить responsive design + hamburger nav

---

## Дополнительное чтение

- **Frontend spec:** `docs/09-frontend.md` — полная дизайн-система (OKLCH, spacing, motion)
- **Backend routes:** `docs/08-api-backend.md` — REST API контракт
- **Architecture:** `docs/architecture.md` — общая архитектура пайплайна
