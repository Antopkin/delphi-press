# Metaculus & Polymarket API Integration for Delphi Press

*Research date: 2026-03-28*

---

## Executive Summary

Both Metaculus and Polymarket provide fully public REST APIs for read operations — no credentials, no API keys, no secrets to manage for data collection. Metaculus offers crowd-aggregated probability distributions on geopolitical and economic questions (median at `community_prediction.full.q2`), mappable directly to `ScheduledEvent.certainty`. Polymarket delivers real-money implied probabilities on current-week events (`float(json.loads(outcomePrices)[0])` = YES probability, no conversion required), mappable to `SignalRecord`. Rate limits are non-constraining: Polymarket allows 300 `/markets` requests per 10 seconds; Metaculus has no published hard limit. **Recommended action:** implement a `PredictionMarketCollector` that queries both APIs in parallel using `asyncio.gather`, caches results for 15–30 minutes, and feeds `ScheduledEvent[]` (Metaculus) and `SignalRecord[]` (Polymarket) into the existing Stage 1 pipeline. Estimated effort: 1–2 days, zero new infrastructure.

---

## Key Findings

### Finding 1: Both APIs are public for reads — no secrets required

**Evidence:** Metaculus `api2/questions/` returns JSON without any Authorization header, confirmed by the publicly browsable Django REST Framework interface at `metaculus.com/api2/questions/`. Polymarket's official documentation explicitly states: "No API key, no authentication, no wallet required" for market data (docs.polymarket.com/market-data/overview). The official Metaculus forecasting bot only uses `Authorization: Token {METACULUS_TOKEN}` for *writing* forecasts, not reading questions (confirmed in metac-bot/main.py source code).

**Implication:** Zero credential management overhead for the read path. No secrets in Fernet vault, no token rotation, no auth error states to handle in `AgentResult`.

### Finding 2: Metaculus community median is a single float at `community_prediction.full.q2`

**Evidence:** The official Metaculus R analysis scripts (`nikosbosse/Metaculus-data-analyses/working-with-API.R`) access `community_prediction$q2` for the median. The metac-bot codebase uses this as the reference probability for benchmark scoring. Additional percentile fields: `q1` (25th), `q3` (75th), `mean`. Field is `null` when `number_of_forecasters < 5`.

**Implication:** `q2` maps directly to `ScheduledEvent.certainty` via the `EventCertainty` enum thresholds. The interquartile range `q3 - q1` is available as a forecast uncertainty signal for downstream Delphi rounds.

### Finding 3: Polymarket `outcomePrices[0]` is the YES probability — no conversion needed

**Evidence:** Polymarket's binary market structure enforces `outcomePrices[0] + outcomePrices[1] = 1.0`. The Gamma API returns these as a JSON-stringified array: `"outcomePrices": "[\"0.65\", \"0.35\"]"`, where index 0 = YES outcome. Confirmed by official Polymarket documentation and the KuCoin/Phemex explainers. `float(json.loads(market["outcomePrices"])[0])` yields the YES probability directly.

**Implication:** Parsing is one line. Note: `outcomePrices` is a *string* containing JSON, not a native array — `json.loads()` is required before `float()`. Omitting this is the single most common integration bug.

### Finding 4: Rate limits impose no constraint on a Delphi pipeline

**Evidence:** Official Polymarket documentation (docs.polymarket.com/quickstart/introduction/rate-limits) specifies `/markets` at 300 req/10s and `/events` at 500 req/10s. A full Delphi pipeline run makes at most 50 API calls to each platform. Metaculus has no published hard limit; the official bot uses a conservative 1 req/20s bucket for write operations; public read is unthrottled in practice.

**Implication:** No rate limit management code is required beyond a courtesy `await asyncio.sleep(0.2)` between paginated page fetches. No backoff logic, no token bucket, no queue.

### Finding 5: The two platforms cover different temporal horizons and should both be used

**Evidence:** Polymarket markets typically expire within days to weeks (`endDate` is near-term). Metaculus questions span days to years but can be filtered by `resolve_time__lt` for near-term questions. Polymarket covers high-volume current events (elections, economic data releases, geopolitical turning points). Metaculus covers structural trends and lower-probability tail risks with calibrated crowd forecasts from verified forecasters.

**Implication:** Use Polymarket for "what is the market pricing for this week's event" and Metaculus for "what does the crowd believe about this structural scenario." Both feed `EventThread` significance scoring in Stage 2. Neither replaces RSS/wire news — they augment it.

---

## 1. Metaculus API Reference

### 1.1 Base URLs

| API version | Base URL | Status |
|-------------|----------|--------|
| Legacy (api2) | `https://www.metaculus.com/api2/` | Active, ReDoc documented |
| New API | `https://www.metaculus.com/api/` | Active, used by official bot |

The legacy `api2` endpoint has more community-tested client code and is recommended until the new API is fully documented. Both return equivalent question data.

### 1.2 Authentication

Read operations: **no authentication required.**

For write operations (forecast submission): `Authorization: Token {METACULUS_TOKEN}` header. Token obtained at `https://metaculus.com/aib`.

### 1.3 Key Endpoints

**List questions:**
```
GET https://www.metaculus.com/api2/questions/
```

Parameters: `limit` (int, max 100), `offset` (int), `status` (`open`|`closed`|`resolved`|`upcoming`), `order_by` (`-activity`|`-last_prediction_time`|`resolve_time`), `project` (int), `search` (str), `resolve_time__gt` (ISO 8601), `resolve_time__lt` (ISO 8601), `forecast_type` (`binary`|`continuous`|`multiple_choice`), `include_description` (bool)

Response envelope: `{"count": 4033, "next": "...?offset=100", "previous": null, "results": [...]}`

**Get single question:**
```
GET https://www.metaculus.com/api2/questions/{id}/
```

**List posts (new API):**
```
GET https://www.metaculus.com/api/posts/?tournaments=[3672]&statuses=open&limit=100
```

### 1.4 Question Object — Key Fields

```json
{
  "id": 10003,
  "title": "Will X happen before Y?",
  "url": "https://www.metaculus.com/questions/10003/",
  "resolution_criteria": "Resolves YES if...",
  "description": "Background context...",
  "status": "open",
  "type": "binary",
  "resolve_time": "2025-06-01T00:00:00Z",
  "actual_resolve_time": null,
  "resolution": null,
  "community_prediction": {
    "full": {
      "q1": 0.12,
      "q2": 0.25,
      "q3": 0.42,
      "mean": 0.26
    }
  },
  "number_of_forecasters": 87,
  "categories": [{"id": 5, "name": "Geopolitics"}],
  "tags": [{"name": "Russia"}, {"name": "Ukraine"}]
}
```

**Community prediction fields:** `community_prediction.full.q2` = median probability (primary signal). `null` when fewer than 5 forecasters.

### 1.5 Example Request (Python httpx async)

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.get(
        "https://www.metaculus.com/api2/questions/",
        params={
            "status": "open",
            "forecast_type": "binary",
            "resolve_time__gt": date.today().isoformat(),
            "resolve_time__lt": (date.today() + timedelta(days=14)).isoformat(),
            "order_by": "-activity",
            "limit": 100,
            "include_description": "true",
        },
    )
    data = resp.json()
    questions = data["results"]
    # Iterate pages via data["next"] URL
```

### 1.6 Rate Limits

No official published limit. Practical safe rate: 120 req/min (1 req/0.5s) for batch fetches. The official Metaculus bot uses 1 req/20s for write operations as a conservative default.

---

## 2. Polymarket API Reference

### 2.1 Base URLs

| API | Base URL | Auth |
|-----|----------|------|
| Gamma (market data) | `https://gamma-api.polymarket.com` | None |
| CLOB (order book, live price) | `https://clob.polymarket.com` | None (reads) |
| Data (positions, trades) | `https://data-api.polymarket.com` | None (public) |

### 2.2 Authentication

Gamma API, CLOB read endpoints, Data API: **no authentication required.**

Trading (POST /order): EIP-712 wallet signature + HMAC-SHA256 headers via `py-clob-client` SDK. Not needed for Delphi Press.

### 2.3 Key Gamma API Endpoints

**List markets:**
```
GET https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50&order=volume_24hr
```

Parameters: `active` (bool), `closed` (bool), `limit` (int), `offset` (int), `order` (`volume_24hr`|`volume`|`liquidity`|`end_date`), `ascending` (bool), `tag_id` (int), `exclude_tag_id` (int)

Response: direct JSON array (no pagination envelope — use `offset` for paging)

**List events (grouped markets):**
```
GET https://gamma-api.polymarket.com/events?active=true&closed=false&limit=20
```

**Get category tags:**
```
GET https://gamma-api.polymarket.com/tags
```

Response: `[{"id": 1, "label": "Politics", "slug": "politics"}, ...]`

**Search:**
```
GET https://gamma-api.polymarket.com/public-search?q=ukraine
```

**CLOB live price:**
```
GET https://clob.polymarket.com/price?token_id={clobTokenIds[0]}&side=BUY
```
Response: `{"price": "0.6500"}`

**CLOB price history:**
```
GET https://clob.polymarket.com/prices-history?interval=1d&token_id={token_id}
```
Response: `{"history": [{"t": 1709000000, "p": "0.52"}, ...]}`

### 2.4 Market Object — Key Fields

```json
{
  "id": "abc123",
  "question": "Will Russia and Ukraine sign a ceasefire before June 2025?",
  "conditionId": "0x1234abcd...",
  "slug": "russia-ukraine-ceasefire",
  "category": "Politics",
  "description": "Resolves YES if...",
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

**Parsing `outcomePrices`:**
```python
import json
prices = json.loads(market["outcomePrices"])   # ["0.35", "0.65"]
yes_prob = float(prices[0])                     # 0.35
```

### 2.5 Example Request (Python httpx async)

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.get(
        "https://gamma-api.polymarket.com/markets",
        params={
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": 100,
        },
    )
    markets = resp.json()  # list directly
    
    # Filter by end date proximity and minimum liquidity
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc) + timedelta(days=30)
    markets = [
        m for m in markets
        if m.get("endDate") and datetime.fromisoformat(m["endDate"].replace("Z", "+00:00")) <= cutoff
        and float(m.get("liquidity") or 0) >= 5000
    ]
```

### 2.6 Rate Limits (Official)

| Endpoint | Limit |
|----------|-------|
| Gamma general | 4,000 req/10s |
| `/events` | 500 req/10s |
| `/markets` | 300 req/10s |
| `/public-search` | 350 req/10s |
| CLOB `/price` | 1,500 req/10s |

Throttling: delayed/queued (not immediate 429). Sliding time windows.

---

## 3. Schema Mapping

### 3.1 Metaculus → `ScheduledEvent`

```python
def metaculus_to_scheduled_event(q: dict) -> ScheduledEvent | None:
    cp = q.get("community_prediction", {}) or {}
    full = cp.get("full", {}) or {}
    q2 = full.get("q2")
    if q2 is None:
        return None  # no community forecast yet
    
    certainty = (
        EventCertainty.CONFIRMED   if q2 >= 0.80 else
        EventCertainty.LIKELY      if q2 >= 0.55 else
        EventCertainty.POSSIBLE    if q2 >= 0.30 else
        EventCertainty.SPECULATIVE
    )
    
    resolve_time = q.get("resolve_time")
    event_date = datetime.fromisoformat(resolve_time.replace("Z", "+00:00")).date() if resolve_time else date.today()
    
    cats = [c["name"].lower() for c in q.get("categories", [])]
    event_type = _infer_event_type(cats)  # map to EventType enum
    
    return ScheduledEvent(
        id=f"metaculus_{q['id']}",
        title=q["title"],
        description=(q.get("description") or "")[:500],
        event_date=event_date,
        event_type=event_type,
        certainty=certainty,
        source_url=q.get("url", ""),
        newsworthiness=round(min(q2 + 0.1 * math.log(max(q.get("number_of_forecasters", 1), 1)), 1.0), 3),
        potential_impact=(q.get("resolution_criteria") or "")[:300],
    )
```

**Mapping table:**

| `ScheduledEvent` | Metaculus field | Notes |
|-----------------|----------------|-------|
| `id` | `question.id` | Prefixed `metaculus_` |
| `title` | `question.title` | Direct |
| `description` | `question.description` | 500-char truncation |
| `event_date` | `question.resolve_time` | Parse ISO 8601 → `date` |
| `event_type` | `question.categories[].name` | Map to `EventType` enum |
| `certainty` | `community_prediction.full.q2` | Float → enum thresholds |
| `source_url` | `question.url` | Direct |
| `newsworthiness` | `q2` + `number_of_forecasters` | Log-weighted |
| `participants` | `question.tags[].name` | Entity-like tag names |

### 3.2 Polymarket → `SignalRecord`

```python
import json, math

def polymarket_to_signal_record(market: dict) -> SignalRecord:
    prices = json.loads(market.get("outcomePrices", '["0.5","0.5"]'))
    yes_prob = float(prices[0]) if prices else 0.5
    
    volume = float(market.get("volume") or 0)
    volume_score = min(math.log10(max(volume, 1)) / 5.0, 1.0)  # normalized: 100k USDC → 1.0
    signal_strength = abs(yes_prob - 0.5) * 2  # 0 at 50/50, 1.0 at certainty
    relevance = round(signal_strength * 0.6 + volume_score * 0.4, 3)
    
    tags = [t["label"] for t in market.get("tags", [])]
    
    return SignalRecord(
        id=f"polymarket_{market['id']}",
        title=market.get("question", ""),
        summary=(market.get("description") or "")[:1000],
        url=f"https://polymarket.com/market/{market.get('slug', market['id'])}",
        source_name="Polymarket",
        source_type=SignalSource.WEB_SEARCH,
        published_at=_parse_end_date(market.get("endDate")),
        language="en",
        categories=tags,
        entities=[],
        relevance_score=relevance,
    )
```

**Mapping table:**

| `SignalRecord` | Polymarket field | Notes |
|---------------|-----------------|-------|
| `id` | `market.id` | Prefixed `polymarket_` |
| `title` | `market.question` | Direct |
| `summary` | `market.description` | 1000-char truncation |
| `url` | `market.slug` | Build Polymarket URL |
| `source_name` | — | Constant `"Polymarket"` |
| `source_type` | — | `SignalSource.WEB_SEARCH` |
| `published_at` | `market.endDate` | Temporal anchor |
| `categories` | `market.tags[].label` | Direct list |
| `relevance_score` | `outcomePrices[0]` + `volume` | Formula above |

---

## 4. Implementation Recommendations

### 4.1 New collector file

**Path:** `src/agents/collectors/prediction_market_collector.py`

The collector runs in parallel with existing Stage 1 agents (`NewsScout`, `EventCalendar`, `OutletHistorian`). It outputs both `ScheduledEvent[]` and `SignalRecord[]` in a single `AgentResult.data` dict.

### 4.2 Fetch strategy

```
1. On each pipeline run, fetch Metaculus (open binary questions, resolve within 14 days)
2. On each pipeline run, fetch Polymarket (active markets, end within 30 days, volume > 10k USDC)
3. Run both fetches concurrently via asyncio.gather
4. Apply quality filters (min forecasters, min liquidity)
5. Convert to ScheduledEvent[] + SignalRecord[]
6. Cache results for 30 min (Metaculus) / 15 min (Polymarket)
```

### 4.3 Caching

Use a module-level `TTLCache` (simple dict + monotonic timestamp). Key: `(platform, query_hash)`. Do not use Redis for this — pipeline runs are short-lived and in-process caching is sufficient.

### 4.4 Keyword filtering

Neither API supports server-side keyword filtering on question title. Fetch the top 100 questions by activity/volume, then filter client-side:

```python
def matches_topic(title: str, keywords: list[str]) -> bool:
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in keywords)
```

### 4.5 `SignalSource` enum extension

Add `PREDICTION_MARKET = "prediction_market"` to `SignalSource` in `src/schemas/events.py`. This allows downstream Stage 2 analysts to identify and weight prediction market signals separately from RSS/wire signals.

### 4.6 Error handling

Wrap each platform fetch in `try/except`. If Metaculus fails, return partial result with Polymarket data only (and vice versa). The collector should never block the pipeline — return `AgentResult(success=True, data={"events": [], "signals": []})` as minimum viable empty result.

---

## 5. Limitations

- **Rate limits (Metaculus):** Not officially documented. Treat as 120 req/min safe ceiling. [UNVERIFIED precise limit — no official source found]
- **Metaculus `api2/` deprecation timeline:** Unknown. Migration to `/api/posts/` is forward-compatible but not documented in full.
- **Polymarket `outcomePrices` format:** The JSON-stringified string format (rather than native array) is a known friction point. If Polymarket normalizes this in a future API version, parsing code must be updated.
- **Geographic coverage:** Both platforms are English-language, US/EU-centric. Russian, Chinese, and Middle Eastern events are underrepresented. Coverage gap is significant for Russian-language media pipeline targets.
- **Topic coverage on Polymarket:** Highly concentrated in US politics, finance, and crypto. World affairs coverage is thinner.
- **Probability calibration:** Polymarket prices reflect trader sentiment + capital allocation, not pure calibration. Metaculus community predictions are better calibrated for long-horizon questions. Neither should be used as sole certainty signal.
- **Research scope:** Kalshi API (US-regulated, strong on economic events) was not researched in depth. Consider as Sprint 2 addition (see `foresight_centers.md`).

---

## Sources

1. [Metaculus API Documentation](https://www.metaculus.com/api/)
2. [Metaculus API ReDoc Schema](https://www.metaculus.com/api2/schema/redoc/)
3. [Metaculus API Launch Announcement](https://www.metaculus.com/questions/15141/officially-launching-the-metaculus-api/)
4. [metac-bot main.py (official Metaculus bot)](https://github.com/Metaculus/metac-bot/blob/d5df71c12ab031fbbf66bd54f770be2bc00fb912/main.py)
5. [Metaculus data analyses R scripts](https://github.com/nikosbosse/Metaculus-data-analyses/blob/main/working-with-API.R)
6. [Metaculus forecasting-tools (official Python library)](https://github.com/Metaculus/forecasting-tools)
7. [Polymarket API Rate Limits (official)](https://docs.polymarket.com/quickstart/introduction/rate-limits)
8. [Polymarket Fetch Markets Guide](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)
9. [Polymarket Market Data Overview](https://docs.polymarket.com/market-data/overview)
10. [Polymarket API Architecture (Medium, 2025)](https://medium.com/@gwrx2005/the-polymarket-api-architecture-endpoints-and-use-cases-f1d88fa6c1bf)
11. [Polymarket Developer Guide (Hypereal, 2026)](https://hypereal.cloud/a/polymarket-api)
12. [Polymarket Binary Market Structure Explained](https://phemex.com/news/article/understanding-polymarkets-binary-outcome-structure-yes-no-1-52038)
13. [Polymarket API Endpoints Reference](https://docs.polymarket.com/quickstart/reference/endpoints)
14. [Best Prediction Market APIs Comparison](https://newyorkcityservers.com/blog/best-prediction-market-apis)
15. [Chainstack Polymarket API Guide](https://chainstack.com/polymarket-api-for-developers/)

---