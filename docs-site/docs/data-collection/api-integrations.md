# Внешние API-интеграции

Справочник по REST API, которые собирают данные для Delphi Press: предсказательные рынки, новости, события и форсайт-сигналы.

---

## Обзор платформ

| Платформа | Назначение | Авторизация | Лимит | Интеграция |
|-----------|-----------|------------|-------|-----------|
| **Metaculus** | Предсказания вероятностей (толпа) | Опциональна (чтение) | 120 req/min | `MetaculusClient` |
| **Polymarket** | Реальные цены (рынки) | Не требуется | 300 req/10s | `PolymarketClient` |
| **GDELT DOC 2.0** | Статьи (индекс) | Не требуется | ~1 req/sec | `GdeltDocClient` |
| **Polymarket CLOB** | История цен | Не требуется | 1500 req/10s | `PolymarketClient.fetch_price_history()` |
| **Polymarket Data API** | Сделки (биржа) | Не требуется | 200 req/10s | `PolymarketClient.fetch_market_trades()` |

---

## Metaculus API

Краудсорсированные вероятности геополитических и экономических вопросов.

### Эндпоинты

#### Новое API (рекомендуется)

```
GET https://www.metaculus.com/api/posts/
```

**Параметры:**
- `statuses` — `open`, `closed`, `resolved`, `upcoming`
- `forecast_type` — `binary`, `continuous`, `multiple_choice`
- `scheduled_resolve_time__gt` — ISO 8601 (начало диапазона)
- `scheduled_resolve_time__lt` — ISO 8601 (конец диапазона)
- `order_by` — `-hotness`, `-last_prediction_time`, `scheduled_resolve_time`
- `limit` — макс. 100
- `tournaments` — список ID (опционально)
- `search` — поисковой запрос (опционально)
- `with_cp` — `true` для включения вероятностей

**Пример (curl):**

```bash
curl -s "https://www.metaculus.com/api/posts/?statuses=open&forecast_type=binary&scheduled_resolve_time__gt=2026-04-05T00:00:00Z&scheduled_resolve_time__lt=2026-04-20T00:00:00Z&order_by=-hotness&limit=100&with_cp=true" | jq '.results[0]'
```

#### Legacy API (`api2/`)

```
GET https://www.metaculus.com/api2/questions/
GET https://www.metaculus.com/api2/questions/{id}/
```

Более полная документация, но планируется миграция на новое API. Параметры аналогичны.

### Структура объекта вопроса

```json
{
  "id": 10003,
  "title": "Will X happen before Y?",
  "url": "https://www.metaculus.com/questions/10003/",
  "description": "Background context...",
  "resolution_criteria": "Resolves YES if...",
  "scheduled_resolve_time": "2025-06-01T00:00:00Z",
  "question": {
    "aggregations": {
      "recency_weighted": {
        "latest": {
          "centers": [0.35],
          "interval_lower_bounds": [0.25],
          "interval_upper_bounds": [0.45]
        }
      }
    }
  },
  "nr_forecasters": 87,
  "projects": {
    "category": [{"name": "Geopolitics"}]
  }
}
```

**Ключевые поля:**
- `centers[0]` — **медиана вероятности** (q2) — основной сигнал для `ScheduledEvent.certainty`
- `interval_lower_bounds[0]` — 25-й процентиль (q1)
- `interval_upper_bounds[0]` — 75-й процентиль (q3)
- `nr_forecasters` — число участников (фильтруем если < 10)

### Авторизация

**Чтение:** не требуется.

**Запись прогнозов:** `Authorization: Token {TOKEN}` (получить на `metaculus.com/aib`).

### Лимиты и рекомендации

- **Официальный лимит:** не опубликован
- **Безопасная частота:** 120 req/min (1 req/0.5s)
- **Кэширование:** 30 минут

!!! note "Маппинг в ScheduledEvent"
    ```python
    q2 >= 0.80  → EventCertainty.CONFIRMED
    q2 >= 0.55  → EventCertainty.LIKELY
    q2 >= 0.30  → EventCertainty.POSSIBLE
    q2 <  0.30  → EventCertainty.SPECULATIVE
    ```

---

## Polymarket API

Реальные деньги на прогнозах текущих событий.

### 1. Gamma API (обнаружение рынков)

Основной API для списка активных рынков.

```
GET https://gamma-api.polymarket.com/markets
GET https://gamma-api.polymarket.com/events
GET https://gamma-api.polymarket.com/tags
GET https://gamma-api.polymarket.com/public-search
```

**Параметры `/markets`:**
- `active` — `true`, `false`
- `closed` — `true`, `false`
- `limit` — макс. 1000
- `offset` — для пагинации
- `order` — `volume_24hr`, `volume`, `liquidity`, `end_date`
- `ascending` — `true`, `false`
- `tag_id` — фильтр по категории (опционально)

**Пример (curl):**

```bash
curl -s "https://gamma-api.polymarket.com/markets?active=true&closed=false&order=volume_24hr&ascending=false&limit=50" | jq '.[0]'
```

**Структура объекта рынка:**

```json
{
  "id": "abc123",
  "question": "Will Russia and Ukraine sign a ceasefire before June 2025?",
  "slug": "russia-ukraine-ceasefire",
  "description": "Resolves YES if...",
  "conditionId": "0x1234abcd...",
  "endDate": "2025-06-01T00:00:00Z",
  "active": true,
  "closed": false,
  "outcomes": "[\"Yes\", \"No\"]",
  "outcomePrices": "[\"0.35\", \"0.65\"]",
  "volume": "450000.00",
  "volume24hr": "12000.00",
  "liquidity": "85000.00",
  "clobTokenIds": "[\"yes_token_id\", \"no_token_id\"]",
  "tags": [{"id": 1, "label": "Politics"}]
}
```

**Парсинг вероятностей:**

!!! warning "Важно: JSON-строка, не массив"
    ```python
    import json
    
    prices = json.loads(market["outcomePrices"])  # Парсим JSON-строку!
    yes_probability = float(prices[0])            # Вероятность YES
    no_probability = float(prices[1])             # Вероятность NO
    ```

### 2. CLOB API (история цен)

Получение исторических цен и текущего спреда.

```
GET https://clob.polymarket.com/prices-history
GET https://clob.polymarket.com/book
GET https://clob.polymarket.com/spread
GET https://clob.polymarket.com/price
```

**Параметры `prices-history`:**
- `market` — **CLOB token ID** (из `clobTokenIds[0]` с Gamma API, не `id` рынка!)
- `interval` — `1h`, `6h`, `1d`, `1w`, `1m`, `all`, `max`
- `startTs` — Unix timestamp (альтернатива `interval`)
- `endTs` — Unix timestamp (с `startTs`)
- `fidelity` — минут на точку (по умолчанию 1)

**Пример (curl):**

```bash
curl -s "https://clob.polymarket.com/prices-history?market=token_id_here&interval=1d&fidelity=60" | jq '.history'
```

**Ответ:**

```json
{
  "history": [
    {"t": 1709000000, "p": "0.52"},
    {"t": 1709086400, "p": "0.58"},
    {"t": 1709172800, "p": "0.61"}
  ]
}
```

!!! danger "Известная ошибка CLOB API"
    Разрешённые рынки + `fidelity < 720` + `interval=max` → пустой ответ.
    
    **Обходной путь:** использовать `startTs`/`endTs` с разбиением на окна 14-15 дней.

### 3. Data API (сделки)

Получение истории всех сделок на рынке.

```
GET https://data-api.polymarket.com/trades
```

**Параметры:**
- `market` — `conditionId` (из Gamma API, не обычный `id`!)
- `limit` — макс. 10000
- `takerOnly` — `true`, `false`

**Структура ответа:**

```json
[
  {
    "proxyWallet": "0x...",
    "side": "BUY",
    "conditionId": "0x...",
    "size": "100.00",
    "price": "0.52",
    "timestamp": 1709000000,
    "outcome": "YES",
    "outcomeIndex": 0
  }
]
```

### Лимиты Polymarket

| Эндпоинт | Лимит |
|----------|-------|
| `/markets`, `/events` | 300–500 req/10s |
| `/public-search` | 350 req/10s |
| `/prices-history` | 1000 req/10s |
| `/price`, `/spread`, `/book` | 1500 req/10s |
| Data API `/trades` | 200 req/10s |

Дросселирование мягкое (задержки, не 429).

!!! note "Маппинг в SignalRecord"
    ```python
    relevance_score = signal_strength * 0.6 + volume_score * 0.4
    # где:
    # signal_strength = abs(yes_prob - 0.5) * 2  (0 при 50/50, 1 при уверенности)
    # volume_score = min(log10(volume) / 5, 1.0)  (нормировано на 100k USDC)
    ```

---

## GDELT DOC 2.0 API

Полнотекстовый индекс новостей мира (15-минутное обновление).

### Эндпоинт

```
GET https://api.gdeltproject.org/api/v2/doc/doc
```

Без авторизации. HTTPS поддерживается.

### Основные параметры

| Параметр | Значения | По умолчанию |
|----------|----------|------------|
| `query` | Строка, операторы `"phrase"`, `OR`, `-negation` | — |
| `mode` | `artlist`, `timelinevol`, `timelinetone`, `timelinelang`, `timelinesourcecountry` | `artlist` |
| `format` | `json`, `csv`, `rss`, `jsonfeed` | HTML |
| `maxrecords` | 1–250 | 75 |
| `timespan` | `15min`, `1h`, `24h`, `7d`, `1m`, `3m` | 3 мес |
| `sort` | `datedesc`, `dateasc`, `tonedesc`, `hybridrel` | datedesc |

**Пример (curl):**

```bash
curl -s "https://api.gdeltproject.org/api/v2/doc/doc?query=ukraine%20war&mode=artlist&format=json&maxrecords=50&timespan=24h&sort=hybridrel" | jq '.articles[0]'
```

### Продвинутые операторы

```
theme:ECON_CENTRAL_BANK       # Фильтр по теме GKG
sourcelang:russian            # Язык статьи (англ. название)
sourcecountry:RS              # Страна источника (FIPS 2-буквы)
domain:reuters.com            # Домен издания
tone<-5                       # Тон < -5 (негативный)
toneabs>10                    # Высокая эмоциональность
near10:"interest rate"        # Слова в 10 словах друг от друга
repeat3:"sanctions"           # Слово повторяется 3+ раза
```

**Полный список тем GKG:** `http://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT`

Примеры для Delphi Press:
- `ECON_CENTRAL_BANK` — центральные банки
- `MILITARY_CONFLICT` — военные конфликты
- `GOV_ELECTIONS` — выборы
- `NATURAL_DISASTER` — стихийные бедствия
- `DIPLOMATIC_RELATIONS` — дипломатия

### Структура JSON-ответа (artlist)

```json
{
  "articles": [
    {
      "url": "https://example.com/article",
      "title": "Headline text",
      "seendate": "20260328T143000Z",
      "domain": "example.com",
      "language": "English",
      "sourcecountry": "US",
      "socialimage": "https://example.com/img.jpg"
    }
  ]
}
```

**Важно:**
- `language` — англоязычное имя (`English`, `Russian`), не ISO код
- `sourcecountry` — FIPS (US, RS, UA, GB), не ISO 3166

### Маппинг на SignalRecord

```python
# Парсим дату "20260328T143000Z"
published_at = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)

# Нормализуем язык: English → en, Russian → ru
language_map = {
    "english": "en", "russian": "ru", "german": "de",
    "french": "fr", "spanish": "es", "chinese": "zh",
}
language = language_map.get(language.lower(), "en")

signal = SignalRecord(
    id=f"gdelt_{hash(url + title)}",
    title=title,
    summary="",  # DOC API не возвращает текст
    url=url,
    source_name=domain,
    source_type=SignalSource.WEB_SEARCH,
    published_at=published_at,
    language=language,
    relevance_score=0.6,  # базовый балл
)
```

### Лимиты и кэширование

- **Лимит:** ~1 req/sec (не опубликовано официально, основано на сообщениях сообщества)
- **Кэширование:** 15 минут (GDELT обновляется каждые 15 минут)
- **Защита:** экспоненциальный backoff на 429

!!! danger "Киррилица не поддерживается"
    GDELT возвращает HTML вместо JSON для запросов с кириллицей. Решение: использовать `transliterate` или английские ключевые слова.

---

## GDELT Events CSV (15-минутный фид)

Структурированные события с кодами CAMEO.

### Архитектура

Три файла каждые 15 минут:
1. **Events** — уникальные события (дедублированы)
2. **Mentions** — упоминания события в статьях (many-to-one)
3. **GKG** — Global Knowledge Graph (темы, персоны, организации)

**Список файлов:** `http://data.gdeltproject.org/gdeltv2/masterfilelist.txt` (обновляется каждые 15 мин)

**Формат имени:** `YYYYMMDDHHMMSS.export.CSV.zip` (Events)

### Events CSV — ключевые поля

| Поле | Тип | Описание |
|------|-----|---------|
| `GlobalEventID` | int | Первичный ключ |
| `Day` | int | YYYYMMDD |
| `Actor1Name`, `Actor2Name` | str | Участники (страны, лица) |
| `EventCode` | str | CAMEO код (e.g., `1900`, `0411`) |
| `EventRootCode` | str | 2-значный корень (e.g., `19`, `04`) |
| `QuadClass` | int | 1=Вербальное сотрудничество, 2=Материальное сотрудничество, 3=Вербальный конфликт, 4=Материальный конфликт |
| `GoldsteinScale` | float | -10 до +10 (стабильность) |
| `AvgTone` | float | -100 до +100 (тональность) |
| `NumMentions` | int | Упоминаний в 15-мин окне |
| `ActionGeo_CountryCode` | str | Где произошло событие |
| `SOURCEURL` | str | URL первоисточника |
| `DATEADDED` | int | Временная метка обработки (YYYYMMDDHHMMSS) |

### CAMEO → EventType

```python
CAMEO_ROOT_TO_EVENT_TYPE = {
    "01": "political",    # Make Public Statement
    "02": "political",    # Appeal
    "03": "diplomatic",   # Express Intent
    "04": "diplomatic",   # Consult
    "05": "diplomatic",   # Diplomatic Cooperation
    "06": "diplomatic",   # Material Cooperation
    "07": "political",    # Provide Aid
    "13": "military",     # Threaten
    "14": "military",     # Protest
    "15": "military",     # Exhibit Force
    "17": "social",       # Coerce
    "18": "military",     # Assault
    "19": "military",     # Fight
    "20": "military",     # Mass Violence
}
```

### Маппинг на ScheduledEvent

```python
def gdelt_event_to_scheduled(row: dict) -> ScheduledEvent | None:
    num_mentions = int(row.get("NumMentions", 0))
    goldstein = float(row.get("GoldsteinScale", 0))
    
    # Фильтруем малозначительные события
    if num_mentions < 5:
        return None
    
    # Расчёт новостности
    mention_score = min(num_mentions / 500, 1.0)
    conflict_score = abs(goldstein) / 10.0
    newsworthiness = mention_score * 0.7 + conflict_score * 0.3
    
    event_date = datetime.strptime(row["Day"], "%Y%m%d").date()
    event_type = CAMEO_ROOT_TO_EVENT_TYPE.get(row["EventRootCode"], "other")
    
    return ScheduledEvent(
        id=f"evt_{row['GlobalEventID']}",
        title=f"{row['Actor1Name']} vs {row['Actor2Name']}",
        event_date=event_date,
        event_type=EventType(event_type),
        certainty=EventCertainty.CONFIRMED if goldstein < -3 else EventCertainty.LIKELY,
        newsworthiness=round(newsworthiness, 3),
    )
```

---

## Web Search Providers (для NewsScout)

Две внешние платформы для обнаружения статей по ключевым словам и темам.

### Exa API

Семантический поиск по индексу новостей и веб-контента (через embedding).

**Использование:** как основной источник в `NewsScout` для поиска статей по темам.

**Требует:** API ключ.

### Jina API

Получение полного текста статьи по URL (`jina.ai/reader`).

**Использование:** обогащение `SignalRecord.summary` при необходимости.

**Требует:** API ключ (бесплатный для базового использования).

---

## Общие паттерны интеграции

### Таймауты

```python
import httpx

async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(url)
```

Все запросы к внешним API должны иметь явный таймаут (30 сек стандартно).

### Повторы с backoff

```python
from src.utils.retry import retry_with_backoff

response = await retry_with_backoff(
    lambda: client.get(url),
    max_retries=2,
    base_delay=1.0,
)
```

Экспоненциальный backoff при `429`, `502`, `503`.

### Кэширование

```python
import time

class APIClient:
    def __init__(self):
        self._cache = {}  # {key: (timestamp, data)}
        self._cache_ttl = 900  # 15 мин
    
    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.monotonic() - ts < self._cache_ttl:
                return data
        return None
    
    def _set_cached(self, key: str, data: Any) -> None:
        self._cache[key] = (time.monotonic(), data)
```

**TTL по платформам:**
- Metaculus: 30 мин (вероятности обновляются редко)
- Polymarket: 15 мин (цены волатильны)
- GDELT: 15 мин (индекс обновляется каждые 15 мин)

### Обработка ошибок

```python
try:
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
except httpx.HTTPStatusError as e:
    logger.error("API request failed: %s", e)
    return []  # graceful degradation
except httpx.TimeoutException:
    logger.warning("API timeout: %s", url)
    return []
except json.JSONDecodeError:
    logger.warning("Invalid JSON from API")
    return []
```

Агенты не должны бросать исключения — возвращают `AgentResult(success=False, error=...)` или пустые данные.

### User-Agent

```python
headers = {
    "User-Agent": "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)"
}
```

Все запросы должны содержать человеческий User-Agent для соблюдения Best Practices.

---

## Статус ограничений

### Metaculus (403 — ограничено)

Текущее состояние: **RESTRICTED**. Запрос на tier `BENCHMARKING` отправлен 2026-03-29.

Полная поддержка ожидается после одобрения. На данный момент используются только public endpoints для чтения.

### Polymarket (полностью доступен)

Все три API полностью функциональны без авторизации.

### GDELT (полностью доступен)

DOC 2.0 и CSV feedы полностью функциональны. BigQuery на платной основе (учитывайте при масштабировании).

---

## Рекомендации по выбору источника

- **Быстрые новости (часы):** GDELT DOC + Exa
- **Событийные сигналы (дни):** GDELT Events CSV
- **Маркет-сигналы (текущее направление):** Polymarket
- **Структурные прогнозы (недели-месяцы):** Metaculus

Рекомендуется использовать все четыре источника параллельно для комплексного сигнала.
