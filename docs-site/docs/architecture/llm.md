# LLM-инфраструктура

## Интеграция с OpenRouter

**Delphi Press** использует **OpenRouter.ai** — унифицированный OpenAI-совместимый API для доступа к 200+ LLM-моделям (Claude, GPT-4, Gemini, Llama, DeepSeek и др.) через единый эндпоинт.

### Архитектура провайдера

- **Base URL**: `https://openrouter.ai/api/v1`
- **Формат моделей**: `provider/model`, например `anthropic/claude-opus-4.6`, `google/gemini-2.5-flash`
- **Клиент**: OpenAI Python SDK v1.0+ с переопределённым `base_url`
- **Аутентификация**: API-ключ в заголовке `Authorization: Bearer sk-or-...`

## 27 LLM-задач с моделями и параметрами

Все 27 LLM-задач пайплайна настроены с primary и fallback моделями (Judge — детерминированный агент, LLM не вызывается):

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
- base = 1 сек (базовая задержка)
- max_delay = 30 сек (потолок)
- jitter ∈ [0, 0.5] сек (случайный разброс для избежания thundering herd)
- n = номер попытки (0, 1, 2, ...)

Пример:
- Попытка 0: сразу выполнить
- Попытка 1: ошибка → ждём 1–1.5 сек
- Попытка 2: ошибка → ждём 2–2.5 сек
- Попытка 3: ошибка → ждём 4–4.5 сек
- Попытка 4 (последняя): ошибка → выбрасываем исключение

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

$$\text{delay} = \max(\text{Retry-After}, \text{exponential backoff})$$

## Стоимость и бюджетный контроль

### Формула стоимости вызова

Каждый LLM-вызов рассчитывает стоимость по формуле:

$$\text{cost\_usd} = \left(\frac{\text{tokens\_in}}{1{,}000{,}000} \times \text{price\_in}\right) + \left(\frac{\text{tokens\_out}}{1{,}000{,}000} \times \text{price\_out}\right)$$

где:
- `tokens_in`, `tokens_out` — переданные OpenRouter в `usage`
- `price_in`, `price_out` — цены из таблицы `MODEL_PRICING` ($/1M токенов)

Пример: Claude Opus 4.6
- Input: \$3 за 1М токенов
- Output: \$15 за 1М токенов
- Для 10k входных, 1k выходных: cost = (10k/1M × 3) + (1k/1M × 15) = 0.03 + 0.015 = \$0.045

### Бюджетный контроль

**BudgetTracker** отслеживает расходы в рамках одного прогноза и блокирует вызовы, которые превысят лимит.

| Параметр | Значение |
|---|---|
| Лимит на прогноз | \$50 USD (по умолчанию, настраивается) |
| Проверка перед вызовом | Если `estimated_cost > remaining_budget`, raise `LLMBudgetExceededError` |
| Типичный прогноз | \$1–\$15 USD |
| Максимальный прогноз | До \$50 USD (при многих событиях, долгих раундах) |

Алгоритм:

$$\text{remaining} = \text{budget\_usd} - \sum_{i=1}^{n} \text{cost\_usd}_i$$

$$\text{if } \text{estimated\_cost} > \text{remaining} \text{ then } \text{raise BudgetExceededError}$$

Оценка стоимости рассчитывается по количеству токенов в промпте:

$$\text{estimated\_tokens\_in} = \text{estimate\_messages\_tokens}(\text{messages})$$

$$\text{estimated\_cost} = \frac{\text{estimated\_tokens\_in}}{1{,}000{,}000} \times \text{price\_in} \times 1.2$$

Коэффициент 1.2 добавляет буфер на выходные токены (обычно выход меньше входа, но разница варьируется).

### Примеры и мониторинг

**BudgetTracker** предоставляет методы для аналитики:

- `summary_by_stage()`: расходы по стадиям пайплайна
- `summary_by_model()`: расходы по моделям
- `to_records()`: все `CostRecord` для сохранения в БД

Пример логирования:

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
