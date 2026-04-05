# LLM-инфраструктура

## Интеграция с OpenRouter

**Delphi Press** использует **OpenRouter.ai** — унифицированный OpenAI-совместимый API для доступа к 200+ LLM-моделям (Claude, GPT-4, Gemini, Llama, DeepSeek и др.) через единый эндпоинт.

### Архитектура провайдера

- **Base URL**: `https://openrouter.ai/api/v1`
- **Формат моделей**: `provider/model`, например `anthropic/claude-opus-4.6`, `google/gemini-2.5-flash`
- **Клиент**: OpenAI Python SDK v1.0+ с переопределённым `base_url`
- **Аутентификация**: API-ключ в заголовке `Authorization: Bearer sk-or-...`

## 28 LLM-задач с моделями и параметрами

В `DEFAULT_ASSIGNMENTS` зарегистрировано 28 задач. Judge имеет запись (temp=0.3, json_mode=True), но фактически использует детерминированную агрегацию без LLM-вызовов:

### Коллекторы (Стадия 1)

| Task ID | Назначение | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| news_scout_search | Формирование поисковых запросов | Gemini 3.1-flash-lite | Gemini 2.5-flash | 0.3 | Нет |
| event_calendar | Поиск запланированных событий | Gemini 3.1-flash-lite | Gemini 2.5-flash | 0.3 | Да |
| event_assessment | Оценка значимости событий | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.4 | Да |
| outlet_historian | Анализ стиля издания | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.4 | Да |

### Аналитики (Стадии 2–3)

| Task ID | Назначение | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| event_clustering | Кластеризация сигналов | Gemini 3.1-flash-lite | Gemini 2.5-flash | 0.2 | Да |
| trajectory_analysis | Сценарии развития событий | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |
| cross_impact_analysis | Матрица перекрёстных влияний | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.4 | Да |
| geopolitical_analysis | Геополитический контекст | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.5 | Да |
| economic_analysis | Экономический контекст | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.5 | Да |
| media_analysis | Медийный контекст | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.5 | Да |

### Дельфи R1 (Стадия 4)

| Task ID | Назначение | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| delphi_r1_realist | Реалист | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.7 | Да |
| delphi_r1_geostrateg | Геостратег | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.7 | Да |
| delphi_r1_economist | Экономист | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.7 | Да |
| delphi_r1_media | Медиа-эксперт | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.7 | Да |
| delphi_r1_devils | Адвокат дьявола | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.9 | Да |

### Медиатор и Дельфи R2 (Стадия 5)

| Task ID | Назначение | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| mediator | Синтез расхождений | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.5 | Да |
| delphi_r2_realist | Дельфи R2: Реалист | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |
| delphi_r2_geostrateg | Дельфи R2: Геостратег | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |
| delphi_r2_economist | Дельфи R2: Экономист | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |
| delphi_r2_media | Дельфи R2: Медиа-эксперт | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |
| delphi_r2_devils | Дельфи R2: Адвокат дьявола | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.6 | Да |

### Генераторы (Стадии 6–9)

| Task ID | Назначение | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| framing | Анализ фрейминга | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.5 | Да |
| style_generation | Генерация заголовков (мультиязык) | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.8 | Нет |
| style_generation_ru | Генерация заголовков (русский) | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.8 | Нет |
| style_generation_en | Генерация заголовков (английский) | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.8 | Нет |
| quality_factcheck | Факт-чек | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.2 | Да |
| quality_style | Стилистическая проверка | Claude Opus 4.6 | Claude Sonnet 4.5 | 0.3 | Да |

!!! note "JSON Mode"
    24 из 27 задач используют JSON mode для структурированного вывода. Это означает:

    - OpenRouter просит модель вывести JSON
    - Ответ парсится как `dict` и валидируется через Pydantic-модель
    - Если парсинг или валидация не удаётся, агент возвращает `AgentResult(success=False)`

## Разнообразие через промпты

Все 5 персон Дельфи используют **Claude Opus 4.6** — одну и ту же модель. Разнообразие ошибок обеспечивается не выбором разных LLM, а уникальными системными промптами (~400–500 строк на персону) и когнитивными смещениями.

## Retry и fallback-цепочка

### Exponential backoff с jitter

При ошибке LLM-провайдера (HTTP 429, 500, 502, 503, 504) система выполняет повторный запрос с экспоненциальной задержкой:

$$\text{delay}_n = \min\left(\text{base} \cdot 2^n, \text{max\_delay}\right) + \text{jitter}$$

где:

- base = 1 сек (базовая задержка, `llm_retry_base_delay`)
- max_delay = 30 сек (потолок, `llm_retry_max_delay`)
- jitter ∈ [0, 0.5] сек (случайный разброс для избежания thundering herd)
- n = номер попытки (0, 1, 2, ...)

Пример:

- Попытка 0: сразу выполнить
- Попытка 1: ошибка → ждём 1–1.5 сек
- Попытка 2: ошибка → ждём 2–2.5 сек
- Попытка 3 (последняя): ошибка → выбрасываем исключение

### Fallback-цепочка

При исчерпании всех retry-попыток для primary модели система переключается на fallback-модели по очереди:

$$\begin{aligned}
&\text{Primary Model}\\
&\quad \xrightarrow{\text{retry × 3}} \text{Fallback}\\
&\quad \xrightarrow{\text{all fail}} \text{raise LLMProviderError}
\end{aligned}$$

Пример для `delphi_r1_realist`:
1. Попробовать Claude Opus 4.6 (primary) × 3 retry
2. Если всё ещё ошибка → попробовать Claude Sonnet 4.5 (fallback) × 3 retry
3. Если оба отказали → выбросить исключение, агент вернёт `AgentResult(success=False)`

### HTTP 429 (Rate Limiting)

Если провайдер возвращает HTTP 429 с заголовком `Retry-After`, система уважает этот заголовок:

Если заголовок `Retry-After` присутствует, он используется напрямую. Иначе — fallback на exponential backoff:

```python
delay = retry_after or min(base_delay * (2 ** attempt), max_delay)
```

## Таймауты на стадиях

Каждая стадия пайплайна имеет индивидуальный таймаут, после которого выполнение прерывается. Таймауты учитывают сложность стадии и количество параллельных агентов:

| Стадия | Агенты | Параллель | Таймаут (сек) | Поведение |
|---|---|---|---|---|
| 1. Collection | 4 коллектора | ✓ Параллельно | 600 | `min_successful=2` — нужны минимум 2 успешных |
| 2. Event Identification | Event Trend Analyzer | Последовательно | 600 | Обязательна (required=True) |
| 3. Trajectory | 3 аналитика | ✓ Параллельно | 600 | `min_successful=2` — нужны минимум 2 успешных |
| 4. Delphi R1 | 5 персон | ✓ Параллельно | 600 | `min_successful=3` — нужны минимум 3 успешных |
| 5. Delphi R2 | Медиатор + 5 персон | Последовательно | 900 | Обязательна (required=True) или пропускается если `delphi_rounds < 2` |
| 6. Consensus | Judge | Последовательно | 300 | Обязательна (детерминированный, LLM не требуется) |
| 7. Framing | Framing Agent | Последовательно | 300 | Обязательна |
| 8. Generation | Style Replicator | Последовательно | 300 | Обязательна |
| 9. Quality Gate | Quality Gate | Последовательно | 300 | Обязательна |

!!! info "Fail-soft стратегия"
    Стадии с параметром `min_successful` используют fail-soft подход: если достаточное количество параллельных агентов завершилось успешно, стадия считается пройденной, даже если некоторые агенты упали.

### LLM timeout per call

Каждый отдельный LLM-вызов имеет таймаут **120 сек** (`llm_timeout_seconds`). Если OpenRouter не ответил за этот период, система:
1. Прерывает ожидание
2. Генерирует `LLMProviderError`
3. Переходит к следующей retry-попытке или fallback-модели

### ARQ job timeout

Полный пайплайн выполняется как ARQ job с таймаутом **5400 сек** (90 минут, `arq_job_timeout`). Если пайплайн не завершился за этот период:
1. ARQ прерывает job
2. Результат помечается как failed в БД
3. Пользователь получает сообщение об ошибке через API

## Стоимость и бюджетный контроль

### Формула стоимости вызова

Каждый LLM-вызов рассчитывает стоимость по формуле:

$$\text{cost\_usd} = \left(\frac{\text{tokens\_in}}{1{,}000{,}000} \times \text{price\_in}\right) + \left(\frac{\text{tokens\_out}}{1{,}000{,}000} \times \text{price\_out}\right)$$

где:

- `tokens_in`, `tokens_out` — переданные OpenRouter в `usage`
- `price_in`, `price_out` — цены из таблицы моделей ($/1M токенов)

Пример: Claude Opus 4.6

- Input: \$5 за 1М токенов
- Output: \$25 за 1М токенов
- Для 10k входных, 1k выходных: cost = (10k/1M × 5) + (1k/1M × 25) = 0.05 + 0.025 = \$0.075

### Цены моделей (OpenRouter)

| Модель | Input (\$/1М токенов) | Output (\$/1М токенов) | Использование |
|---|---|---|---|
| anthropic/claude-opus-4.6 | \$5.00 | \$25.00 | Основная модель (Opus, все агенты) |
| anthropic/claude-sonnet-4.5 | \$3.00 | \$15.00 | Fallback для Opus задач |
| google/gemini-3.1-flash-lite-preview | \$0.25 | \$1.50 | Primary для коллекторов (fast) |
| google/gemini-2.5-flash | \$0.30 | \$2.50 | Fallback для коллекторов |
| openai/gpt-4o-mini | \$0.15 | \$0.60 | Экономичная опция (не в use) |
| openai/gpt-4o | \$2.50 | \$10.00 | Премиум OpenAI (не в use) |
| google/gemini-2.5-pro | \$1.25 | \$10.00 | Премиум Gemini (не в use) |

### Бюджетный контроль per-prediction

**BudgetTracker** отслеживает расходы в рамках одного прогноза. Проверка бюджета выполняется ПЕРЕД каждым LLM-вызовом:

| Параметр | Значение |
|---|---|
| Лимит на прогноз (по умолчанию) | \$50 USD |
| Лимит (настраивается через `max_budget_usd`) | От \$1 до \$500 USD |
| Проверка перед вызовом | Если `estimated_cost > remaining_budget`, raise `LLMBudgetExceededError` |
| Типичный прогноз Light | ~\$1–\$2 USD |
| Типичный прогноз Full | ~\$10–\$15 USD |
| Максимальный прогноз (при большом объёме) | До \$50 USD |

Алгоритм проверки:

$$\text{remaining} = \text{budget\_usd} - \sum_{i=1}^{n} \text{cost\_usd}_i$$

$$\text{if } \text{estimated\_cost} > \text{remaining} \text{ then } \text{raise LLMBudgetExceededError}$$

Оценка стоимости рассчитывается по количеству токенов в промпте с буфером:

\[\text{est\_tokens} = \text{estimate\_messages\_tokens}(\text{messages})\]

\[\text{est\_cost} = \frac{\text{est\_tokens}}{10^6} \times \text{price\_in} + \frac{\text{est\_tokens}}{10^6} \times \text{price\_out}\]

Буфер обеспечивается тем, что `est_tokens` используется и для входных, и для выходных токенов (фактический выход обычно меньше входа).

!!! warning "Бюджет исчерпан"
    Если во время пайплайна бюджет исчерпывается:

    - LLM-вызов блокируется исключением `LLMBudgetExceededError`
    - Стадия падает с ошибкой
    - Пайплайн прерывается (если стадия required=True)
    - Результат помечается как failed, информация о расходах сохраняется в БД

### Примеры и мониторинг

**BudgetTracker** предоставляет методы для аналитики:

- `summary_by_stage()`: расходы по стадиям пайплайна
- `summary_by_model()`: расходы по моделям
- `to_records()`: все `CostRecord` для сохранения в БД

Пример логирования прогноза:

```
Стадия 1 (Collection): \$1.50
Стадия 2 (Event Identification): \$0.50
Стадия 3 (Trajectory): \$3.00
Стадия 4 (Delphi R1): \$8.00
Стадия 5 (Mediator + R2): \$10.00
Стадия 6 (Consensus): \$0 (детерминированный Judge)
Стадии 7–9 (Framing + Generation + QG): \$5.50
-----------
Итого: \$30.50 USD
```

## Обработка ошибок и исключения

### Иерархия исключений

```python
LLMProviderError                      # Базовое исключение провайдера
├── LLMRateLimitError (HTTP 429)      # Rate limit
└── [другие статусы 5xx]              # 500, 502, 503, 504

LLMBudgetExceededError                # Превышен бюджет
```

### LLMProviderError

Генерируется при ошибке OpenRouter или провайдера:

- **HTTP 429** (Rate Limit): → `LLMRateLimitError` с `retry_after` заголовком
- **HTTP 5xx** (Server Error): → `LLMProviderError` → retry с backoff
- **Timeout** (120 сек): → `LLMProviderError` → retry
- **Invalid API Key**: → `LLMProviderError` → агент возвращает `success=False`

**Поведение:**
1. Повторить с exponential backoff (3 попытки)
2. Если primary модель не ответила, попробовать fallback
3. Если все fallback отказали, выбросить исключение
4. Агент ловит исключение в `BaseAgent.run()` → возвращает `AgentResult(success=False)`

### LLMBudgetExceededError

Генерируется перед вызовом, если оценённая стоимость превысит оставшийся бюджет:

```python
class LLMBudgetExceededError(Exception):
    def __init__(self, budget_usd: float, spent_usd: float):
        # Example: "Budget exceeded: spent $32.50 of $50.00"
```

**Поведение:**
1. LLM-вызов БЛОКИРУЕТСЯ
2. Router выбрасывает исключение
3. Агент ловит в `BaseAgent.run()` → возвращает `AgentResult(success=False, error="Budget exceeded")`
4. Стадия проверяет минимум успешных (если есть)
5. Если стадия required=True, пайплайн падает

### Стратегия восстановления

| Сценарий | Действие | Результат |
|---|---|---|
| Timeout LLM-вызова | Retry с backoff × 3 | Успех или fallback |
| Fallback исчерпаны | Выбросить ошибку | Агент возвращает `success=False` |
| Стадия с `min_successful=2` и 1 агент упал | Продолжить | Стадия успешна если 2+ успешно |
| Стадия required=True упала | Прервать пайплайн | Пайплайн → failed |
| Бюджет исчерпан | Блокировать вызов | Стадия падает |

## Конфигурация LLM-слоя

Все параметры LLM настраиваются через переменные окружения (файл `.env`):

```bash
# OpenRouter API
OPENROUTER_API_KEY=sk-or-...

# Модели по умолчанию
DEFAULT_MODEL_CHEAP=google/gemini-3.1-flash-lite-preview
DEFAULT_MODEL_REASONING=anthropic/claude-opus-4.6
DEFAULT_MODEL_STRONG=anthropic/claude-opus-4.6

# Retry и таймауты
LLM_MAX_RETRIES=3                      # Количество retry-попыток per model
LLM_RETRY_BASE_DELAY=1.0               # Базовая задержка (сек)
LLM_RETRY_MAX_DELAY=30.0               # Максимальная задержка (сек)
LLM_TIMEOUT_SECONDS=120.0              # Таймаут single LLM call (сек)

# Бюджет
MAX_BUDGET_USD=50.0                    # Лимит на прогноз (USD)
BUDGET_WARNING_THRESHOLD=0.8           # Предупреждение при 80% расходе
```

### Пример с переопределением для тестирования

```bash
# Дешёвый тест (Gemini Flash)
OPENROUTER_API_KEY=sk-or-...
DEFAULT_MODEL_REASONING=google/gemini-2.5-flash
MAX_BUDGET_USD=5.0

# Production (Claude Opus)
OPENROUTER_API_KEY=sk-or-...
DEFAULT_MODEL_REASONING=anthropic/claude-opus-4.6
MAX_BUDGET_USD=50.0
```

!!! tip "Presets вместо env vars"
    Для удобства используйте presets (`light`, `full`) в API вместо переопределения env vars. Presets уже оптимизированы для стоимости и качества.
