# 07 -- LLM-абстракция (`src/llm/`)

## Назначение

Модуль `llm` -- единая точка доступа ко всем LLM-провайдерам. Абстрагирует различия между OpenRouter (OpenAI-совместимый API) и YandexGPT, обеспечивает роутинг моделей по задачам, fallback при отказах, потоковый вывод (SSE), трекинг стоимости и бюджетный контроль.

**Потребители**: все агенты (`src/agents/`), quality gate, style replicator -- любой компонент, которому нужен LLM-вызов.

**Принцип**: агент не знает, какую модель он использует. Он запрашивает `router.complete(task="delphi_r1", persona="realist", ...)`, а роутер выбирает модель, провайдера и fallback-цепочку.

---

## Структура файлов

```
src/llm/
    __init__.py          # Реэкспорт публичного API
    providers.py         # OpenRouterClient, YandexGPTClient
    router.py            # ModelRouter -- выбор модели по задаче
    prompts/
        __init__.py
        base.py          # BasePrompt -- Jinja2 шаблонизация
        event_analysis.py
        delphi.py
        framing.py
        generation.py
        quality.py
```

---

## 1. Pydantic-схемы

### 1.1 LLMResponse

Унифицированный ответ от любого провайдера. Содержит метрики для трекинга стоимости.

```python
from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Унифицированный ответ от LLM-провайдера."""

    content: str = Field(..., description="Текст ответа модели")
    model: str = Field(..., description="Идентификатор модели: 'anthropic/claude-sonnet-4'")
    provider: str = Field(..., description="Провайдер: 'openrouter' | 'yandex'")
    tokens_in: int = Field(..., ge=0, description="Число входных токенов")
    tokens_out: int = Field(..., ge=0, description="Число выходных токенов")
    cost_usd: float = Field(..., ge=0.0, description="Стоимость вызова в USD")
    duration_ms: int = Field(..., ge=0, description="Время выполнения запроса в ms")
    finish_reason: str = Field(default="stop",
                               description="Причина завершения: 'stop', 'length', 'error'")
    raw_response: dict = Field(default_factory=dict,
                               description="Сырой ответ API (для отладки)")

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def tokens_per_second(self) -> float:
        if self.duration_ms == 0:
            return 0.0
        return self.tokens_out / (self.duration_ms / 1000)
```

### 1.2 LLMMessage

Стандартное сообщение в формате chat completion.

```python
from enum import StrEnum


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    """Одно сообщение в диалоге с LLM."""
    role: MessageRole
    content: str
```

### 1.3 LLMRequest

Параметры запроса к LLM.

```python
class LLMRequest(BaseModel):
    """Параметры запроса к LLM (передаётся провайдеру)."""

    messages: list[LLMMessage]
    model: str = Field(..., description="Идентификатор модели")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128_000)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    json_mode: bool = Field(default=False,
                            description="Запросить JSON output (response_format)")
    stop_sequences: list[str] = Field(default_factory=list)
```

### 1.4 CostRecord

Запись о стоимости одного вызова (для аккумуляции).

```python
from datetime import datetime


class CostRecord(BaseModel):
    """Запись о стоимости одного LLM-вызова."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    prediction_id: str = Field(..., description="UUID прогноза")
    stage: str = Field(..., description="Стадия пайплайна: 'delphi_r1', 'quality_gate'")
    agent: str = Field(default="", description="Имя агента: 'realist', 'judge'")
    model: str = Field(...)
    provider: str = Field(...)
    tokens_in: int = Field(default=0)
    tokens_out: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    duration_ms: int = Field(default=0)
```

### 1.5 ModelAssignment

Назначение модели для конкретной задачи.

```python
class ModelAssignment(BaseModel):
    """Привязка модели к задаче/агенту."""

    task: str = Field(..., description="Идентификатор задачи")
    primary_model: str = Field(..., description="Основная модель")
    fallback_models: list[str] = Field(default_factory=list,
                                       description="Fallback модели (по приоритету)")
    provider: str = Field(default="openrouter")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=4096)
    json_mode: bool = Field(default=False)
```

---

## 2. Провайдеры (`providers.py`)

### 2.1 Абстрактный интерфейс

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """Абстрактный LLM-провайдер."""

    @abstractmethod
    async def complete(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Синхронный (не-стриминг) вызов LLM.

        Args:
            request: Параметры запроса.

        Returns:
            LLMResponse с полными метриками.

        Raises:
            LLMProviderError: При ошибке API.
            LLMRateLimitError: При превышении rate limit.
            LLMBudgetExceededError: При превышении бюджета (не здесь, а в router).
        """
        ...

    @abstractmethod
    async def stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[str]:
        """
        Потоковый вызов LLM (для SSE).

        Yields:
            Фрагменты текста по мере генерации.

        Примечание:
            Метрики (tokens, cost) недоступны до завершения потока.
            Для их получения используется complete_from_stream().
        """
        ...

    @abstractmethod
    async def complete_from_stream(
        self,
        request: LLMRequest,
    ) -> tuple[AsyncIterator[str], "asyncio.Future[LLMResponse]"]:
        """
        Потоковый вызов с отложенным получением метрик.

        Returns:
            Tuple из:
            - AsyncIterator[str]: поток фрагментов текста
            - Future[LLMResponse]: future, который resolve-ится после
              завершения потока с полными метриками.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Идентификатор провайдера: 'openrouter', 'yandex'."""
        ...
```

### 2.2 OpenRouterClient

Основной провайдер. Обеспечивает доступ ко всем моделям через единый API (OpenAI-совместимый формат).

```python
from openai import AsyncOpenAI


class OpenRouterClient(LLMProvider):
    """
    Клиент OpenRouter.ai -- OpenAI-совместимый API для 200+ моделей.

    Особенности:
    - base_url = "https://openrouter.ai/api/v1"
    - Модели указываются как "anthropic/claude-sonnet-4", "openai/gpt-4o-mini"
    - Стоимость возвращается в response headers (x-openrouter-cost) или usage
    - Поддерживает structured output (json_mode)
    """

    def __init__(
        self,
        api_key: str,
        *,
        default_headers: dict[str, str] | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
        timeout_seconds: float = 120.0,
    ) -> None:
        """
        Args:
            api_key: OpenRouter API key (env: OPENROUTER_API_KEY).
            default_headers: Доп. заголовки (HTTP-Referer, X-Title для OpenRouter).
            max_retries: Число повторных попыток при transient errors.
            retry_base_delay: Базовая задержка для exponential backoff (секунды).
            retry_max_delay: Максимальная задержка между попытками.
            timeout_seconds: Timeout на один запрос (модели типа Opus могут думать долго).
        """
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://foresighting.news",
                "X-Title": "Foresighting News",
                **(default_headers or {}),
            },
            max_retries=0,  # Retry-логику реализуем сами
            timeout=timeout_seconds,
        )
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Non-streaming вызов.

        Реализация:
        1. Конвертировать LLMRequest -> OpenAI ChatCompletion params.
        2. Выполнить запрос с retry (exponential backoff).
        3. Извлечь usage (prompt_tokens, completion_tokens).
        4. Рассчитать стоимость по таблице MODEL_PRICING.
        5. Вернуть LLMResponse.

        Retry-логика:
        - Retry при: HTTP 429, 500, 502, 503, 504, ConnectionError, Timeout.
        - Не retry при: HTTP 400, 401, 403 (клиентская ошибка).
        - Backoff: delay = min(base * 2^attempt, max_delay) + jitter.
        """
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Streaming вызов.

        Использует client.chat.completions.create(stream=True).
        Yields текстовые чанки из response.choices[0].delta.content.

        Примечание: OpenRouter возвращает usage в последнем чанке
        (stream_options={"include_usage": true}).
        """
        ...

    async def complete_from_stream(
        self, request: LLMRequest,
    ) -> tuple[AsyncIterator[str], "asyncio.Future[LLMResponse]"]:
        """
        Streaming + метрики.

        Внутри: аккумулирует текст, при получении финального чанка
        собирает LLMResponse и resolve-ит future.
        """
        ...

    def _calculate_cost(
        self, model: str, tokens_in: int, tokens_out: int,
    ) -> float:
        """
        Рассчитать стоимость по таблице MODEL_PRICING.

        Формула: (tokens_in / 1_000_000 * price_in) +
                 (tokens_out / 1_000_000 * price_out)

        Если модель не найдена в таблице, стоимость = 0.0 (с warning в лог).
        """
        ...

    @property
    def provider_name(self) -> str:
        return "openrouter"
```

### 2.3 YandexGPTClient

Клиент для YandexGPT через официальный SDK. Используется для русскоязычных задач (стилистическая проверка, генерация на русском).

```python
from yandex_cloud_ml_sdk import AsyncYCloudML


class YandexGPTClient(LLMProvider):
    """
    Клиент YandexGPT через yandex-cloud-ml-sdk.

    Особенности:
    - Модели: 'yandexgpt', 'yandexgpt-lite', 'yandexgpt-32k'
    - Авторизация: folder_id + API key (или IAM token)
    - Формат сообщений отличается от OpenAI -- SDK абстрагирует
    - Стоимость: по тарифам Yandex Cloud (за 1000 токенов)
    - Не поддерживает json_mode напрямую -- эмулируется через промпт
    """

    def __init__(
        self,
        folder_id: str,
        api_key: str,
        *,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        """
        Args:
            folder_id: Yandex Cloud folder ID (env: YANDEX_FOLDER_ID).
            api_key: Yandex Cloud API key (env: YANDEX_API_KEY).
            max_retries: Число повторных попыток.
            retry_base_delay: Базовая задержка для backoff.
            retry_max_delay: Максимальная задержка.
            timeout_seconds: Timeout на один запрос.
        """
        self._sdk = AsyncYCloudML(folder_id=folder_id, auth=api_key)
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._timeout = timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Non-streaming вызов YandexGPT.

        Реализация:
        1. Маппинг model name:
           - 'yandexgpt' -> 'yandexgpt/latest'
           - 'yandexgpt-lite' -> 'yandexgpt-lite/latest'
           - 'yandexgpt-32k' -> 'yandexgpt/latest' (с увеличенным контекстом)
        2. Конвертировать messages в формат SDK.
        3. Вызвать model.configure(temperature=...).run(messages).
        4. Извлечь usage из ответа.
        5. Рассчитать стоимость по тарифу Yandex Cloud.

        Особенности:
        - json_mode: если request.json_mode=True, добавить в system prompt
          инструкцию "Respond ONLY with valid JSON".
        - temperature: YandexGPT поддерживает 0..1 (не 0..2 как OpenAI).
          Значения > 1 обрезаются до 1.0 с warning.
        """
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Streaming вызов YandexGPT.

        Использует model.configure(...).run_stream(messages).
        """
        ...

    async def complete_from_stream(
        self, request: LLMRequest,
    ) -> tuple[AsyncIterator[str], "asyncio.Future[LLMResponse]"]:
        """Streaming + метрики (аналогично OpenRouterClient)."""
        ...

    def _calculate_cost(
        self, model: str, tokens_in: int, tokens_out: int,
    ) -> float:
        """
        Стоимость YandexGPT по тарифам Yandex Cloud.

        Тарифы (март 2026, приблизительные):
        - yandexgpt: $0.0032 / 1K input, $0.0032 / 1K output (~0.24 руб/1K)
        - yandexgpt-lite: $0.00075 / 1K input, $0.00075 / 1K output (~0.06 руб/1K)
        """
        ...

    @property
    def provider_name(self) -> str:
        return "yandex"
```

### 2.4 Retry-логика (общая)

Вынесена в utility-функцию, используемую обоими провайдерами:

```python
import asyncio
import random


class LLMProviderError(Exception):
    """Базовая ошибка LLM-провайдера."""
    def __init__(self, message: str, *, provider: str, status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMRateLimitError(LLMProviderError):
    """Rate limit (HTTP 429)."""
    retry_after: float | None = None


class LLMBudgetExceededError(Exception):
    """Превышен бюджет на LLM-вызовы."""
    def __init__(self, budget_usd: float, spent_usd: float):
        super().__init__(
            f"Budget exceeded: spent ${spent_usd:.2f} of ${budget_usd:.2f}"
        )
        self.budget_usd = budget_usd
        self.spent_usd = spent_usd


async def retry_with_backoff(
    coro_factory,  # Callable[[], Coroutine]
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_status_codes: set[int] = frozenset({429, 500, 502, 503, 504}),
) -> Any:
    """
    Выполнить корутину с exponential backoff.

    Алгоритм:
    1. Попробовать выполнить coro.
    2. Если ошибка retryable -- подождать и повторить.
    3. Задержка: min(base * 2^attempt, max_delay) + random(0, base/2).
    4. Для HTTP 429: использовать Retry-After header если доступен.

    Args:
        coro_factory: Фабрика корутин (вызывается заново на каждую попытку).
        max_retries: Макс. число повторов.
        base_delay: Базовая задержка (секунды).
        max_delay: Потолок задержки.
        retryable_status_codes: HTTP-коды для retry.

    Raises:
        LLMProviderError: Если все попытки исчерпаны.
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except LLMRateLimitError as e:
            if attempt == max_retries:
                raise
            delay = e.retry_after or min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay + random.uniform(0, base_delay / 2))
        except LLMProviderError as e:
            if attempt == max_retries:
                raise
            if e.status_code not in retryable_status_codes:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay + random.uniform(0, base_delay / 2))
```

### 2.5 Token Counting

Для предварительной оценки числа токенов (до вызова API) используется `tiktoken`:

```python
import tiktoken


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Оценить число токенов в тексте.

    Используется tiktoken с encoding для GPT-4 (cl100k_base).
    Для YandexGPT и Claude это приблизительная оценка (+-10%).

    Args:
        text: Текст для оценки.
        model: Модель (влияет на выбор encoding).

    Returns:
        Приблизительное число токенов.
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def estimate_messages_tokens(messages: list[LLMMessage]) -> int:
    """Оценить общее число токенов во всех сообщениях."""
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.content) + 4  # overhead на role и разделители
    return total + 2  # overhead на начало/конец
```

---

## 3. Роутер (`router.py`)

### 3.1 Назначение

Центральная точка принятия решений: какую модель использовать для какой задачи, через какого провайдера, с каким fallback. Также отвечает за контроль бюджета и обеспечение model diversity для Delphi.

### 3.2 Таблица назначений моделей

Задачи пайплайна и их модели по умолчанию:

| task ID | Описание | Primary Model | Fallback | Temperature | json_mode |
|---|---|---|---|---|---|
| `news_scout_search` | Формирование поисковых запросов | `openai/gpt-4o-mini` | `yandexgpt-lite` | 0.3 | false |
| `event_calendar` | Поиск запланированных событий | `openai/gpt-4o-mini` | `yandexgpt-lite` | 0.3 | true |
| `outlet_historian` | Анализ стиля СМИ | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.4 | true |
| `event_clustering` | Кластеризация сигналов | `openai/gpt-4o-mini` | `google/gemini-2.0-flash` | 0.2 | true |
| `trajectory_analysis` | Сценарии развития событий | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.6 | true |
| `delphi_r1_realist` | Дельфи: реалист | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.7 | true |
| `delphi_r1_geostrateg` | Дельфи: геостратег | `openai/gpt-4o` | `anthropic/claude-sonnet-4` | 0.7 | true |
| `delphi_r1_economist` | Дельфи: экономист | `google/gemini-2.5-pro` | `anthropic/claude-sonnet-4` | 0.7 | true |
| `delphi_r1_media` | Дельфи: медиа-эксперт | `meta-llama/llama-4-maverick` | `openai/gpt-4o` | 0.7 | true |
| `delphi_r1_devils` | Дельфи: адвокат дьявола | `deepseek/deepseek-r1` | `anthropic/claude-sonnet-4` | 0.9 | true |
| `mediator` | Синтез расхождений | `anthropic/claude-opus-4` | `anthropic/claude-sonnet-4` | 0.5 | true |
| `delphi_r2_*` | Дельфи раунд 2 (те же персоны) | *те же, что в R1* | *те же* | 0.6 | true |
| `judge` | Финальный ранжинг | `anthropic/claude-opus-4` | `anthropic/claude-sonnet-4` | 0.3 | true |
| `framing` | Анализ фрейминга | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.5 | true |
| `style_generation` | Генерация заголовков | `yandexgpt` | `anthropic/claude-sonnet-4` | 0.8 | false |
| `style_generation_en` | Генерация (английский) | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.8 | false |
| `quality_factcheck` | Факт-чек | `anthropic/claude-sonnet-4` | `openai/gpt-4o` | 0.2 | true |
| `quality_style` | Стилистическая проверка | `yandexgpt` | `anthropic/claude-sonnet-4` | 0.3 | true |

### 3.3 Model Diversity для Delphi

Ключевое требование: **в раунде Delphi ни два агента-персоны не должны использовать одну и ту же модель**. Это обеспечивает разнообразие "мнений" и снижает корреляцию bias-ов.

```python
DELPHI_PERSONA_MODELS: dict[str, str] = {
    "realist":    "anthropic/claude-sonnet-4",
    "geostrateg": "openai/gpt-4o",
    "economist":  "google/gemini-2.5-pro",
    "media":      "meta-llama/llama-4-maverick",
    "devils":     "deepseek/deepseek-r1",
}
```

При инициализации роутер проверяет: `assert len(set(DELPHI_PERSONA_MODELS.values())) == len(DELPHI_PERSONA_MODELS)` -- все модели уникальны.

### 3.4 API

```python
class ModelRouter:
    """
    Роутер моделей: выбирает модель и провайдера по задаче.
    Управляет fallback-цепочками и бюджетом.
    """

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        *,
        assignments: dict[str, ModelAssignment] | None = None,
        budget_usd: float = 50.0,
    ) -> None:
        """
        Args:
            providers: Словарь провайдеров {'openrouter': ..., 'yandex': ...}.
            assignments: Таблица назначений (если None, используется DEFAULT_ASSIGNMENTS).
            budget_usd: Максимальный бюджет на один прогноз в USD.
        """
        ...

    async def complete(
        self,
        *,
        task: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool | None = None,
        prediction_id: str = "",
    ) -> LLMResponse:
        """
        Выполнить LLM-вызов с роутингом и fallback.

        Алгоритм:
        1. Найти ModelAssignment по task.
        2. Проверить бюджет: если оставшийся budget < estimated_cost, raise.
        3. Определить провайдера по модели.
        4. Выполнить запрос к primary модели.
        5. Если ошибка -- попробовать fallback модели по очереди.
        6. Записать CostRecord.
        7. Вернуть LLMResponse.

        Args:
            task: Идентификатор задачи из таблицы назначений.
            messages: Диалог.
            temperature: Override температуры (если None, из assignment).
            max_tokens: Override max_tokens.
            json_mode: Override json_mode.
            prediction_id: UUID прогноза для cost tracking.

        Returns:
            LLMResponse.

        Raises:
            LLMBudgetExceededError: Бюджет исчерпан.
            LLMProviderError: Все провайдеры отказали.
        """
        ...

    async def stream(
        self,
        *,
        task: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        prediction_id: str = "",
    ) -> AsyncIterator[str]:
        """
        Потоковый LLM-вызов с роутингом.

        Fallback при стриминге: если primary провайдер отказал до начала стрима,
        переключиться на fallback. Если ошибка посреди стрима -- прервать,
        не переключаться (partial output уже отправлен клиенту).

        Yields:
            Фрагменты текста.
        """
        ...

    def get_model_for_task(self, task: str) -> str:
        """
        Получить primary модель для задачи.

        Args:
            task: ID задачи.

        Returns:
            Идентификатор модели.

        Raises:
            KeyError: Задача не найдена в таблице.
        """
        ...

    def get_remaining_budget(self) -> float:
        """Оставшийся бюджет в USD."""
        ...

    def get_cost_summary(self) -> dict[str, float]:
        """
        Суммарная стоимость по стадиям.

        Returns:
            {'delphi_r1': 8.50, 'mediator': 2.10, ...}
        """
        ...

    def reset_budget(self) -> None:
        """Сбросить счётчик расходов (для нового прогноза)."""
        ...

    def _resolve_provider(self, model: str) -> LLMProvider:
        """
        Определить провайдера по имени модели.

        Правила:
        - 'yandexgpt*' -> YandexGPTClient
        - Всё остальное -> OpenRouterClient (который поддерживает все модели)
        """
        ...
```

### 3.5 Fallback-логика

```
Primary model request
    |
    +--> Success? --> return LLMResponse
    |
    +--> Error (retryable)?
         |
         +--> Retry with backoff (up to max_retries)
         |    |
         |    +--> Success? --> return
         |    +--> Still failing? --> try fallback_models[0]
         |
         +--> Error (non-retryable, e.g., 401)?
              |
              +--> Skip retries, try fallback_models[0]
                   |
                   +--> Success? --> return
                   +--> Error? --> try fallback_models[1]
                        |
                        +--> ... (until list exhausted)
                        +--> All failed --> raise LLMProviderError
```

### 3.6 Budget Enforcement

```python
class BudgetTracker:
    """Трекер расходов на LLM-вызовы в рамках одного прогноза."""

    def __init__(self, budget_usd: float) -> None:
        self._budget = budget_usd
        self._records: list[CostRecord] = []
        self._lock = asyncio.Lock()

    @property
    def spent(self) -> float:
        """Потрачено USD."""
        return sum(r.cost_usd for r in self._records)

    @property
    def remaining(self) -> float:
        """Осталось USD."""
        return max(0.0, self._budget - self.spent)

    async def record(self, cost_record: CostRecord) -> None:
        """Записать расход. Thread-safe через asyncio.Lock."""
        async with self._lock:
            self._records.append(cost_record)

    async def check_budget(self, estimated_cost: float) -> None:
        """
        Проверить, хватает ли бюджета на предстоящий вызов.

        Args:
            estimated_cost: Оценка стоимости (по числу токенов в промпте).

        Raises:
            LLMBudgetExceededError: Если estimated_cost > remaining.
        """
        if estimated_cost > self.remaining:
            raise LLMBudgetExceededError(self._budget, self.spent)

    def summary_by_stage(self) -> dict[str, float]:
        """Группировка расходов по стадиям пайплайна."""
        result: dict[str, float] = {}
        for r in self._records:
            result[r.stage] = result.get(r.stage, 0.0) + r.cost_usd
        return result

    def summary_by_model(self) -> dict[str, float]:
        """Группировка расходов по моделям."""
        result: dict[str, float] = {}
        for r in self._records:
            result[r.model] = result.get(r.model, 0.0) + r.cost_usd
        return result

    def to_records(self) -> list[CostRecord]:
        """Все записи расходов (для сохранения в БД)."""
        return list(self._records)

    def reset(self) -> None:
        """Сбросить для нового прогноза."""
        self._records.clear()
```

---

## 4. Prompt Templates (`prompts/base.py`)

### 4.1 Назначение

Управление промптами через Jinja2-шаблонизацию. Каждый агент имеет свой шаблон промпта, но все наследуются от `BasePrompt` с единым интерфейсом.

### 4.2 Архитектурные решения

- **Jinja2**: промпты могут содержать условия, циклы, фильтры. Например, список событий рендерится циклом.
- **Разделение system / user**: system prompt -- постоянная инструкция (роль, формат вывода), user prompt -- данные конкретного запроса.
- **JSON Schema для structured output**: промпт может содержать описание ожидаемой JSON-структуры, которая валидируется Pydantic после парсинга.
- **Промпты хранятся в коде**, а не в БД: это позволяет version-control и review через PR.

### 4.3 API

```python
from jinja2 import Environment, BaseLoader, StrictUndefined
from pydantic import BaseModel


class BasePrompt:
    """
    Базовый класс для LLM-промптов с Jinja2-шаблонизацией.

    Подклассы определяют шаблоны system_template и user_template,
    а также output_schema для валидации ответа.
    """

    # Подклассы переопределяют эти атрибуты
    system_template: str = ""
    user_template: str = ""
    output_schema: type[BaseModel] | None = None  # Pydantic-модель для парсинга ответа

    def __init__(self) -> None:
        self._env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,  # Ошибка при неизвестных переменных
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_system(self, **variables) -> str:
        """
        Рендерить system prompt с подстановкой переменных.

        Args:
            **variables: Переменные для шаблона.

        Returns:
            Готовый system prompt.

        Raises:
            jinja2.UndefinedError: Если переменная не передана.
        """
        template = self._env.from_string(self.system_template)
        return template.render(**variables).strip()

    def render_user(self, **variables) -> str:
        """
        Рендерить user prompt с подстановкой переменных.

        Args:
            **variables: Переменные для шаблона.

        Returns:
            Готовый user prompt.
        """
        template = self._env.from_string(self.user_template)
        return template.render(**variables).strip()

    def to_messages(self, **variables) -> list[LLMMessage]:
        """
        Сформировать полный диалог (system + user) для отправки в LLM.

        Args:
            **variables: Переменные для обоих шаблонов.

        Returns:
            [LLMMessage(role=system, ...), LLMMessage(role=user, ...)]
        """
        messages = []
        system = self.render_system(**variables)
        if system:
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system))
        user = self.render_user(**variables)
        if user:
            messages.append(LLMMessage(role=MessageRole.USER, content=user))
        return messages

    def render_output_schema_instruction(self) -> str:
        """
        Сгенерировать текстовую инструкцию с JSON Schema для structured output.

        Если output_schema определена, генерирует блок вида:

        ```
        Respond ONLY with valid JSON matching this schema:
        {
            "type": "object",
            "properties": {
                "events": {"type": "array", ...},
                ...
            },
            "required": [...]
        }
        ```

        Вставляется в конец system prompt автоматически.

        Returns:
            Строка с инструкцией или "" если schema не задана.
        """
        if self.output_schema is None:
            return ""
        schema = self.output_schema.model_json_schema()
        return (
            "\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```"
        )

    def parse_response(self, content: str) -> BaseModel | None:
        """
        Распарсить ответ LLM в Pydantic-модель.

        Алгоритм:
        1. Если output_schema is None -- вернуть None.
        2. Попробовать json.loads(content).
        3. Если не JSON -- попробовать извлечь JSON из Markdown code block.
        4. Валидировать через output_schema.model_validate(data).

        Args:
            content: Сырой текст ответа LLM.

        Returns:
            Экземпляр output_schema или None.

        Raises:
            PromptParseError: Если ответ невалидный JSON или не проходит валидацию.
        """
        ...


class PromptParseError(Exception):
    """Ошибка парсинга ответа LLM."""
    def __init__(self, message: str, raw_content: str):
        super().__init__(message)
        self.raw_content = raw_content
```

### 4.4 Пример конкретного промпта

```python
# src/llm/prompts/event_analysis.py

from src.llm.prompts.base import BasePrompt
from pydantic import BaseModel, Field


class EventCluster(BaseModel):
    """Один кластер событий в ответе LLM."""
    cluster_name: str
    summary: str
    signals: list[int] = Field(description="Индексы сигналов из входного списка")
    newsworthiness: float = Field(ge=0.0, le=1.0)


class EventClusteringOutput(BaseModel):
    """Ожидаемый формат ответа от LLM для кластеризации."""
    clusters: list[EventCluster]
    unclustered_signals: list[int] = Field(default_factory=list)


class EventClusteringPrompt(BasePrompt):
    """Промпт для кластеризации сигналов в события (Stage 2)."""

    output_schema = EventClusteringOutput

    system_template = """You are an expert news analyst. Your task is to cluster
news signals into coherent event threads.

Rules:
- Group signals that describe the same real-world event or storyline
- Each cluster should have a clear, descriptive name
- Rate newsworthiness from 0.0 (trivial) to 1.0 (breaking/critical)
- Signals that don't fit any cluster go to unclustered_signals
- Maximum {{ max_clusters }} clusters
- Minimum 2 signals per cluster

{{ output_schema_instruction }}"""

    user_template = """Here are {{ signals|length }} news signals collected in the last
{{ days_back }} days:

{% for signal in signals %}
[{{ loop.index0 }}] {{ signal.title }}
    Source: {{ signal.source_name }} | Date: {{ signal.published_at or "unknown" }}
    {{ signal.summary[:200] }}
{% endfor %}

Cluster these signals into event threads. Focus on events that are likely
to develop further and become headlines on {{ target_date }}.
Target outlet: {{ outlet_name }} ({{ outlet_country }}, {{ outlet_language }})."""
```

### 4.5 Реестр промптов

Каждый файл в `prompts/` экспортирует один или несколько классов-промптов. Промпт привязывается к агенту через задание в конструкторе агента:

```python
# src/agents/analysts/event_trend.py

class EventTrendAnalyzer(BaseAgent):
    def __init__(self, router: ModelRouter, ...):
        self._router = router
        self._prompt = EventClusteringPrompt()  # промпт зашит в агенте

    async def execute(self, context: PipelineContext) -> AgentResult:
        messages = self._prompt.to_messages(
            signals=context.signals,
            max_clusters=20,
            days_back=7,
            target_date=str(context.target_date),
            outlet_name=context.outlet.name,
            outlet_country=context.outlet.country,
            outlet_language=context.outlet.language,
            output_schema_instruction=self._prompt.render_output_schema_instruction(),
        )

        response = await self._router.complete(
            task="event_clustering",
            messages=messages,
            prediction_id=context.prediction_id,
        )

        parsed = self._prompt.parse_response(response.content)
        ...
```

---

## 5. Таблица цен моделей (OpenRouter, март 2026)

Цены за 1 миллион токенов. Источник: `https://openrouter.ai/models`.

> **Дисклеймер**: цены приведены по состоянию на март 2026 и могут измениться. В коде таблица хранится как словарь `MODEL_PRICING` и обновляется вручную при изменении тарифов.

| Model ID | Input ($/1M tokens) | Output ($/1M tokens) | Context window |
|---|---|---|---|
| `openai/gpt-4o-mini` | $0.15 | $0.60 | 128K |
| `openai/gpt-4o` | $2.50 | $10.00 | 128K |
| `openai/o3-mini` | $1.10 | $4.40 | 200K |
| `anthropic/claude-sonnet-4` | $3.00 | $15.00 | 200K |
| `anthropic/claude-opus-4` | $15.00 | $75.00 | 200K |
| `anthropic/claude-haiku-3.5` | $0.80 | $4.00 | 200K |
| `google/gemini-2.5-pro` | $1.25 | $10.00 | 1M |
| `google/gemini-2.0-flash` | $0.10 | $0.40 | 1M |
| `meta-llama/llama-4-maverick` | $0.20 | $0.60 | 1M |
| `deepseek/deepseek-r1` | $0.55 | $2.19 | 64K |
| `deepseek/deepseek-v3-0324` | $0.30 | $0.88 | 64K |

### YandexGPT (Yandex Cloud, март 2026)

| Модель | Input ($/1K tokens) | Output ($/1K tokens) |
|---|---|---|
| `yandexgpt` (Pro) | ~$0.0032 | ~$0.0032 |
| `yandexgpt-lite` | ~$0.00075 | ~$0.00075 |

> Тарифы Yandex Cloud указаны в рублях; приведённые доллары -- конвертация по курсу ~80 RUB/USD.

### Реализация в коде

```python
# src/llm/providers.py

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # model_id: (input_per_million, output_per_million) in USD
    "openai/gpt-4o-mini":           (0.15, 0.60),
    "openai/gpt-4o":                (2.50, 10.00),
    "openai/o3-mini":               (1.10, 4.40),
    "anthropic/claude-sonnet-4":    (3.00, 15.00),
    "anthropic/claude-opus-4":      (15.00, 75.00),
    "anthropic/claude-haiku-3.5":   (0.80, 4.00),
    "google/gemini-2.5-pro":        (1.25, 10.00),
    "google/gemini-2.0-flash":      (0.10, 0.40),
    "meta-llama/llama-4-maverick":  (0.20, 0.60),
    "deepseek/deepseek-r1":         (0.55, 2.19),
    "deepseek/deepseek-v3-0324":    (0.30, 0.88),
}

YANDEX_PRICING: dict[str, tuple[float, float]] = {
    # model_id: (input_per_thousand, output_per_thousand) in USD
    "yandexgpt":      (0.0032, 0.0032),
    "yandexgpt-lite": (0.00075, 0.00075),
}


def calculate_cost(
    model: str, tokens_in: int, tokens_out: int,
) -> float:
    """
    Рассчитать стоимость вызова.

    Returns:
        Стоимость в USD. 0.0 если модель не найдена в таблице.
    """
    if model in MODEL_PRICING:
        price_in, price_out = MODEL_PRICING[model]
        return (tokens_in / 1_000_000 * price_in) + (tokens_out / 1_000_000 * price_out)

    # YandexGPT: цены за 1K (не за 1M)
    yandex_key = model.replace("/latest", "").replace("yandexgpt/", "yandexgpt")
    if yandex_key in YANDEX_PRICING:
        price_in, price_out = YANDEX_PRICING[yandex_key]
        return (tokens_in / 1_000 * price_in) + (tokens_out / 1_000 * price_out)

    return 0.0
```

---

## 6. Cost Tracking: аккумуляция по пайплайну

### 6.1 Поток данных

```
Agent вызывает router.complete(task=..., prediction_id=...)
    |
    +--> Router выполняет LLM-запрос
    |
    +--> Провайдер возвращает LLMResponse (с tokens, cost)
    |
    +--> Router создаёт CostRecord и сохраняет в BudgetTracker
    |
    +--> BudgetTracker аккумулирует spent, проверяет budget
```

### 6.2 Жизненный цикл BudgetTracker

```python
# src/agents/orchestrator.py

class PipelineOrchestrator:
    async def run(self, request: PredictionRequest) -> PredictionResponse:
        # 1. Создать трекер для этого прогноза
        budget_tracker = BudgetTracker(budget_usd=self._config.max_budget_usd)
        self._router.set_budget_tracker(budget_tracker)

        try:
            # 2. Запустить 9 стадий пайплайна
            ...
        finally:
            # 3. Сохранить records в БД
            cost_records = budget_tracker.to_records()
            await self._db.save_cost_records(cost_records)

            # 4. Логировать итог
            logger.info(
                "Pipeline cost summary",
                prediction_id=request.id,
                total_cost=budget_tracker.spent,
                by_stage=budget_tracker.summary_by_stage(),
                by_model=budget_tracker.summary_by_model(),
            )

            # 5. Сбросить трекер
            budget_tracker.reset()
```

### 6.3 Бюджетный контроль

- **Бюджет по умолчанию**: $50 на один прогноз (настраивается через `MAX_BUDGET_USD` env var).
- **Проверка перед вызовом**: `router.complete()` оценивает стоимость по числу входных токенов (через `estimate_messages_tokens`) и проверяет `budget_tracker.check_budget(estimated_cost)`.
- **При превышении**: бросается `LLMBudgetExceededError`. Оркестратор ловит исключение и:
  1. Помечает прогноз как `status="budget_exceeded"`.
  2. Возвращает частичные результаты (то, что успел собрать).
  3. Логирует предупреждение.
- **Мягкий лимит**: при достижении 80% бюджета -- warning в лог и SSE-event для UI.

---

## 7. Конфигурация

```python
# src/config.py

class LLMConfig(BaseSettings):
    """Настройки LLM-слоя."""

    # Провайдеры
    openrouter_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_api_key: str = ""

    # Дефолтные модели (переопределяемые через таблицу назначений)
    default_model_cheap: str = "openai/gpt-4o-mini"
    default_model_reasoning: str = "anthropic/claude-sonnet-4"
    default_model_strong: str = "anthropic/claude-opus-4"
    default_model_russian: str = "yandexgpt"

    # Retry
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 30.0
    llm_timeout_seconds: float = 120.0

    # Budget
    max_budget_usd: float = 50.0
    budget_warning_threshold: float = 0.8  # Warning при 80%

    class Config:
        env_prefix = ""  # Используем OPENROUTER_API_KEY напрямую
```

---

## 8. Зависимости

```toml
# В pyproject.toml [project.dependencies]

# OpenAI SDK (OpenRouter-совместимый)
openai = ">=1.0"

# YandexGPT
yandex-cloud-ml-sdk = ">=0.3"

# Token counting
tiktoken = ">=0.7"

# Шаблонизация промптов
Jinja2 = ">=3.1"

# Pydantic (shared)
pydantic = ">=2.0"
pydantic-settings = ">=2.0"
```

---

## 9. Тестирование

### 9.1 Unit-тесты (`tests/test_llm/`)

| Тест | Что проверяет |
|---|---|
| `test_openrouter_complete` | Мок OpenAI SDK, проверка маппинга request/response |
| `test_openrouter_retry` | 3 ошибки 503, потом успех -> LLMResponse |
| `test_openrouter_non_retryable` | Ошибка 401 -> не retry, сразу raise |
| `test_yandex_complete` | Мок YandexGPT SDK, проверка маппинга |
| `test_yandex_temperature_clamp` | temperature=1.5 -> warning + clamp to 1.0 |
| `test_router_primary_success` | Primary модель отвечает -> LLMResponse |
| `test_router_fallback` | Primary fail -> fallback success |
| `test_router_all_fail` | Все модели fail -> LLMProviderError |
| `test_router_budget_check` | Бюджет исчерпан -> LLMBudgetExceededError |
| `test_router_model_diversity` | Все Delphi-модели уникальны |
| `test_budget_tracker_accumulation` | 3 записи -> correct spent |
| `test_budget_tracker_summary` | summary_by_stage() корректен |
| `test_cost_calculation` | calculate_cost() для разных моделей |
| `test_prompt_render` | Jinja2 подстановка переменных |
| `test_prompt_schema_instruction` | JSON schema генерируется корректно |
| `test_prompt_parse_json` | Парсинг JSON из ответа LLM |
| `test_prompt_parse_markdown_block` | Парсинг JSON из ```json...``` блока |
| `test_prompt_parse_invalid` | Невалидный JSON -> PromptParseError |
| `test_estimate_tokens` | tiktoken корректно считает токены |

### 9.2 Интеграционные тесты

Помечены `@pytest.mark.integration`:

| Тест | Что проверяет |
|---|---|
| `test_openrouter_real_call` | Реальный вызов GPT-4o-mini через OpenRouter |
| `test_yandex_real_call` | Реальный вызов YandexGPT |
| `test_openrouter_streaming` | Реальный streaming вызов |
| `test_router_e2e` | Полный цикл: router -> provider -> response -> cost |

### 9.3 Мок-стратегия

Для unit-тестов провайдеры мокаются через `unittest.mock.AsyncMock`:

```python
# tests/test_llm/conftest.py

import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_openrouter():
    provider = AsyncMock(spec=OpenRouterClient)
    provider.provider_name = "openrouter"
    provider.complete.return_value = LLMResponse(
        content='{"result": "test"}',
        model="openai/gpt-4o-mini",
        provider="openrouter",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.00005,
        duration_ms=500,
    )
    return provider


@pytest.fixture
def mock_yandex():
    provider = AsyncMock(spec=YandexGPTClient)
    provider.provider_name = "yandex"
    provider.complete.return_value = LLMResponse(
        content="Тестовый ответ",
        model="yandexgpt",
        provider="yandex",
        tokens_in=80,
        tokens_out=40,
        cost_usd=0.00038,
        duration_ms=800,
    )
    return provider


@pytest.fixture
def router(mock_openrouter, mock_yandex):
    return ModelRouter(
        providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
        budget_usd=50.0,
    )
```

---

## 10. Наблюдаемость

### 10.1 Структурированное логирование

Каждый LLM-вызов логируется с полными метриками:

```python
import structlog

logger = structlog.get_logger()

# После каждого вызова:
logger.info(
    "llm_call_completed",
    task=task,
    model=response.model,
    provider=response.provider,
    tokens_in=response.tokens_in,
    tokens_out=response.tokens_out,
    cost_usd=response.cost_usd,
    duration_ms=response.duration_ms,
    finish_reason=response.finish_reason,
    prediction_id=prediction_id,
)

# При fallback:
logger.warning(
    "llm_fallback_triggered",
    task=task,
    failed_model=primary_model,
    fallback_model=fallback_model,
    error=str(error),
    prediction_id=prediction_id,
)

# При превышении бюджета:
logger.error(
    "llm_budget_exceeded",
    budget_usd=budget_tracker._budget,
    spent_usd=budget_tracker.spent,
    prediction_id=prediction_id,
)
```

### 10.2 Метрики

Для будущей интеграции с Prometheus:

- `llm_calls_total` (counter): `{task, model, provider, status}`
- `llm_call_duration_seconds` (histogram): `{task, model}`
- `llm_tokens_total` (counter): `{direction=in|out, model}`
- `llm_cost_usd_total` (counter): `{task, model}`
- `llm_budget_remaining_usd` (gauge): `{prediction_id}`

---

## 11. Ограничения и будущие расширения

### Текущие ограничения

- **Нет локальных моделей**: весь LLM inference -- через внешние API. Латентность зависит от сети.
- **Нет prompt caching**: каждый вызов отправляет полный промпт. OpenRouter поддерживает prompt caching для Anthropic моделей -- можно включить в v2.
- **Нет batching**: каждый вызов -- отдельный HTTP-запрос. Для стадий с 20+ параллельными вызовами это может создавать нагрузку.
- **Таблица цен -- ручная**: обновляется вручную при изменении тарифов.

### Расширения v2

- **Prompt caching**: включить `anthropic-beta: prompt-caching-2024-07-31` для Claude-моделей. Экономия до 90% на повторяющихся system prompt-ах.
- **OpenRouter fallback routing**: использовать `route: "fallback"` в OpenRouter API вместо ручного fallback.
- **Локальные модели**: Ollama или vLLM для дешёвых задач (кластеризация, дедупликация).
- **Автообновление цен**: периодический запрос к `https://openrouter.ai/api/v1/models` для актуализации `MODEL_PRICING`.
- **Structured outputs**: использовать OpenAI/Anthropic native structured outputs (JSON schema в API) вместо промпт-инструкций.
- **A/B тестирование моделей**: рандомизация назначений для сравнения качества моделей на одних задачах.
