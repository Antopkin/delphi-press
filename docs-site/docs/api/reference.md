# REST API Reference

Полное описание всех REST API-эндпоинтов Delphi Press. API использует JSON, требует аутентификации через JWT и доступен по адресу `https://delphi.antopkin.ru/api/v1`.

## Обзор

| Группа | Эндпоинты | Описание |
|--------|-----------|---------|
| **Аутентификация** | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Управление учётной записью и JWT-токеном |
| **Прогнозы** | `POST /predictions`, `GET /predictions`, `GET /predictions/{id}`, `GET /predictions/{id}/stream` | CRUD-операции и SSE-поток прогресса |
| **Медиа** | `GET /outlets` | Поиск и автокомплит СМИ |
| **API-ключи** | `GET /keys`, `POST /keys`, `DELETE /keys/{id}`, `POST /keys/{id}/validate` | Управление ключами OpenRouter |
| **Здоровье** | `GET /health`, `GET /health/feeds` | Проверка статуса системы |

---

## Аутентификация

Все защищённые эндпоинты требуют JWT-токен в заголовке:

```bash
Authorization: Bearer <access_token>
```

### POST /auth/register

Регистрация нового пользователя.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password_min_8_chars"
}
```

**Response: 201 Created**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Ошибки:**

- `409 Conflict` — Email уже зарегистрирован

**Пример:**
```bash
curl -X POST https://delphi.antopkin.ru/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "analyst@example.com",
    "password": "MySecurePass123!"
  }'
```

---

### POST /auth/login

Аутентификация и получение JWT-токена.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password_min_8_chars"
}
```

**Response: 200 OK**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Ошибки:**

- `401 Unauthorized` — Неверный email или пароль

**Пример:**
```bash
curl -X POST https://delphi.antopkin.ru/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "analyst@example.com",
    "password": "MySecurePass123!"
  }' \
  -s | jq -r '.access_token'
```

---

### GET /auth/me

Получить информацию о текущем пользователе. **Требует аутентификацию.**

**Response: 200 OK**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "analyst@example.com",
  "is_active": true,
  "created_at": "2026-04-01T12:34:56Z"
}
```

**Пример:**
```bash
curl -X GET https://delphi.antopkin.ru/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## Прогнозы

### POST /predictions

Создать новый прогноз и поставить в очередь для обработки.

**Request:**
```json
{
  "outlet": "ТАСС",
  "target_date": "2026-04-15",
  "preset": "full",
  "api_key": "sk-or-...",
  "outlet_url": "https://tass.ru"
}
```

**Параметры:**

| Параметр | Тип | Обязателен | Описание |
|----------|-----|-----------|---------|
| `outlet` | string (1–200 символов) | Да | Название или сокращение СМИ (например: "ТАСС", "BBC Russian", "Независимая газета") |
| `target_date` | date (YYYY-MM-DD) | Да | Целевая дата, на которую делается прогноз |
| `preset` | string | Нет (по умолчанию "full") | Конфигурация пайплайна: `light` или `full` |
| `api_key` | string | Нет | Ваш OpenRouter API-ключ. Если не указан, используется сохранённый в профиле |
| `outlet_url` | string (URL) | Нет | URL официального сайта СМИ для уточнения разрешения |

**Response: 201 Created**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "outlet": "ТАСС",
  "target_date": "2026-04-15",
  "created_at": "2026-04-05T10:00:00Z",
  "progress_url": "/api/v1/predictions/a1b2c3d4.../stream",
  "result_url": "/api/v1/predictions/a1b2c3d4...",
  "outlet_resolved": true,
  "outlet_language": "ru",
  "outlet_url": "https://tass.ru",
  "key_source": "user"
}
```

**Ключевые поля ответа:**

| Поле | Описание |
|------|---------|
| `id` | UUID прогноза. Используйте для отслеживания статуса и получения результатов |
| `status` | `pending`, `processing`, `completed`, `failed` |
| `progress_url` | SSE-эндпоинт для подписки на обновления прогресса |
| `result_url` | Полный результат после завершения |
| `outlet_resolved` | Удалось ли системе автоматически разрешить СМИ (определить язык и URL) |
| `outlet_language` | Язык выходных заголовков (ISO 639-1 код, например `ru`, `en`) |
| `outlet_url` | Разрешённый или переданный URL СМИ |
| `key_source` | Источник API-ключа: `manual` (вручную в запросе), `user` (сохранённый в профиле), `server` (серверный) |

**Ошибки:**

- `400 Bad Request` — Неверный `preset` или некорректная дата
- `401 Unauthorized` — API-ключ не предоставлен, не сохранён и нет серверного ключа
- `409 Conflict` — Прогноз с такими параметрами уже существует
- `503 Service Unavailable` — Очередь задач недоступна

**Пример:**
```bash
curl -X POST https://delphi.antopkin.ru/api/v1/predictions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "outlet": "ТАСС",
    "target_date": "2026-04-15",
    "preset": "full",
    "api_key": "sk-or-v1-..."
  }'
```

!!! note "Асинхронная обработка"
    Эндпоинт возвращает `201 Created` с метаданными прогноза. Обработка запускается асинхронно в фоне. Используйте `progress_url` для подписки на обновления в реальном времени или `result_url` для получения финального результата.

---

### GET /predictions

Список прогнозов с пагинацией. Возвращает все прогнозы в системе (включая анонимные и публичные).

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|---------|
| `limit` | integer (1–100) | 20 | Количество результатов на странице |
| `offset` | integer (≥0) | 0 | Смещение от начала списка |
| `status` | string | Нет | Фильтр по статусу: `pending`, `collecting`, `analyzing`, `forecasting`, `generating`, `completed`, `failed` |

**Response: 200 OK**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "outlet_name": "ТАСС",
      "target_date": "2026-04-15",
      "status": "completed",
      "created_at": "2026-04-05T10:00:00Z",
      "total_duration_ms": 120000,
      "headlines_count": 5
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

**Пример:**
```bash
curl -X GET 'https://delphi.antopkin.ru/api/v1/predictions?status=completed&limit=10'
```

!!! note "Доступность"
    Этот эндпоинт доступен без аутентификации. Возвращает публичный список всех прогнозов, включая те, которые принадлежат другим пользователям.

---

### GET /predictions/{prediction_id}

Полная информация о конкретном прогнозе, включая все заголовки и метрики пайплайна.

**Path Parameters:**

- `prediction_id` (string) — UUID прогноза

**Response: 200 OK**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "outlet_name": "ТАСС",
  "target_date": "2026-04-15",
  "status": "completed",
  "created_at": "2026-04-05T10:00:00Z",
  "completed_at": "2026-04-05T10:02:00Z",
  "total_duration_ms": 120000,
  "total_llm_cost_usd": 2.45,
  "error_message": null,
  "headlines": [
    {
      "rank": 1,
      "headline_text": "Центральный банк России повышает базовую ставку",
      "first_paragraph": "Решение принято на плановом заседании совета директоров...",
      "confidence": 0.87,
      "confidence_label": "high",
      "category": "экономика",
      "reasoning": "На основе анализа макроэкономических индикаторов...",
      "evidence_chain": [
        {
          "source": "FedWatch",
          "signal": "инфляционные ожидания выросли на 0.3%"
        }
      ],
      "agent_agreement": "4/5 персон согласны",
      "dissenting_views": [
        {
          "persona": "Реалист",
          "argument": "Политический календарь говорит против повышения"
        }
      ]
    }
  ],
  "pipeline_steps": [
    {
      "agent_name": "RSSCollector",
      "step_order": 1,
      "status": "completed",
      "duration_ms": 5000,
      "llm_model_used": null,
      "llm_tokens_in": 0,
      "llm_tokens_out": 0,
      "llm_cost_usd": 0.0
    },
    {
      "agent_name": "EventClustering",
      "step_order": 2,
      "status": "completed",
      "duration_ms": 12000,
      "llm_model_used": "anthropic/claude-opus-4.6",
      "llm_tokens_in": 3200,
      "llm_tokens_out": 800,
      "llm_cost_usd": 0.18
    }
  ]
}
```

**Ошибки:**

- `404 Not Found` — Прогноз не найден
- `403 Forbidden` — Доступ запрещён (прогноз принадлежит другому аутентифицированному пользователю)

**Доступность:**

- Анонимные прогнозы (user_id = None) доступны всем
- Личные прогнозы доступны только владельцу

**Пример:**
```bash
curl -X GET 'https://delphi.antopkin.ru/api/v1/predictions/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
```

---

### GET /predictions/{prediction_id}/stream

Server-Sent Events (SSE) поток прогресса выполнения прогноза в реальном времени.

**Event Types:**

| Событие | Данные | Описание |
|---------|--------|---------|
| `connected` | `{prediction_id: "..."}` | Соединение установлено |
| `progress` | `{stage: "Stage 2", message: "...", progress_pct: 15}` | Текущий прогресс |
| `step_complete` | `{agent: "EventClustering", duration_ms: 12000, cost_usd: 0.18}` | Этап завершён |
| `completed` | `{prediction_id: "...", total_cost_usd: 2.45}` | Прогноз завершён |
| `error` | `{message: "...", stage: "Stage 4"}` | Критическая ошибка |
| `timeout` | `{message: "Connection timed out"}` | Соединение закрыто по таймауту |

**Пример на JavaScript:**
```javascript
const eventSource = new EventSource(
  '/api/v1/predictions/a1b2c3d4.../stream',
  {
    headers: { 'Authorization': `Bearer ${token}` }
  }
);

eventSource.addEventListener('progress', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Прогресс: ${data.progress_pct}% — ${data.message}`);
});

eventSource.addEventListener('completed', (event) => {
  console.log('Прогноз готов!');
  eventSource.close();
});

eventSource.addEventListener('error', (event) => {
  console.error('Ошибка:', JSON.parse(event.data).message);
  eventSource.close();
});
```

**Пример на Python:**
```python
import httpx

token = "..."
prediction_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

with httpx.stream(
    "GET",
    f"https://delphi.antopkin.ru/api/v1/predictions/{prediction_id}/stream",
    headers={"Authorization": f"Bearer {token}"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data:"):
            import json
            event_data = json.loads(line[5:])
            print(f"Событие: {event_data}")
```

**Примечание:** Соединение закроется после события `completed` или `error`, или по таймауту (120 секунд неактивности).

---

## Медиа

### GET /outlets

Автокомплит-поиск СМИ по названию. Поиск проводится по двум источникам:
1. **Статический каталог** — 20 популярных мировых изданий (быстрый поиск в памяти)
2. **Динамическая база** — СМИ, которые были разрешены в процессе прогнозирования

Результаты дедублицируются и объединяются.

**Query Parameters:**

| Параметр | Тип | Обязателен | Описание |
|----------|-----|-----------|---------|
| `q` | string (1–100 символов) | Да | Строка поиска (название или часть названия) |
| `limit` | integer (1–50) | Нет (по умолчанию 10) | Максимум результатов |

**Response: 200 OK**
```json
{
  "items": [
    {
      "name": "ТАСС",
      "normalized_name": "тасс",
      "country": "RU",
      "language": "ru",
      "political_leaning": "neutral",
      "website_url": "https://tass.ru"
    },
    {
      "name": "ТВЦ",
      "normalized_name": "твц",
      "country": "RU",
      "language": "ru",
      "political_leaning": "neutral",
      "website_url": "https://tvc.ru"
    }
  ]
}
```

**Ошибки:**

- `400 Bad Request` — `q` короче 1 символа или длиннее 100

**Пример:**
```bash
curl -X GET 'https://delphi.antopkin.ru/api/v1/outlets?q=ТАСС&limit=5'
```

!!! note "Анонимный эндпоинт"
    Этот эндпоинт доступен без аутентификации.

---

## API-ключи

Управление OpenRouter API-ключами. Ключи шифруются на сервере и не передаются в ответах.

### GET /keys

Список API-ключей пользователя. **Требует аутентификацию.**

**Response: 200 OK**
```json
[
  {
    "id": 1,
    "provider": "openrouter",
    "label": "Мой основной ключ",
    "is_active": true,
    "created_at": "2026-04-01T12:34:56Z",
    "last_used_at": "2026-04-05T09:45:00Z",
    "health": "ok"
  },
  {
    "id": 2,
    "provider": "openrouter",
    "label": "Резервный ключ",
    "is_active": false,
    "created_at": "2026-03-15T08:00:00Z",
    "last_used_at": null,
    "health": "corrupted"
  }
]
```

**Поля:**

| Поле | Описание |
|------|---------|
| `id` | Числовой идентификатор ключа |
| `provider` | Провайдер LLM (на данный момент только `openrouter`) |
| `label` | Пользовательское имя/описание ключа |
| `is_active` | Используется ли ключ по умолчанию при создании прогнозов |
| `health` | `ok` (рабочий) или `corrupted` (повреждён при расшифровке, требуется пересохранение) |
| `last_used_at` | Время последнего использования для прогнозирования или `null` |

**Пример:**
```bash
curl -X GET https://delphi.antopkin.ru/api/v1/keys \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /keys

Добавить новый OpenRouter API-ключ. Ключ шифруется перед сохранением.

**Request:**
```json
{
  "provider": "openrouter",
  "api_key": "sk-or-v1-...",
  "label": "Мой основной ключ"
}
```

**Parameters:**

| Параметр | Тип | Обязателен | Описание |
|----------|-----|-----------|---------|
| `provider` | string | Да | `openrouter` |
| `api_key` | string (≥10 символов) | Да | Ваш OpenRouter API-ключ (начинается с `sk-or-`) |
| `label` | string (≤100 символов) | Нет | Описание ключа для личного учёта |

**Response: 201 Created**
```json
{
  "id": 3,
  "provider": "openrouter",
  "label": "Мой основной ключ",
  "is_active": true,
  "created_at": "2026-04-05T10:15:00Z",
  "last_used_at": null,
  "health": "ok"
}
```

**Ошибки:**

- `400 Bad Request` — API-ключ короче 10 символов
- `409 Conflict` — Ключ для этого провайдера уже существует

**Пример:**
```bash
curl -X POST https://delphi.antopkin.ru/api/v1/keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "provider": "openrouter",
    "api_key": "sk-or-v1-...",
    "label": "Работа"
  }'
```

---

### DELETE /keys/{key_id}

Удалить сохранённый API-ключ. **Требует аутентификацию.**

**Path Parameters:**

- `key_id` (integer) — Числовой идентификатор ключа

**Response: 204 No Content**

**Ошибки:**

- `404 Not Found` — Ключ не найден или принадлежит другому пользователю

**Пример:**
```bash
curl -X DELETE https://delphi.antopkin.ru/api/v1/keys/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /keys/{key_id}/validate

Проверить валидность сохранённого API-ключа, отправив тестовый запрос к OpenRouter.

**Path Parameters:**

- `key_id` (integer) — Числовой идентификатор ключа

**Response: 200 OK**
```json
{
  "valid": true,
  "message": "Ключ OpenRouter валиден."
}
```

или

```json
{
  "valid": false,
  "message": "Ключ невалиден или отозван."
}
```

**Возможные сообщения:**

| Сообщение | Смысл |
|-----------|-------|
| `Ключ OpenRouter валиден.` | Ключ рабочий |
| `Ключ невалиден или отозван.` | Ключ неправильный или отозван на OpenRouter |
| `Ключ повреждён (невозможно расшифровать). Удалите и добавьте заново.` | Ошибка при расшифровке (требуется пересохранение) |
| `Ошибка подключения: ...` | Сетевая ошибка при подключении к OpenRouter |

**Ошибки:**

- `404 Not Found` — Ключ не найден

**Пример:**
```bash
curl -X POST https://delphi.antopkin.ru/api/v1/keys/1/validate \
  -H "Authorization: Bearer $TOKEN"
```

---

## Здоровье и мониторинг

### GET /health

Проверка работоспособности системы (БД, Redis, версия).

**Response: 200 OK** (если все работает)
```json
{
  "status": "healthy",
  "version": "0.9.5",
  "uptime_seconds": 86400,
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 5
    },
    "redis": {
      "status": "ok",
      "latency_ms": 2
    }
  }
}
```

**Response: 503 Service Unavailable** (если что-то не работает)
```json
{
  "status": "unhealthy",
  "version": "0.9.5",
  "uptime_seconds": 7200,
  "checks": {
    "database": {
      "status": "error",
      "error": "unavailable"
    },
    "redis": {
      "status": "ok",
      "latency_ms": 3
    }
  }
}
```

**Проверяемые компоненты:**

| Компонент | Что проверяется |
|-----------|-----------------|
| `database` | SQLite/PostgreSQL отвечает на SELECT 1 |
| `redis` | Redis отвечает на PING, измеряется задержка |

**Пример:**
```bash
curl -X GET https://delphi.antopkin.ru/api/v1/health
```

!!! note "Анонимный эндпоинт"
    Доступен без аутентификации для мониторинга.

---

### GET /health/feeds

Статус RSS-фидов для каждого источника данных. Информация загружается из Redis по данным, накопленным RSSCollector-ом.

**Response: 200 OK**
```json
{
  "feeds": [
    {
      "feed_url": "https://tass.ru/rss/v2.0/",
      "last_fetched_at": "2026-04-05T10:30:00Z",
      "articles_count": "512",
      "error_count": "0",
      "last_error": null
    },
    {
      "feed_url": "https://bbcnews.bbc.co.uk/feed.xml",
      "last_fetched_at": "2026-04-05T10:28:30Z",
      "articles_count": "1024",
      "error_count": "3",
      "last_error": "HTTP 429: Too Many Requests"
    }
  ]
}
```

**Поля:**

| Поле | Описание |
|------|---------|
| `feed_url` | URL RSS-фида |
| `last_fetched_at` | Момент последней успешной загрузки |
| `articles_count` | Количество статей, загруженных из фида |
| `error_count` | Количество ошибок при загрузке |
| `last_error` | Последняя ошибка (если есть) |

**Пример:**
```bash
curl -X GET https://delphi.antopkin.ru/api/v1/health/feeds
```

!!! note "Анонимный эндпоинт"
    Доступен без аутентификации для мониторинга.

---

## Обработка ошибок

Все ошибки возвращаются в формате:

```json
{
  "detail": "Описание ошибки на русском языке"
}
```

### Коды статуса

| Код | Смысл | Пример |
|-----|-------|--------|
| `200` | OK — запрос успешен | Получение данных |
| `201` | Created — ресурс создан | Создание прогноза |
| `204` | No Content — успешно удалено | Удаление ключа |
| `400` | Bad Request — некорректный ввод | Неверный `preset` |
| `401` | Unauthorized — требуется аутентификация | Отсутствует токен |
| `403` | Forbidden — доступ запрещён | Чужой прогноз |
| `404` | Not Found — ресурс не существует | Прогноз не найден |
| `409` | Conflict — конфликт состояния | Email уже используется |
| `503` | Service Unavailable — сервис недоступен | Redis отключён |

---

## Примеры workflow

### Полный цикл: регистрация → прогноз → результат

```bash
#!/bin/bash
set -e

API="https://delphi.antopkin.ru/api/v1"

# 1. Регистрация
TOKEN=$(curl -s -X POST $API/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "analyst@example.com",
    "password": "SecurePass123!"
  }' | jq -r '.access_token')

echo "✓ Зарегистрирован: $TOKEN"

# 2. Сохранить API-ключ OpenRouter
curl -s -X POST $API/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openrouter",
    "api_key": "sk-or-v1-..."
  }' | jq '.'

echo "✓ API-ключ сохранён"

# 3. Создать прогноз
PREDICTION=$(curl -s -X POST $API/predictions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "outlet": "ТАСС",
    "target_date": "2026-04-15",
    "preset": "full"
  }')

PRED_ID=$(echo $PREDICTION | jq -r '.id')
echo "✓ Прогноз создан: $PRED_ID"

# 4. Отслеживать прогресс в реальном времени
echo "Отслеживаю прогресс..."
curl -s -X GET $API/predictions/$PRED_ID/stream \
  -H "Authorization: Bearer $TOKEN" | \
  grep -o '"event":"[^"]*"' | \
  while read line; do
    echo "  $line"
  done

# 5. Получить результаты
echo "Получаю результаты..."
curl -s -X GET $API/predictions/$PRED_ID \
  -H "Authorization: Bearer $TOKEN" | \
  jq '.headlines | .[0:3]'
```

### Программное использование на Python

```python
import httpx
import json
from datetime import date, timedelta

API = "https://delphi.antopkin.ru/api/v1"

# Создать HTTP-клиент с авторизацией
def create_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {token}"}
    )

# Создать прогноз
def predict(client: httpx.Client, outlet: str, target_date: date) -> str:
    resp = client.post("/predictions", json={
        "outlet": outlet,
        "target_date": target_date.isoformat(),
        "preset": "full"
    })
    resp.raise_for_status()
    return resp.json()["id"]

# Подписаться на обновления
def stream_progress(client: httpx.Client, pred_id: str):
    with client.stream("GET", f"/predictions/{pred_id}/stream") as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                data = json.loads(line[5:])
                event_type = data.get("event", "progress")
                if event_type == "progress":
                    print(f"  {data.get('message', '')}")
                elif event_type == "completed":
                    print(f"✓ Завершено за {data.get('total_duration_ms', 0)}ms")
                    break
                elif event_type == "error":
                    print(f"✗ Ошибка: {data.get('message', '')}")
                    break

# Получить результаты
def get_results(client: httpx.Client, pred_id: str) -> dict:
    resp = client.get(f"/predictions/{pred_id}")
    resp.raise_for_status()
    return resp.json()

# Использование
token = "ваш_токен_здесь"
client = create_client(token)

target = date.today() + timedelta(days=10)
pred_id = predict(client, "ТАСС", target)
print(f"Прогноз {pred_id} создан")

stream_progress(client, pred_id)
result = get_results(client, pred_id)

for headline in result["headlines"][:3]:
    print(f"{headline['rank']}. {headline['headline_text']} ({headline['confidence']:.0%})")
```

---

## Лимиты и квоты

- **Размер запроса**: 1 MB
- **Timeout запроса**: 120 секунд
- **Параллельные прогнозы на пользователя**: без лимита
- **Прогнозы в день**: без жёсткого лимита (зависит от квоты OpenRouter)
- **Список прогнозов**: максимум 100 на странице

---

## Версионирование

API использует семантическое версионирование (SemVer). Текущая версия: **v1** (endpoint: `/api/v1`).

Планы будущих версий:

- **v2**: GraphQL поддержка, улучшенная фильтрация, webhook-события
- **v3**: Интеграции с внешними аналитическими платформами

---

## CORS и безопасность

- **CORS включён** для доменов, указанных в переменной окружения `CORS_ORIGINS`
- **CSRF-защита** активна для форм на веб-интерфейсе
- **JWT-токены** подписаны и не истекают (настраивается через `JWT_EXPIRE_DAYS`)
- **API-ключи** шифруются Fernet перед сохранением и никогда не передаются в открытом виде
- **Ownership checks** предотвращают доступ к чужим прогнозам (IDOR protection)

---

## Поддержка

Если возникли вопросы или проблемы:

1. Проверьте [документацию по архитектуре](../architecture/overview.md)
2. Посмотрите примеры запросов в секциях эндпоинтов выше
3. Напишите issue на [GitHub](https://github.com/antopkin/delphi-press)
