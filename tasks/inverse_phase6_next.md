# Inverse Problem Phase 6: Data API Live Enrichment

> Промпт для следующей сессии Claude Code.
> Контекст: Phase 5 (v0.9.3) завершена — 1243+ тестов, conditionId fix, BSS variants, bootstrap CI.

---

## Контекст: что уже сделано

### Phase 5 (v0.9.3)
- **conditionId fix**: enrichment теперь использует правильный join key (CTF hex hash, не Gamma internal id)
- **BSS baseline**: +0.196 mean, 95% CI [+0.094, +0.297], p=2.38e-07, 22/22 folds
- **BSS variants**: --volume-gate, --adaptive-extremize, --timing-weight, --all-variants (single-pass)
- **Bootstrap CI**: paired fold + block bootstrap + sign test
- **Cron**: weekly refresh_profiles.sh (Sunday 03:00 UTC)
- **Server**: INVERSE_PROFILES_PATH в .env, swap 4GB, cron настроен

### Что НЕ работает
- Enrichment в production pipeline **не срабатывает для текущих рынков**: профили загружены, но `inverse_trades` пуст для live Polymarket markets. Trades из HuggingFace — исторические, не совпадают с активными рынками.

---

## Задача: Data API Live Enrichment

### Ключевое открытие (из Phase 5 research)

Polymarket Data API (`data-api.polymarket.com`) — **публичный, без аутентификации**:

```
GET https://data-api.polymarket.com/trades?market={conditionId}&takerOnly=false&limit=10000
```

- Rate limit: 200 req/10 сек
- Ответ: `proxyWallet`, `side` (BUY/SELL), `conditionId`, `size`, `price`, `timestamp`
- `proxyWallet` = те же адреса что `maker`/`taker` в HuggingFace → матчатся с профилями

### Архитектура интеграции

```
Pipeline run → ForesightCollector → fetch_enriched_markets() → Gamma API
    ↓
Для каждого matching market с condition_id:
    ↓
NEW: fetch trades via Data API → list[TradeRecord]
    ↓
compute_informed_signal(trades, profiles, raw_prob, market_id)
    ↓
Judge получает informed_probability
```

### Два варианта реализации

**Вариант A: On-demand fetch (простой)**
- В `_map_polymarket()`: для каждого рынка с condition_id → fetch trades из Data API
- Плюс: свежие данные, простая реализация
- Минус: добавляет latency к pipeline (~1-2 сек на рынок × 20-30 рынков = 30-60 сек)

**Вариант B: Pre-fetch batch (быстрее)**
- Новый метод `fetch_market_trades(condition_ids: list[str])` на PolymarketClient
- Параллельный fetch через asyncio.gather() с semaphore (10 concurrent)
- Плюс: быстрее (параллельно), можно кэшировать
- Минус: чуть сложнее

### Рекомендация: Вариант B

Рынков ~20-30 на запрос. С semaphore(10) и limit=10000 на запрос → ~3 сек total.

### Что реализовать

1. **`PolymarketClient.fetch_market_trades(condition_id: str) -> list[dict]`** в `src/data_sources/foresight.py`
   - GET data-api.polymarket.com/trades?market={condition_id}&takerOnly=false&limit=10000
   - Пагинация если > 10000 trades
   - Retry с backoff (reuse retry_with_backoff)
   - Cache TTL 15 мин (как fetch_markets)

2. **`PolymarketClient.fetch_trades_batch(condition_ids: list[str]) -> dict[str, list[dict]]`**
   - asyncio.gather() с semaphore(10)
   - Возвращает dict[condition_id → list[trade_dict]]

3. **Adapter: Data API response → TradeRecord**
   - `proxyWallet` → `user_id`
   - `conditionId` → `market_id`
   - `side` BUY/SELL → YES/NO (BUY on YES token = YES)
   - `price` → `price` (already 0-1)
   - `size` → `size` (USD value)
   - `timestamp` → `timestamp` (unix → datetime)

4. **Интеграция в ForesightCollector._map_polymarket()**
   - После fetch_enriched_markets() → собрать condition_ids
   - fetch_trades_batch(condition_ids) → inverse_trades dict
   - Использовать вместо/вместе с pre-loaded inverse_trades

5. **Тесты**
   - Mock Data API response → verify TradeRecord mapping
   - Mock trades + profiles → verify enrichment fires
   - Integration: full pipeline с mock markets + mock trades

### Файлы для чтения

- `src/data_sources/foresight.py` — PolymarketClient (добавить fetch_market_trades)
- `src/agents/collectors/foresight_collector.py` — _map_polymarket (интеграция)
- `src/inverse/schemas.py` — TradeRecord (target schema)
- `src/inverse/signal.py` — compute_informed_signal (consumer)
- `src/inverse/store.py` — load_profiles (already works)
- `tasks/research/polymarket_clob_api.md` — наш research по API

### Критерии успеха

| Метрика | Порог |
|---|---|
| Data API trades fetched | > 0 trades для live markets |
| TradeRecord conversion | All fields valid, price ∈ [0,1] |
| Enrichment fires | informed_probability in foresight_signals |
| Judge uses informed signal | Evidence chain mentions informed traders |
| No pipeline slowdown | < 60 сек added latency |
| Tests | All green + new tests for Data API |

### Принципы

- TDD: failing test first
- Async everywhere (httpx)
- Graceful degradation: если Data API down → fallback на profiles-only
- Rate limit respect: semaphore(10), retry с backoff
- Не ломать существующий batch enrichment (--profiles/--trades flags)

---

## Серверные задачи (после основной работы)

1. Docker restart worker (подхватит INVERSE_PROFILES_PATH)
2. Проверить BSS variant results (results/walk_forward_*.csv)
3. Обновить docs с результатами вариантов
