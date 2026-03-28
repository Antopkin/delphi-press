# Metaculus API — Диагностика и актуальный reference

## Проблема
HTTP 403 from `GET https://www.metaculus.com/api2/questions/`

## Причина

**Две причины одновременно:**

1. **Все API endpoints теперь требуют авторизацию** — включая GET (read). Изменено ~Q3-Q4 2024.
2. **`api2` deprecated** — новый canonical endpoint: `/api/posts/`

Токен: бесплатный, создаётся на `https://www.metaculus.com/aib/`

## Решение

### Изменения в MetaculusClient

**1. Конструктор**: добавить `token` и `Authorization` header
```python
def __init__(self, *, token: str = "", timeout: float = 30.0):
    headers = {"User-Agent": _USER_AGENT}
    if token:
        headers["Authorization"] = f"Token {token}"
    self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers=headers)
```

**2. Endpoint**: `/api2/questions/` → `/api/posts/`

**3. Параметры**:
- `status` → `statuses`
- `resolve_time__gt` → `scheduled_resolve_time__gt`
- `resolve_time__lt` → `scheduled_resolve_time__lt`

**4. Парсинг ответа**:
```python
# БЫЛО (api2):
cp = q.get("community_prediction", {})
q2 = cp.get("full", {}).get("q2")
forecasters = q.get("number_of_forecasters", 0)

# СТАЛО (api/posts):
question = post.get("question", {})
agg = question.get("aggregations", {})
latest = (agg.get("recency_weighted") or {}).get("latest") or {}
centers = latest.get("centers")
q2 = centers[0] if centers else None
forecasters = question.get("nr_forecasters", 0)
```

## Rate limits
- Нет опубликованного лимита
- Безопасно: 120 req/min
- `limit` параметр: max 100
- Токен бесплатный, не истекает

## Что нужно добавить
- `METACULUS_TOKEN` в `.env` / config
- Graceful degradation: если токен не задан → skip Metaculus (уже есть, просто 403 → [])
