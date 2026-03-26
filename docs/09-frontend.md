# 09 -- Frontend: шаблоны, стили, JavaScript

> Реализуемые файлы: `src/web/templates/base.html`, `index.html`, `progress.html`, `results.html`, `about.html`, `partials/headline_card.html`, `partials/reasoning_block.html`, `src/web/static/css/custom.css`, `src/web/static/js/form.js`, `src/web/static/js/progress.js`, `src/web/static/js/results.js`, `src/web/router.py`
> Зависимости: Pico.css 2.0 (CDN), Vanilla JS (ES2022), Jinja2 3.1+, FastAPI

---

## Обзор

Фронтенд -- server-rendered HTML через Jinja2 + минимальный клиентский JavaScript для интерактивных элементов (SSE, autocomplete, accordion). Никаких фреймворков: ни React, ни Vue, ни Angular.

Принципы:

- **"Grandmother-friendly"**: интерфейс должен быть понятен нетехническому пользователю
- **Semantic HTML first**: Pico.css стилизует HTML-элементы без классов -- используем семантику по максимуму
- **Progressive enhancement**: страница работает без JavaScript (кроме `progress.html`, где SSE критичен)
- **Mobile-first**: все страницы адаптивны, начиная с мобильного layout
- **Минимальный CSS**: `custom.css` только для специфических компонентов (бейджи, карточки, прогресс)
- **Один запрос -- один экран**: нет SPA-навигации, каждый маршрут = отдельная страница

---

## 1. Design System

### 1.1 Базовый фреймворк: Pico.css 2.0

Pico.css подключается через CDN. Он обеспечивает:
- Типографику на системных шрифтах (быстрая загрузка, нативный вид)
- Стилизацию форм, кнопок, таблиц без классов
- Тёмную/светлую тему через `data-theme` на `<html>`
- Responsive контейнер `<main class="container">`
- Сетку через `<div class="grid">`

CDN-ссылка:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
```

### 1.2 Цветовая схема

Используем Pico.css defaults (светлая тема), перекрывая минимальный набор переменных в `custom.css`:

| Назначение | CSS-переменная | Значение | Обоснование |
|---|---|---|---|
| Основной accent | `--pico-primary` | `#2563eb` | Синий -- профессиональный, нейтральный, хорошая читаемость |
| Primary hover | `--pico-primary-hover` | `#1d4ed8` | Чуть темнее для hover-состояния |
| Background | `--pico-background-color` | `#ffffff` | Белый фон, чисто и просто |
| Card background | `--fn-card-bg` | `#f8fafc` | Слегка серый для карточек, создаёт визуальное разделение |
| Card border | `--fn-card-border` | `#e2e8f0` | Мягкая серая граница |
| Success (green) | `--fn-confidence-very-high` | `#16a34a` | Зелёный -- очень высокая уверенность |
| Info (blue) | `--fn-confidence-high` | `#2563eb` | Синий -- высокая уверенность |
| Warning (amber) | `--fn-confidence-moderate` | `#d97706` | Янтарный -- средняя уверенность |
| Caution (orange) | `--fn-confidence-low` | `#ea580c` | Оранжевый -- низкая уверенность |
| Danger (red) | `--fn-confidence-speculative` | `#dc2626` | Красный -- спекулятивно |
| Step done | `--fn-step-done` | `#16a34a` | Зелёный чекмарк |
| Step active | `--fn-step-active` | `#2563eb` | Синий пульсирующий |
| Step pending | `--fn-step-pending` | `#94a3b8` | Серый |

### 1.3 Типографика

Системные шрифты через Pico.css (не подключаем внешние шрифты):
```
font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```

Размеры:
- Hero headline: `2.5rem` (мобильный: `1.75rem`)
- Section heading (`h2`): `1.75rem`
- Card headline: `1.25rem`
- Body text: `1rem` (16px)
- Small/meta: `0.875rem`

### 1.4 Spacing и Layout

- Контейнер: `<main class="container">` с max-width 960px (Pico default)
- Section spacing: `3rem` между секциями
- Card padding: `1.5rem`
- Mobile: padding уменьшается до `1rem`

---

## 2. Web Router (`src/web/router.py`)

FastAPI router, обслуживающий HTML-страницы. Монтируется в `src/main.py`.

```python
"""src/web/router.py -- HTML page routes.

Serves Jinja2-rendered pages for the web interface.
All user-facing text is in Russian; code comments in English.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.db.repositories import PredictionRepository

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="src/web/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page with prediction form and recent predictions."""
    repo = PredictionRepository()
    recent = await repo.get_recent(limit=5)

    tomorrow = date.today() + timedelta(days=1)
    max_date = date.today() + timedelta(days=30)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recent_predictions": recent,
            "min_date": tomorrow.isoformat(),
            "max_date": max_date.isoformat(),
        },
    )


@router.get("/predict/{prediction_id}", response_class=HTMLResponse)
async def prediction_progress(request: Request, prediction_id: str):
    """Progress page -- shows SSE-driven progress while pipeline runs."""
    repo = PredictionRepository()
    prediction = await repo.get_by_id(prediction_id)

    if prediction and prediction.status == "completed":
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "prediction": prediction,
            },
        )

    return templates.TemplateResponse(
        "progress.html",
        {
            "request": request,
            "prediction_id": prediction_id,
            "outlet": prediction.outlet if prediction else "...",
            "target_date": prediction.target_date.isoformat() if prediction else "...",
        },
    )


@router.get("/results/{prediction_id}", response_class=HTMLResponse)
async def prediction_results(request: Request, prediction_id: str):
    """Results page -- displays completed prediction with headline cards."""
    repo = PredictionRepository()
    prediction = await repo.get_by_id(prediction_id)

    if not prediction or prediction.status != "completed":
        return templates.TemplateResponse(
            "progress.html",
            {
                "request": request,
                "prediction_id": prediction_id,
                "outlet": prediction.outlet if prediction else "...",
                "target_date": (
                    prediction.target_date.isoformat() if prediction else "..."
                ),
            },
        )

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "prediction": prediction,
        },
    )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About / Methodology page."""
    return templates.TemplateResponse(
        "about.html",
        {"request": request},
    )
```

---

## 3. Base Template (`base.html`)

Базовый layout, от которого наследуются все страницы.

```html
{# src/web/templates/base.html -- Base layout for all pages. #}
<!doctype html>
<html lang="ru" data-theme="light">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">

    <title>{% block title %}Foresighting News{% endblock %}</title>
    <meta name="description" content="Прогнозирование заголовков СМИ с помощью мультиагентного ИИ">

    {# Pico.css -- semantic HTML framework, no classes needed for most elements #}
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">

    {# Project-specific overrides -- confidence badges, progress indicators, cards #}
    <link rel="stylesheet" href="{{ url_for('static', path='css/custom.css') }}">

    <link rel="icon" href="{{ url_for('static', path='img/favicon.svg') }}" type="image/svg+xml">

    {% block extra_head %}{% endblock %}
</head>
<body>

    {# ===== NAVIGATION ===== #}
    <nav class="container">
        <ul>
            <li>
                <a href="/" class="fn-logo">
                    <strong>Foresighting News</strong>
                </a>
            </li>
        </ul>
        <ul>
            <li><a href="/">Главная</a></li>
            <li><a href="/about">О методологии</a></li>
        </ul>
    </nav>

    {# ===== MAIN CONTENT ===== #}
    <main class="container">
        {% block content %}{% endblock %}
    </main>

    {# ===== FOOTER ===== #}
    <footer class="container">
        <hr>
        <div class="grid">
            <div>
                <small>
                    &copy; {{ current_year | default(2026) }} Foresighting News.
                    Прогнозы носят исследовательский характер.
                </small>
            </div>
            <div style="text-align: right;">
                <small>
                    Powered by AI
                    &middot;
                    <a href="https://github.com/your-repo/foresighting-news"
                       target="_blank"
                       rel="noopener noreferrer">
                        GitHub
                    </a>
                </small>
            </div>
        </div>
    </footer>

    {% block extra_js %}{% endblock %}

</body>
</html>
```

---

## 4. Страница: Главная (`index.html`)

Задача: вовлечь пользователя, объяснить суть за 10 секунд, дать ввести запрос.

```html
{# src/web/templates/index.html -- Landing page with prediction form. #}
{% extends "base.html" %}

{% block title %}Foresighting News -- Прогноз заголовков СМИ{% endblock %}

{% block content %}

{# ===== HERO SECTION ===== #}
<section class="fn-hero">
    <hgroup>
        <h1>Что напишут СМИ завтра?</h1>
        <p>
            Мультиагентная система прогнозирования заголовков.
            Пять ИИ-экспертов анализируют события и предсказывают,
            о чём будет писать выбранное издание.
        </p>
    </hgroup>
</section>

{# ===== HOW IT WORKS ===== #}
<section>
    <div class="grid">
        <div>
            <hgroup>
                <h3>1. Выберите СМИ</h3>
                <p>Укажите издание: ТАСС, РБК, BBC Russian, Незыгарь или любое другое</p>
            </hgroup>
        </div>
        <div>
            <hgroup>
                <h3>2. Укажите дату</h3>
                <p>На какой день нужен прогноз -- от завтра до +30 дней</p>
            </hgroup>
        </div>
        <div>
            <hgroup>
                <h3>3. Получите прогноз</h3>
                <p>Система соберёт данные, проведёт экспертный анализ и выдаст заголовки с обоснованиями</p>
            </hgroup>
        </div>
    </div>
</section>

{# ===== PREDICTION FORM ===== #}
<section>
    <article>
        <header>
            <h2>Новый прогноз</h2>
        </header>

        <form id="prediction-form" action="/api/v1/predictions" method="post">

            {# -- Outlet field with autocomplete -- #}
            <label for="outlet">
                СМИ
                <div class="fn-autocomplete-wrapper">
                    <input
                        type="text"
                        id="outlet"
                        name="outlet"
                        placeholder="Начните вводить название, например: ТАСС"
                        autocomplete="off"
                        required
                        aria-describedby="outlet-help"
                    >
                    <ul id="outlet-suggestions" class="fn-autocomplete-dropdown" role="listbox" hidden></ul>
                </div>
                <small id="outlet-help">Название издания на русском или английском</small>
            </label>

            {# -- Target date field -- #}
            <label for="target_date">
                Дата прогноза
                <input
                    type="date"
                    id="target_date"
                    name="target_date"
                    min="{{ min_date }}"
                    max="{{ max_date }}"
                    required
                    aria-describedby="date-help"
                >
                <small id="date-help">От завтра до +30 дней</small>
            </label>

            {# -- Submit -- #}
            <button type="submit" id="submit-btn">
                Прогнозировать
            </button>

        </form>

        {# -- Error display area -- #}
        <div id="form-error" class="fn-form-error" hidden role="alert"></div>

    </article>
</section>

{# ===== RECENT PREDICTIONS ===== #}
{% if recent_predictions %}
<section>
    <h2>Последние прогнозы</h2>
    <div class="overflow-auto">
        <table>
            <thead>
                <tr>
                    <th scope="col">СМИ</th>
                    <th scope="col">Дата</th>
                    <th scope="col">Статус</th>
                    <th scope="col">Топ-заголовок</th>
                    <th scope="col"></th>
                </tr>
            </thead>
            <tbody>
                {% for pred in recent_predictions %}
                <tr>
                    <td>{{ pred.outlet }}</td>
                    <td>{{ pred.target_date.strftime('%d.%m.%Y') }}</td>
                    <td>
                        {% if pred.status == 'completed' %}
                            <span class="fn-badge fn-badge--success">Готово</span>
                        {% elif pred.status == 'in_progress' %}
                            <span class="fn-badge fn-badge--info">В процессе</span>
                        {% elif pred.status == 'failed' %}
                            <span class="fn-badge fn-badge--danger">Ошибка</span>
                        {% else %}
                            <span class="fn-badge">{{ pred.status }}</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if pred.headlines %}
                            {{ pred.headlines[0].headline | truncate(60) }}
                        {% else %}
                            --
                        {% endif %}
                    </td>
                    <td>
                        {% if pred.status == 'completed' %}
                            <a href="/results/{{ pred.id }}" role="button" class="outline secondary">
                                Результаты
                            </a>
                        {% elif pred.status == 'in_progress' %}
                            <a href="/predict/{{ pred.id }}" role="button" class="outline">
                                Следить
                            </a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</section>
{% endif %}

{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', path='js/form.js') }}"></script>
{% endblock %}
```

---

## 5. Страница: Прогресс (`progress.html`)

Показывается пока пайплайн работает. Ключевой интерактивный элемент -- SSE-подключение.

```html
{# src/web/templates/progress.html -- Real-time progress via SSE. #}
{% extends "base.html" %}

{% block title %}Прогноз для {{ outlet }} -- Foresighting News{% endblock %}

{% block content %}

<section>
    <hgroup>
        <h1>Формируем прогноз</h1>
        <p>
            <strong>{{ outlet }}</strong> &middot; {{ target_date }}
        </p>
    </hgroup>
</section>

{# ===== PROGRESS BAR ===== #}
<section>
    <progress id="progress-bar" value="0" max="100"></progress>
    <div class="fn-progress-meta">
        <span id="progress-percent">0%</span>
        <span id="progress-elapsed"></span>
    </div>
</section>

{# ===== STEP LIST ===== #}
<section>
    <article>
        <ul id="step-list" class="fn-step-list">
            <li class="fn-step fn-step--pending" data-stage="collection">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Собираем новости</strong>
                    <small>RSS-фиды, поисковые системы, архивы издания</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="event_identification">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Выявляем ключевые события</strong>
                    <small>Кластеризация сигналов, определение трендов</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="trajectory">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Анализируем траектории событий</strong>
                    <small>Сценарии развития, перекрёстные влияния</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="delphi_r1">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Экспертная панель: раунд 1</strong>
                    <small>Пять ИИ-экспертов независимо оценивают ситуацию</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="delphi_r2">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Экспертная панель: раунд 2</strong>
                    <small>Медиация расхождений, уточнение прогнозов</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="consensus">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Формируем консенсус</strong>
                    <small>Агрегация оценок, калибровка вероятностей</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="framing">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Анализируем стиль издания</strong>
                    <small>Как {{ outlet }} подаст каждое событие</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="generation">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Генерируем заголовки</strong>
                    <small>Стилизация под формат издания</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
            <li class="fn-step fn-step--pending" data-stage="quality_gate">
                <span class="fn-step-icon" aria-hidden="true">&#9675;</span>
                <div class="fn-step-content">
                    <strong>Проверяем качество</strong>
                    <small>Факт-чек, стилистика, дедупликация</small>
                </div>
                <span class="fn-step-duration"></span>
            </li>
        </ul>
    </article>
</section>

{# ===== NARRATIVE MESSAGE ===== #}
<section>
    <article id="narrative-area" class="fn-narrative" hidden>
        <p id="narrative-message"></p>
    </article>
</section>

{# ===== ERROR DISPLAY (hidden by default) ===== #}
<section id="error-section" hidden>
    <article class="fn-error-card">
        <header>
            <h3>Произошла ошибка</h3>
        </header>
        <p id="error-message"></p>
        <footer>
            <a href="/" role="button">Попробовать снова</a>
        </footer>
    </article>
</section>

{% endblock %}

{% block extra_js %}
{# Pass prediction_id to JavaScript via data attribute #}
<script
    id="progress-config"
    type="application/json"
>{"predictionId": "{{ prediction_id }}", "outlet": "{{ outlet }}"}</script>
<script src="{{ url_for('static', path='js/progress.js') }}"></script>
{% endblock %}
```

---

## 6. Страница: Результаты (`results.html`)

Главная ценность продукта -- карточки прогнозов с обоснованиями.

```html
{# src/web/templates/results.html -- Prediction results with headline cards. #}
{% extends "base.html" %}

{% block title %}Прогноз: {{ prediction.outlet }} -- Foresighting News{% endblock %}

{% block content %}

{# ===== HEADER ===== #}
<section>
    <hgroup>
        <h1>Прогноз для {{ prediction.outlet }}</h1>
        <p>
            Дата прогноза: <strong>{{ prediction.target_date.strftime('%d.%m.%Y') }}</strong>
            &middot;
            Выполнен за {{ (prediction.duration_ms / 1000) | round(0) | int }} сек.
            {% if prediction.total_cost_usd > 0 %}
                &middot;
                Стоимость: ${{ prediction.total_cost_usd | round(2) }}
            {% endif %}
        </p>
    </hgroup>
</section>

{# ===== HEADLINE CARDS ===== #}
<section>
    {% for headline in prediction.headlines %}
        {% include "partials/headline_card.html" %}
    {% endfor %}
</section>

{# ===== ACTIONS ===== #}
<section style="text-align: center;">
    <a href="/" role="button">Новый прогноз</a>
</section>

{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', path='js/results.js') }}"></script>
{% endblock %}
```

---

## 7. Partial: Карточка заголовка (`partials/headline_card.html`)

Переиспользуемый компонент. Ожидает переменную `headline` (объект `HeadlineOutput`) в контексте Jinja2.

```html
{# src/web/templates/partials/headline_card.html
   Expects: headline (HeadlineOutput), loop.index (from {% for %}) #}

<article class="fn-headline-card">
    <header>
        <div class="fn-headline-header">
            <span class="fn-rank">#{{ loop.index }}</span>

            {# Confidence badge -- color-coded #}
            {% set conf = headline.confidence %}
            {% if conf >= 0.8 %}
                {% set badge_class = "fn-badge--very-high" %}
                {% set badge_label = "Очень высокая" %}
            {% elif conf >= 0.6 %}
                {% set badge_class = "fn-badge--high" %}
                {% set badge_label = "Высокая" %}
            {% elif conf >= 0.4 %}
                {% set badge_class = "fn-badge--moderate" %}
                {% set badge_label = "Средняя" %}
            {% elif conf >= 0.2 %}
                {% set badge_class = "fn-badge--low" %}
                {% set badge_label = "Низкая" %}
            {% else %}
                {% set badge_class = "fn-badge--speculative" %}
                {% set badge_label = "Спекулятивно" %}
            {% endif %}

            <span class="fn-badge {{ badge_class }}">
                {{ (conf * 100) | round(0) | int }}% -- {{ badge_label }}
            </span>

            {# Category tag #}
            <span class="fn-category">{{ headline.category }}</span>
        </div>
    </header>

    {# Headline text -- the main attraction #}
    <h3 class="fn-headline-text">{{ headline.headline }}</h3>

    {# First paragraph preview #}
    <p class="fn-first-paragraph">{{ headline.first_paragraph }}</p>

    {# Brief reasoning summary #}
    <p class="fn-reasoning-summary">
        <small><em>{{ headline.reasoning }}</em></small>
    </p>

    {# Expandable detailed reasoning #}
    {% include "partials/reasoning_block.html" %}

</article>
```

---

## 8. Partial: Блок обоснований (`partials/reasoning_block.html`)

Раскрывающийся блок с деталями: цепочка доказательств, согласие экспертов, особые мнения.

```html
{# src/web/templates/partials/reasoning_block.html
   Expects: headline (HeadlineOutput) #}

<details class="fn-reasoning-block">
    <summary>Обоснование</summary>

    <div class="fn-reasoning-content">

        {# === Evidence chain === #}
        {% if headline.evidence_chain %}
        <div class="fn-evidence">
            <h4>Цепочка доказательств</h4>
            <ul>
                {% for evidence in headline.evidence_chain %}
                <li>
                    <strong>{{ evidence.source }}:</strong>
                    {{ evidence.summary }}
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        {# === Agent agreement === #}
        <div class="fn-agreement">
            <h4>Согласие экспертов</h4>
            {% if headline.agent_agreement == "consensus" %}
                <p class="fn-agreement-indicator fn-agreement--consensus">
                    5 из 5 экспертов согласны
                </p>
            {% elif headline.agent_agreement == "majority" %}
                <p class="fn-agreement-indicator fn-agreement--majority">
                    4 из 5 экспертов согласны
                </p>
            {% elif headline.agent_agreement == "split" %}
                <p class="fn-agreement-indicator fn-agreement--split">
                    Мнения разделились (3 против 2)
                </p>
            {% endif %}
        </div>

        {# === Dissenting views === #}
        {% if headline.dissenting_views %}
        <div class="fn-dissent">
            <h4>Особые мнения</h4>
            {% for dv in headline.dissenting_views %}
            <blockquote class="fn-dissent-item">
                <p>{{ dv.view }}</p>
                <footer>
                    <cite>-- {{ dv.agent }}</cite>
                </footer>
            </blockquote>
            {% endfor %}
        </div>
        {% endif %}

    </div>
</details>
```

---

## 9. Страница: О методологии (`about.html`)

```html
{# src/web/templates/about.html -- Methodology explanation. #}
{% extends "base.html" %}

{% block title %}О методологии -- Foresighting News{% endblock %}

{% block content %}

<section>
    <hgroup>
        <h1>О методологии</h1>
        <p>Как работает прогнозирование заголовков</p>
    </hgroup>
</section>

{# ===== DELPHI METHOD ===== #}
<section>
    <h2>Метод Дельфи</h2>
    <p>
        В основе Foresighting News лежит
        <strong>метод Дельфи</strong> -- проверенная методика
        группового прогнозирования, разработанная корпорацией RAND
        в 1960-х годах.
    </p>
    <p>
        Суть метода: несколько экспертов <em>независимо</em> оценивают
        ситуацию, затем знакомятся с аргументами друг друга
        (не зная авторства) и пересматривают свои оценки.
        Анонимность устраняет давление авторитета.
        Итерация позволяет скорректировать ошибки.
        Статистическая агрегация даёт более точный результат,
        чем мнение любого отдельного эксперта.
    </p>
    <p>
        В нашей системе роль экспертов выполняют пять ИИ-агентов,
        каждый с уникальной аналитической рамкой и работающий
        на отдельной языковой модели. Это обеспечивает разнообразие
        перспектив и минимизирует систематические ошибки.
    </p>
</section>

{# ===== EXPERT PERSONAS ===== #}
<section>
    <h2>Пять экспертов</h2>

    <div class="grid">
        <article>
            <header>
                <div class="fn-persona-icon" aria-hidden="true">&#128202;</div>
                <h3>Реалист-аналитик</h3>
            </header>
            <p>
                Опытный аналитик политических рисков. Мыслит категориями
                базовых ставок и исторических аналогий. Начинает с вопроса:
                &laquo;Как часто подобное происходило раньше?&raquo;
            </p>
            <footer><small>Модель: Claude Sonnet</small></footer>
        </article>

        <article>
            <header>
                <div class="fn-persona-icon" aria-hidden="true">&#127758;</div>
                <h3>Геополитический стратег</h3>
            </header>
            <p>
                Специалист по международным отношениям. Видит мир через
                призму силовых балансов и стратегических интересов.
                Ключевой вопрос: &laquo;Cui bono?&raquo;
            </p>
            <footer><small>Модель: GPT-4o</small></footer>
        </article>
    </div>

    <div class="grid">
        <article>
            <header>
                <div class="fn-persona-icon" aria-hidden="true">&#128176;</div>
                <h3>Экономический аналитик</h3>
            </header>
            <p>
                Макроэкономист и рыночный аналитик. Следит за деньгами:
                потоки капитала, фискальная политика, санкции. Принцип:
                &laquo;Следуй за деньгами&raquo;.
            </p>
            <footer><small>Модель: Gemini Pro</small></footer>
        </article>

        <article>
            <header>
                <div class="fn-persona-icon" aria-hidden="true">&#128240;</div>
                <h3>Медиа-эксперт</h3>
            </header>
            <p>
                Бывший редактор крупного агентства. Думает категориями
                &laquo;что попадёт в выпуск&raquo;: новостная ценность,
                редакционная логика, медиа-насыщенность.
            </p>
            <footer><small>Модель: YandexGPT</small></footer>
        </article>
    </div>

    <div class="grid">
        <article>
            <header>
                <div class="fn-persona-icon" aria-hidden="true">&#128520;</div>
                <h3>Адвокат дьявола</h3>
            </header>
            <p>
                Систематический контрариан. Его задача -- найти то,
                что остальные пропустили. Применяет технику pre-mortem:
                &laquo;Допустим, прогноз провалился -- что пошло не так?&raquo;
            </p>
            <footer><small>Модель: DeepSeek R1</small></footer>
        </article>
        <div>{# Empty grid cell for alignment #}</div>
    </div>
</section>

{# ===== CONFIDENCE SCORING ===== #}
<section>
    <h2>Уровни уверенности</h2>
    <p>
        Каждый прогноз получает числовую оценку уверенности
        от 0% до 100%, которая затем переводится в качественную шкалу:
    </p>
    <table>
        <thead>
            <tr>
                <th scope="col">Диапазон</th>
                <th scope="col">Уровень</th>
                <th scope="col">Что это значит</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="fn-badge fn-badge--very-high">80--100%</span></td>
                <td>Очень высокая</td>
                <td>Событие почти наверняка произойдёт и будет освещено. Основано на подтверждённых фактах.</td>
            </tr>
            <tr>
                <td><span class="fn-badge fn-badge--high">60--79%</span></td>
                <td>Высокая</td>
                <td>Высоковероятное развитие событий. Большинство экспертов согласны.</td>
            </tr>
            <tr>
                <td><span class="fn-badge fn-badge--moderate">40--59%</span></td>
                <td>Средняя</td>
                <td>Один из нескольких возможных сценариев. Есть аргументы &laquo;за&raquo; и &laquo;против&raquo;.</td>
            </tr>
            <tr>
                <td><span class="fn-badge fn-badge--low">20--39%</span></td>
                <td>Низкая</td>
                <td>Маловероятный, но заслуживающий внимания сценарий. Может реализоваться при определённых условиях.</td>
            </tr>
            <tr>
                <td><span class="fn-badge fn-badge--speculative">0--19%</span></td>
                <td>Спекулятивно</td>
                <td>&laquo;Чёрный лебедь&raquo;. Событие было бы неожиданным, но именно такие прогнозы самые ценные, если сбываются.</td>
            </tr>
        </tbody>
    </table>
</section>

{# ===== PIPELINE STAGES ===== #}
<section>
    <h2>Стадии прогнозирования</h2>
    <p>Полный цикл прогнозирования состоит из 9 стадий:</p>
    <ol>
        <li>
            <strong>Сбор данных</strong> -- загрузка новостей из RSS-фидов, поисковых систем,
            архивов целевого издания. Параллельно работают три агента-сборщика.
        </li>
        <li>
            <strong>Идентификация событий</strong> -- кластеризация новостных сигналов
            в события, определение ключевых трендов.
        </li>
        <li>
            <strong>Анализ траекторий</strong> -- для каждого события строятся
            сценарии развития и матрица перекрёстных влияний.
        </li>
        <li>
            <strong>Дельфи: раунд 1</strong> -- пять ИИ-экспертов независимо
            оценивают, что произойдёт и как это будет освещено.
        </li>
        <li>
            <strong>Дельфи: раунд 2</strong> -- медиатор выявляет расхождения,
            эксперты пересматривают оценки с учётом аргументов коллег.
        </li>
        <li>
            <strong>Консенсус</strong> -- агрегация оценок, калибровка
            вероятностей, ранжирование прогнозов.
        </li>
        <li>
            <strong>Анализ фрейминга</strong> -- как именно целевое издание
            подаст каждое событие (угол, тон, акценты).
        </li>
        <li>
            <strong>Генерация заголовков</strong> -- создание заголовков
            и первых абзацев в стиле целевого издания.
        </li>
        <li>
            <strong>Контроль качества</strong> -- фактическая проверка,
            стилистический анализ, дедупликация.
        </li>
    </ol>
    <p>
        Общее время: 15--30 минут. Стоимость LLM-вызовов: ~$30 за прогноз.
    </p>
</section>

{# ===== TECH DETAILS ===== #}
<section>
    <h2>Технические детали</h2>
    <p>
        Для тех, кому интересна архитектура: система представляет собой
        модульный монолит на Python с асинхронным пайплайном.
    </p>
    <ul>
        <li>Backend: FastAPI + ARQ (async task queue)</li>
        <li>LLM: OpenRouter (Claude, GPT-4o, Gemini, DeepSeek) + YandexGPT</li>
        <li>Разнообразие моделей: каждый эксперт использует модель от другого провайдера</li>
        <li>Прогресс: Server-Sent Events (SSE) через Redis pub/sub</li>
        <li>БД: SQLite + SQLAlchemy 2.0</li>
    </ul>
    <p>
        Исходный код:
        <a href="https://github.com/your-repo/foresighting-news"
           target="_blank"
           rel="noopener noreferrer">
            GitHub
        </a>
    </p>
</section>

{% endblock %}
```

---

## 10. JavaScript: `form.js`

Autocomplete для поля "СМИ" и submit-логика формы.

```javascript
/**
 * src/web/static/js/form.js
 *
 * Handles the prediction form on the landing page:
 * - Debounced autocomplete for the outlet field (GET /api/v1/outlets?q=...)
 * - Form submission via fetch (POST /api/v1/predictions)
 * - Redirect to progress page on success
 */

(function () {
  "use strict";

  // --- DOM references ---
  var form = document.getElementById("prediction-form");
  var outletInput = document.getElementById("outlet");
  var suggestionsList = document.getElementById("outlet-suggestions");
  var dateInput = document.getElementById("target_date");
  var submitBtn = document.getElementById("submit-btn");
  var errorDiv = document.getElementById("form-error");

  if (!form || !outletInput) return;

  // --- Autocomplete state ---
  var debounceTimer = null;
  var DEBOUNCE_MS = 300;
  var MIN_QUERY_LENGTH = 2;
  var selectedIndex = -1;

  // --- Autocomplete: fetch suggestions ---

  /**
   * Fetch outlet suggestions from the API.
   * @param {string} query - Search string (min 2 chars).
   */
  async function fetchSuggestions(query) {
    if (query.length < MIN_QUERY_LENGTH) {
      hideSuggestions();
      return;
    }

    try {
      var resp = await fetch(
        "/api/v1/outlets?" + new URLSearchParams({ q: query })
      );
      if (!resp.ok) return;

      var data = await resp.json();
      renderSuggestions(data.outlets || []);
    } catch (err) {
      // Network error -- silently ignore, user can type manually
    }
  }

  /**
   * Render suggestion items into the dropdown.
   * @param {Array<{name: string, language: string}>} outlets
   */
  function renderSuggestions(outlets) {
    // Clear previous suggestions safely
    while (suggestionsList.firstChild) {
      suggestionsList.removeChild(suggestionsList.firstChild);
    }
    selectedIndex = -1;

    if (outlets.length === 0) {
      hideSuggestions();
      return;
    }

    outlets.forEach(function (outlet, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("data-index", String(i));
      li.textContent = outlet.name;
      if (outlet.language) {
        var lang = document.createElement("small");
        lang.textContent = " (" + outlet.language + ")";
        li.appendChild(lang);
      }
      li.addEventListener("mousedown", function (e) {
        e.preventDefault(); // Prevent blur before click registers
        selectSuggestion(outlet.name);
      });
      suggestionsList.appendChild(li);
    });

    suggestionsList.hidden = false;
  }

  function hideSuggestions() {
    suggestionsList.hidden = true;
    while (suggestionsList.firstChild) {
      suggestionsList.removeChild(suggestionsList.firstChild);
    }
    selectedIndex = -1;
  }

  /**
   * Set the outlet input to the selected value and close dropdown.
   * @param {string} name
   */
  function selectSuggestion(name) {
    outletInput.value = name;
    hideSuggestions();
  }

  // --- Autocomplete: event listeners ---

  outletInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      fetchSuggestions(outletInput.value.trim());
    }, DEBOUNCE_MS);
  });

  outletInput.addEventListener("blur", function () {
    // Small delay to allow click on suggestion to register
    setTimeout(hideSuggestions, 150);
  });

  outletInput.addEventListener("focus", function () {
    if (outletInput.value.trim().length >= MIN_QUERY_LENGTH) {
      fetchSuggestions(outletInput.value.trim());
    }
  });

  // Keyboard navigation in dropdown
  outletInput.addEventListener("keydown", function (e) {
    var items = suggestionsList.querySelectorAll("li");
    if (!items.length || suggestionsList.hidden) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
      highlightItem(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
      highlightItem(items);
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      selectSuggestion(items[selectedIndex].textContent.split(" (")[0]);
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  });

  /**
   * Highlight the active item in the suggestions list.
   * @param {NodeList} items
   */
  function highlightItem(items) {
    items.forEach(function (item, i) {
      item.classList.toggle("fn-autocomplete-active", i === selectedIndex);
    });
  }

  // --- Date validation ---

  dateInput.addEventListener("change", function () {
    // Browser-native min/max validation handles most cases.
    // This adds a visual confirmation that the date is valid.
    var val = dateInput.value;
    if (!val) return;

    var selected = new Date(val);
    var today = new Date();
    today.setHours(0, 0, 0, 0);

    if (selected <= today) {
      dateInput.setCustomValidity("Выберите дату в будущем");
    } else {
      dateInput.setCustomValidity("");
    }
  });

  // --- Form submission ---

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    showError(""); // Clear previous errors

    var outlet = outletInput.value.trim();
    var targetDate = dateInput.value;

    if (!outlet) {
      showError("Укажите название СМИ");
      outletInput.focus();
      return;
    }

    if (!targetDate) {
      showError("Укажите дату прогноза");
      dateInput.focus();
      return;
    }

    // Disable form while submitting
    submitBtn.setAttribute("aria-busy", "true");
    submitBtn.disabled = true;

    try {
      var resp = await fetch("/api/v1/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          outlet: outlet,
          target_date: targetDate,
        }),
      });

      if (!resp.ok) {
        var errData = await resp.json().catch(function () {
          return { detail: "Ошибка сервера" };
        });
        showError(errData.detail || "Не удалось создать прогноз");
        return;
      }

      var data = await resp.json();

      // Redirect to the progress page
      window.location.href = "/predict/" + data.id;
    } catch (err) {
      showError("Ошибка сети. Проверьте подключение к интернету.");
    } finally {
      submitBtn.removeAttribute("aria-busy");
      submitBtn.disabled = false;
    }
  });

  /**
   * Display or hide the error message.
   * @param {string} msg - Error text (empty to hide).
   */
  function showError(msg) {
    if (!msg) {
      errorDiv.hidden = true;
      errorDiv.textContent = "";
      return;
    }
    errorDiv.textContent = msg;
    errorDiv.hidden = false;
  }
})();
```

---

## 11. JavaScript: `progress.js`

SSE-клиент для страницы прогресса.

```javascript
/**
 * src/web/static/js/progress.js
 *
 * Connects to the SSE endpoint for a prediction and updates the UI:
 * - Progress bar percentage
 * - Step list icons and states (pending / active / done)
 * - Narrative message area
 * - Auto-redirect to results on completion
 * - Error display on failure
 *
 * SSE endpoint: GET /api/v1/predictions/{id}/stream
 * Event format: { stage, message, progress, detail, elapsed_ms, cost_usd }
 */

(function () {
  "use strict";

  // --- Read config from embedded JSON ---
  var configEl = document.getElementById("progress-config");
  if (!configEl) return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (err) {
    return;
  }

  var predictionId = config.predictionId;
  if (!predictionId) return;

  // --- DOM references ---
  var progressBar = document.getElementById("progress-bar");
  var progressPercent = document.getElementById("progress-percent");
  var progressElapsed = document.getElementById("progress-elapsed");
  var stepList = document.getElementById("step-list");
  var narrativeArea = document.getElementById("narrative-area");
  var narrativeMessage = document.getElementById("narrative-message");
  var errorSection = document.getElementById("error-section");
  var errorMessage = document.getElementById("error-message");

  // --- Ordered stage list (matches the <li> data-stage attributes) ---
  var STAGES = [
    "collection",
    "event_identification",
    "trajectory",
    "delphi_r1",
    "delphi_r2",
    "consensus",
    "framing",
    "generation",
    "quality_gate",
  ];

  // Unicode constants for step icons (avoids inline HTML injection)
  var ICON_PENDING = "\u25CB";   // ○
  var ICON_ACTIVE = "\u25CF";    // ●
  var ICON_DONE = "\u2713";      // ✓

  // Track which stage was last active, so we can mark it as "done"
  // when a new stage begins.
  var lastActiveStage = null;
  var stageStartTimes = {};

  // --- Connect to SSE ---
  var sseUrl = "/api/v1/predictions/" + predictionId + "/stream";
  var source = new EventSource(sseUrl);

  source.addEventListener("progress", function (e) {
    var data;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      return;
    }

    handleProgressEvent(data);
  });

  // Handle generic message events (fallback if server sends unnamed events)
  source.onmessage = function (e) {
    var data;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      return;
    }

    handleProgressEvent(data);
  };

  source.onerror = function () {
    // EventSource auto-reconnects on transient errors.
    // If the server has closed the connection permanently,
    // check if we're already done.
    if (source.readyState === EventSource.CLOSED) {
      // Poll the prediction status once to decide what to show
      pollStatus();
    }
  };

  /**
   * Process a single SSE progress event.
   * @param {Object} data - Parsed SSE event payload.
   */
  function handleProgressEvent(data) {
    var stage = data.stage;
    var message = data.message || "";
    var progress = data.progress || 0;
    var elapsedMs = data.elapsed_ms || 0;

    // --- Update progress bar ---
    var pct = Math.round(progress * 100);
    progressBar.value = pct;
    progressPercent.textContent = pct + "%";

    // --- Update elapsed time ---
    if (elapsedMs > 0) {
      progressElapsed.textContent = formatDuration(elapsedMs);
    }

    // --- Handle terminal states ---
    if (stage === "completed") {
      markAllDone();
      source.close();
      // Small delay so user sees 100% before redirect
      setTimeout(function () {
        window.location.href = "/results/" + predictionId;
      }, 1500);
      return;
    }

    if (stage === "failed") {
      source.close();
      showError(message || "Произошла ошибка при выполнении прогноза");
      return;
    }

    // --- Update step list ---
    updateSteps(stage, elapsedMs);

    // --- Update narrative ---
    if (message && data.detail) {
      showNarrative(data.detail);
    } else if (message) {
      showNarrative(message);
    }
  }

  /**
   * Update step list: mark previous as done, current as active.
   * @param {string} currentStage - The stage identifier.
   * @param {number} elapsedMs - Total elapsed time.
   */
  function updateSteps(currentStage, elapsedMs) {
    var stageIndex = STAGES.indexOf(currentStage);
    if (stageIndex === -1) return; // Unknown stage (queued, etc.)

    // Record start time for the current stage
    if (!stageStartTimes[currentStage]) {
      stageStartTimes[currentStage] = elapsedMs;
    }

    // If we moved to a new stage, mark the previous one as done
    if (lastActiveStage && lastActiveStage !== currentStage) {
      var prevLi = stepList.querySelector(
        '[data-stage="' + lastActiveStage + '"]'
      );
      if (prevLi) {
        markStepDone(prevLi, lastActiveStage, elapsedMs);
      }
    }

    // Mark all stages before the current one as done
    for (var i = 0; i < stageIndex; i++) {
      var li = stepList.querySelector('[data-stage="' + STAGES[i] + '"]');
      if (li && !li.classList.contains("fn-step--done")) {
        markStepDone(li, STAGES[i], elapsedMs);
      }
    }

    // Mark current stage as active
    var currentLi = stepList.querySelector(
      '[data-stage="' + currentStage + '"]'
    );
    if (currentLi && !currentLi.classList.contains("fn-step--done")) {
      currentLi.className = "fn-step fn-step--active";
      currentLi.querySelector(".fn-step-icon").textContent = ICON_ACTIVE;
    }

    lastActiveStage = currentStage;
  }

  /**
   * Mark a step <li> as done.
   * @param {HTMLElement} li
   * @param {string} stageName
   * @param {number} currentElapsedMs
   */
  function markStepDone(li, stageName, currentElapsedMs) {
    li.className = "fn-step fn-step--done";
    li.querySelector(".fn-step-icon").textContent = ICON_DONE;

    // Calculate and display duration for this stage
    var startMs = stageStartTimes[stageName];
    if (startMs !== undefined) {
      var durationMs = currentElapsedMs - startMs;
      var durationEl = li.querySelector(".fn-step-duration");
      if (durationEl && durationMs > 0) {
        durationEl.textContent = formatDuration(durationMs);
      }
    }
  }

  /**
   * Mark all steps as done (called on "completed").
   */
  function markAllDone() {
    progressBar.value = 100;
    progressPercent.textContent = "100%";

    var items = stepList.querySelectorAll(".fn-step");
    items.forEach(function (li) {
      li.className = "fn-step fn-step--done";
      li.querySelector(".fn-step-icon").textContent = ICON_DONE;
    });
  }

  /**
   * Show the narrative message area.
   * @param {string} text
   */
  function showNarrative(text) {
    narrativeMessage.textContent = text;
    narrativeArea.hidden = false;
  }

  /**
   * Show the error section.
   * @param {string} text
   */
  function showError(text) {
    errorMessage.textContent = text;
    errorSection.hidden = false;

    // Hide the progress elements
    progressBar.hidden = true;
    document.querySelector(".fn-progress-meta").hidden = true;
  }

  /**
   * Format milliseconds into human-readable Russian duration.
   * @param {number} ms
   * @returns {string}
   */
  function formatDuration(ms) {
    var totalSec = Math.round(ms / 1000);
    if (totalSec < 60) {
      return totalSec + " сек.";
    }
    var min = Math.floor(totalSec / 60);
    var sec = totalSec % 60;
    return min + " мин. " + sec + " сек.";
  }

  /**
   * Fallback: poll prediction status via REST if SSE drops.
   */
  function pollStatus() {
    fetch("/api/v1/predictions/" + predictionId)
      .then(function (resp) {
        if (!resp.ok) throw new Error("Poll failed");
        return resp.json();
      })
      .then(function (data) {
        if (data.status === "completed") {
          window.location.href = "/results/" + predictionId;
        } else if (data.status === "failed") {
          showError(data.error || "Прогноз завершился с ошибкой");
        } else {
          // Still in progress -- try reconnecting SSE after a delay
          setTimeout(function () {
            window.location.reload();
          }, 5000);
        }
      })
      .catch(function () {
        showError("Потеряно соединение с сервером. Обновите страницу.");
      });
  }
})();
```

---

## 12. JavaScript: `results.js`

Минимальный скрипт для страницы результатов.

```javascript
/**
 * src/web/static/js/results.js
 *
 * Handles interactive elements on the results page:
 * - <details> accordion: optionally close others when one opens (UX polish)
 * - No other interactivity needed -- Pico.css + semantic HTML does the rest
 */

(function () {
  "use strict";

  // --- Optional: close other <details> when one opens ---
  // This creates an accordion effect for reasoning blocks.
  // Remove this if you want multiple blocks open simultaneously.

  var detailsElements = document.querySelectorAll(".fn-reasoning-block");

  detailsElements.forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;

      // Close all other open details in the same page
      detailsElements.forEach(function (other) {
        if (other !== details && other.open) {
          other.open = false;
        }
      });
    });
  });
})();
```

---

## 13. Custom CSS (`custom.css`)

Стили, специфичные для проекта. Pico.css обрабатывает всё остальное.

```css
/**
 * src/web/static/css/custom.css
 *
 * Project-specific styles for Foresighting News.
 * Pico.css handles base typography, forms, buttons, and layout.
 * This file only styles custom components:
 *   - Confidence badges
 *   - Progress step indicators
 *   - Headline cards
 *   - Autocomplete dropdown
 *   - Animations
 *   - Mobile adjustments
 */

/* ===================================================================
   CSS CUSTOM PROPERTIES
   =================================================================== */

:root {
  /* Primary (override Pico) */
  --pico-primary: #2563eb;
  --pico-primary-hover: #1d4ed8;
  --pico-primary-focus: rgba(37, 99, 235, 0.25);

  /* Confidence colors */
  --fn-confidence-very-high: #16a34a;
  --fn-confidence-high: #2563eb;
  --fn-confidence-moderate: #d97706;
  --fn-confidence-low: #ea580c;
  --fn-confidence-speculative: #dc2626;

  /* Card */
  --fn-card-bg: #f8fafc;
  --fn-card-border: #e2e8f0;

  /* Steps */
  --fn-step-done: #16a34a;
  --fn-step-active: #2563eb;
  --fn-step-pending: #94a3b8;
}


/* ===================================================================
   LOGO
   =================================================================== */

.fn-logo {
  text-decoration: none;
}


/* ===================================================================
   HERO SECTION
   =================================================================== */

.fn-hero {
  text-align: center;
  padding: 2rem 0 1rem;
}

.fn-hero h1 {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
}

.fn-hero p {
  max-width: 600px;
  margin: 0 auto;
  color: var(--pico-muted-color);
}

@media (max-width: 768px) {
  .fn-hero h1 {
    font-size: 1.75rem;
  }
}


/* ===================================================================
   BADGES (confidence, status)
   =================================================================== */

.fn-badge {
  display: inline-block;
  padding: 0.2em 0.6em;
  border-radius: 1em;
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  color: #fff;
  background-color: var(--pico-muted-color);
}

.fn-badge--very-high {
  background-color: var(--fn-confidence-very-high);
}

.fn-badge--high {
  background-color: var(--fn-confidence-high);
}

.fn-badge--moderate {
  background-color: var(--fn-confidence-moderate);
}

.fn-badge--low {
  background-color: var(--fn-confidence-low);
}

.fn-badge--speculative {
  background-color: var(--fn-confidence-speculative);
}

/* Status badges (for the recent predictions table) */
.fn-badge--success {
  background-color: var(--fn-confidence-very-high);
}

.fn-badge--info {
  background-color: var(--fn-confidence-high);
}

.fn-badge--danger {
  background-color: var(--fn-confidence-speculative);
}


/* ===================================================================
   HEADLINE CARDS
   =================================================================== */

.fn-headline-card {
  background: var(--fn-card-bg);
  border: 1px solid var(--fn-card-border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.fn-headline-card header {
  padding: 0;
  border: none;
  margin-bottom: 0.75rem;
}

.fn-headline-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.fn-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: var(--pico-primary);
  color: #fff;
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.fn-category {
  font-size: 0.8rem;
  color: var(--pico-muted-color);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.fn-headline-text {
  font-size: 1.25rem;
  line-height: 1.4;
  margin: 0.5rem 0;
}

.fn-first-paragraph {
  color: var(--pico-muted-color);
  font-size: 0.95rem;
  line-height: 1.6;
}

.fn-reasoning-summary {
  margin-top: 0.5rem;
}


/* ===================================================================
   REASONING BLOCK (expandable <details>)
   =================================================================== */

.fn-reasoning-block {
  margin-top: 1rem;
  border-top: 1px solid var(--fn-card-border);
  padding-top: 0.75rem;
}

.fn-reasoning-block summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--pico-primary);
  font-size: 0.9rem;
}

.fn-reasoning-block summary:hover {
  text-decoration: underline;
}

.fn-reasoning-content {
  padding: 0.75rem 0 0;
}

.fn-reasoning-content h4 {
  font-size: 0.9rem;
  margin: 1rem 0 0.5rem;
  color: var(--pico-muted-color);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.fn-reasoning-content h4:first-child {
  margin-top: 0;
}

.fn-evidence ul {
  list-style: disc;
  padding-left: 1.5rem;
}

.fn-evidence li {
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  line-height: 1.5;
}

/* Agent agreement indicators */
.fn-agreement-indicator {
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.3rem 0;
}

.fn-agreement--consensus {
  color: var(--fn-confidence-very-high);
}

.fn-agreement--majority {
  color: var(--fn-confidence-high);
}

.fn-agreement--split {
  color: var(--fn-confidence-moderate);
}

/* Dissenting views */
.fn-dissent-item {
  border-left: 3px solid var(--fn-confidence-low);
  padding: 0.5rem 1rem;
  margin: 0.5rem 0;
  font-size: 0.9rem;
}

.fn-dissent-item footer {
  font-size: 0.8rem;
  color: var(--pico-muted-color);
  padding: 0;
  border: none;
}


/* ===================================================================
   PROGRESS PAGE: STEP LIST
   =================================================================== */

.fn-step-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.fn-step {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--fn-card-border);
}

.fn-step:last-child {
  border-bottom: none;
}

.fn-step-icon {
  flex-shrink: 0;
  font-size: 1.2rem;
  width: 1.5rem;
  text-align: center;
  line-height: 1.5;
}

.fn-step-content {
  flex: 1;
}

.fn-step-content strong {
  display: block;
  font-size: 1rem;
}

.fn-step-content small {
  color: var(--pico-muted-color);
}

.fn-step-duration {
  flex-shrink: 0;
  font-size: 0.85rem;
  color: var(--pico-muted-color);
  white-space: nowrap;
  align-self: center;
}

/* Step states */
.fn-step--pending .fn-step-icon {
  color: var(--fn-step-pending);
}

.fn-step--pending .fn-step-content strong {
  color: var(--fn-step-pending);
}

.fn-step--active .fn-step-icon {
  color: var(--fn-step-active);
  animation: fn-pulse 1.5s ease-in-out infinite;
}

.fn-step--active .fn-step-content strong {
  color: var(--fn-step-active);
}

.fn-step--done .fn-step-icon {
  color: var(--fn-step-done);
}

.fn-step--done .fn-step-content strong {
  color: inherit;
}


/* ===================================================================
   PROGRESS PAGE: META & NARRATIVE
   =================================================================== */

.fn-progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.9rem;
  color: var(--pico-muted-color);
}

.fn-narrative {
  text-align: center;
  font-style: italic;
  color: var(--pico-muted-color);
}


/* ===================================================================
   PROGRESS PAGE: ERROR CARD
   =================================================================== */

.fn-error-card {
  border-left: 4px solid var(--fn-confidence-speculative);
}


/* ===================================================================
   FORM: AUTOCOMPLETE DROPDOWN
   =================================================================== */

.fn-autocomplete-wrapper {
  position: relative;
}

.fn-autocomplete-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 100;
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--pico-background-color);
  border: 1px solid var(--fn-card-border);
  border-top: none;
  border-radius: 0 0 0.25rem 0.25rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  max-height: 240px;
  overflow-y: auto;
}

.fn-autocomplete-dropdown li {
  padding: 0.6rem 0.8rem;
  cursor: pointer;
  font-size: 0.95rem;
  border-bottom: 1px solid var(--fn-card-border);
}

.fn-autocomplete-dropdown li:last-child {
  border-bottom: none;
}

.fn-autocomplete-dropdown li:hover,
.fn-autocomplete-dropdown li.fn-autocomplete-active {
  background: var(--fn-card-bg);
  color: var(--pico-primary);
}

.fn-autocomplete-dropdown li small {
  color: var(--pico-muted-color);
  margin-left: 0.25rem;
}


/* ===================================================================
   FORM: ERROR DISPLAY
   =================================================================== */

.fn-form-error {
  padding: 0.75rem 1rem;
  margin-top: 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.25rem;
  color: var(--fn-confidence-speculative);
  font-size: 0.9rem;
}


/* ===================================================================
   ABOUT PAGE: PERSONA ICONS
   =================================================================== */

.fn-persona-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}


/* ===================================================================
   ANIMATIONS
   =================================================================== */

@keyframes fn-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

/* Smooth progress bar transition */
progress {
  transition: value 0.5s ease;
}

/* WebKit progress bar coloring */
progress::-webkit-progress-bar {
  background-color: var(--fn-card-bg);
  border-radius: 0.25rem;
}

progress::-webkit-progress-value {
  background-color: var(--pico-primary);
  border-radius: 0.25rem;
  transition: width 0.5s ease;
}

/* Firefox progress bar */
progress::-moz-progress-bar {
  background-color: var(--pico-primary);
  border-radius: 0.25rem;
}


/* ===================================================================
   MOBILE ADJUSTMENTS
   =================================================================== */

@media (max-width: 576px) {
  .fn-headline-card {
    padding: 1rem;
  }

  .fn-headline-header {
    gap: 0.5rem;
  }

  .fn-headline-text {
    font-size: 1.1rem;
  }

  .fn-step {
    gap: 0.75rem;
  }

  .fn-step-content small {
    display: none; /* Hide description text on very small screens */
  }

  .fn-step-duration {
    font-size: 0.75rem;
  }

  /* Stack persona cards vertically */
  .grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .fn-progress-meta {
    flex-direction: column;
    gap: 0.25rem;
  }
}


/* ===================================================================
   UTILITY: overflow for tables on mobile
   =================================================================== */

.overflow-auto {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

---

## 14. Favicon (`img/favicon.svg`)

Минимальный SVG-favicon. Создаётся как статический файл.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="16" fill="#2563eb"/>
  <text x="50" y="68" font-family="system-ui, sans-serif" font-size="56" font-weight="700" fill="white" text-anchor="middle">FN</text>
</svg>
```

---

## 15. Маршрутизация и API-контракты для фронтенда

### 15.1 HTML-маршруты (web router)

| Маршрут | Шаблон | Данные из бэкенда |
|---|---|---|
| `GET /` | `index.html` | `recent_predictions` (last 5), `min_date`, `max_date` |
| `GET /predict/{id}` | `progress.html` или `results.html` | `prediction_id`, `outlet`, `target_date`; если completed -- redirect на results |
| `GET /results/{id}` | `results.html` | `prediction` (полный PredictionResponse) |
| `GET /about` | `about.html` | -- (статическая страница) |

### 15.2 API-эндпоинты, используемые фронтендом

| Эндпоинт | Метод | JS-файл | Назначение |
|---|---|---|---|
| `/api/v1/outlets?q=...` | GET | `form.js` | Autocomplete: поиск СМИ по имени |
| `/api/v1/predictions` | POST | `form.js` | Создание нового прогноза |
| `/api/v1/predictions/{id}` | GET | `progress.js` (fallback) | Получение статуса прогноза |
| `/api/v1/predictions/{id}/stream` | GET (SSE) | `progress.js` | Стрим прогресса в реальном времени |

### 15.3 Контракт API: autocomplete

**Request:** `GET /api/v1/outlets?q=ТАС`

**Response:**
```json
{
  "outlets": [
    {"name": "ТАСС", "language": "ru"},
    {"name": "ТАСС - Наука", "language": "ru"}
  ]
}
```

### 15.4 Контракт API: создание прогноза

**Request:** `POST /api/v1/predictions`
```json
{
  "outlet": "ТАСС",
  "target_date": "2026-04-02"
}
```

**Response (201 Created):**
```json
{
  "id": "a1b2c3d4-e5f6-...",
  "outlet": "ТАСС",
  "target_date": "2026-04-02",
  "status": "queued"
}
```

### 15.5 Контракт API: SSE stream

**Request:** `GET /api/v1/predictions/{id}/stream`

**Response:** `text/event-stream`
```
event: progress
data: {"stage": "collection", "message": "Сбор данных", "progress": 0.05, "detail": "NewsScout: загружено 50 RSS-фидов", "elapsed_ms": 15000, "cost_usd": 0.50}

event: progress
data: {"stage": "delphi_r1", "message": "Экспертный анализ (раунд 1)", "progress": 0.40, "detail": "Эксперты анализируют влияние тарифной политики...", "elapsed_ms": 180000, "cost_usd": 12.00}

event: progress
data: {"stage": "completed", "message": "Прогноз завершён", "progress": 1.0, "elapsed_ms": 900000, "cost_usd": 30.50}
```

### 15.6 Контракт API: полный результат

**Request:** `GET /api/v1/predictions/{id}`

**Response:**
```json
{
  "id": "a1b2c3d4-...",
  "outlet": "ТАСС",
  "target_date": "2026-04-02",
  "status": "completed",
  "duration_ms": 900000,
  "total_cost_usd": 30.50,
  "headlines": [
    {
      "rank": 1,
      "headline": "Год после Liberation Day: как тарифы...",
      "first_paragraph": "Ровно год назад президент Трамп...",
      "confidence": 0.82,
      "confidence_label": "высокая",
      "category": "экономика",
      "reasoning": "Годовщина + отмена SCOTUS + текущие Section 122",
      "evidence_chain": [
        {"source": "AP", "summary": "AP reported on..."},
        {"source": "CNBC", "summary": "CNBC analysis of..."}
      ],
      "agent_agreement": "consensus",
      "dissenting_views": [
        {"agent": "Адвокат дьявола", "view": "Война Ирана затмит тему тарифов"}
      ]
    }
  ],
  "error": null,
  "failed_stage": null
}
```

---

## 16. Структура файлов

```
src/web/
├── __init__.py
├── router.py                      # HTML page routes (FastAPI)
├── templates/
│   ├── base.html                  # Base layout: nav, footer, Pico.css
│   ├── index.html                 # Landing: form + recent predictions
│   ├── progress.html              # SSE progress page
│   ├── results.html               # Headline cards with reasoning
│   ├── about.html                 # Methodology explanation
│   └── partials/
│       ├── headline_card.html     # Reusable headline card
│       └── reasoning_block.html   # Expandable reasoning section
└── static/
    ├── css/
    │   └── custom.css             # Project-specific styles
    ├── js/
    │   ├── form.js                # Autocomplete + form submission
    │   ├── progress.js            # SSE client + DOM updates
    │   └── results.js             # Accordion for reasoning blocks
    └── img/
        └── favicon.svg            # SVG favicon
```

---

## 17. Реализация: checklist для разработчика

Порядок реализации файлов:

1. [ ] `src/web/__init__.py` -- пустой init
2. [ ] `src/web/static/css/custom.css` -- полный CSS (секция 13)
3. [ ] `src/web/static/img/favicon.svg` -- SVG (секция 14)
4. [ ] `src/web/templates/base.html` -- базовый layout (секция 3)
5. [ ] `src/web/templates/partials/headline_card.html` -- карточка (секция 7)
6. [ ] `src/web/templates/partials/reasoning_block.html` -- обоснование (секция 8)
7. [ ] `src/web/templates/index.html` -- главная (секция 4)
8. [ ] `src/web/templates/progress.html` -- прогресс (секция 5)
9. [ ] `src/web/templates/results.html` -- результаты (секция 6)
10. [ ] `src/web/templates/about.html` -- методология (секция 9)
11. [ ] `src/web/static/js/form.js` -- autocomplete + submit (секция 10)
12. [ ] `src/web/static/js/progress.js` -- SSE клиент (секция 11)
13. [ ] `src/web/static/js/results.js` -- accordion (секция 12)
14. [ ] `src/web/router.py` -- маршруты (секция 2)
15. [ ] Интеграция: монтирование router в `src/main.py` + static files mount

### Монтирование в main.py

```python
# In src/main.py -- mount the web router and static files

from fastapi.staticfiles import StaticFiles
from src.web.router import router as web_router

# Static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

# HTML page routes (must be after API routes to avoid conflicts)
app.include_router(web_router)
```

---

## 18. Тестирование фронтенда

### 18.1 Ручное тестирование

Каждая страница проверяется на:
- Chrome, Firefox, Safari (desktop)
- Chrome Mobile, Safari iOS (mobile)
- Screen reader (VoiceOver на macOS)
- Lighthouse audit: Performance > 90, Accessibility > 95

### 18.2 Автоматическое тестирование

```python
# tests/test_web/test_pages.py

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_index_returns_200():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "Что напишут СМИ завтра?" in resp.text


@pytest.mark.asyncio
async def test_about_returns_200():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/about")
    assert resp.status_code == 200
    assert "Метод Дельфи" in resp.text


@pytest.mark.asyncio
async def test_index_contains_form():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/")
    assert 'id="prediction-form"' in resp.text
    assert 'id="outlet"' in resp.text
    assert 'id="target_date"' in resp.text
```

---

## 19. Accessibility (a11y)

Требования WCAG 2.1 AA:

| Элемент | Реализация |
|---|---|
| Autocomplete dropdown | `role="listbox"` на `<ul>`, `role="option"` на `<li>`, `aria-describedby` на input |
| Progress bar | Нативный `<progress>` -- accessible по умолчанию |
| Step icons | `aria-hidden="true"` на иконках (текст дублируется в `<strong>`) |
| Error messages | `role="alert"` на контейнере ошибок |
| Color contrast | Все badge-цвета проверены на контраст > 4.5:1 с белым текстом |
| Keyboard navigation | Arrow keys в autocomplete, Enter для выбора, Escape для закрытия |
| Focus management | Нативные фокус-стили Pico.css (не переопределяем) |
| Lang attribute | `<html lang="ru">` на всех страницах |

---

## 20. Performance

| Метрика | Цель | Как достигается |
|---|---|---|
| First Contentful Paint | < 1.5s | Server-rendered HTML, Pico.css из CDN (кешируется), нет JS-блокировки рендера |
| Total JS size | < 15 KB | Три файла по ~3-5 KB, vanilla JS, нет зависимостей |
| Total CSS size | < 5 KB (custom) + ~10 KB (Pico) | Минимальный custom.css, Pico из CDN |
| SSE reconnection | Автоматическая | EventSource API reconnects by default |
| No layout shift | CLS = 0 | Фиксированные размеры для badges и progress bar |
