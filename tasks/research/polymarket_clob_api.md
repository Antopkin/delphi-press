# Polymarket CLOB API — Price History & Order Book Reference

*Research date: 2026-03-28*

## 1. Price History

### Endpoint
```
GET https://clob.polymarket.com/prices-history
```
No auth required.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `market` | string | **Yes** | CLOB token ID (not Gamma market id!) |
| `interval` | string | No | `1h`, `6h`, `1d`, `1w`, `1m`, `all`, `max` |
| `startTs` | int | No | Unix timestamp — alternative to interval |
| `endTs` | int | No | Unix timestamp — use with startTs |
| `fidelity` | int | No | Minutes per data point. Default: 1 |

### Response
```json
{"history": [{"t": 1709000000, "p": "0.52"}, ...]}
```
Empty market → `{"history": []}` (200, not 4xx).

### Token ID Resolution (Gamma → CLOB)
```python
clob_ids = json.loads(market["clobTokenIds"])  # JSON-stringified!
yes_token = clob_ids[0]  # YES outcome
no_token = clob_ids[1]   # NO outcome
```

### Known Bug
Resolved markets + `fidelity < 720` + `interval=max` → empty response.
Workaround: use `startTs/endTs` chunked into 14-15 day segments.

## 2. Order Book / Spread

### Book
```
GET https://clob.polymarket.com/book?token_id={id}
```
Response: `{bids: [{price, size}], asks: [{price, size}], last_trade_price, ...}`

### Spread
```
GET https://clob.polymarket.com/spread?token_id={id}
```
Response: `{"spread": "0.02"}`

## 3. Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/prices-history` | 1,000 req/10s |
| `/book` | 1,500 req/10s |
| `/price` | 1,500 req/10s |
| `/spread` | ~1,500 req/10s |

All free, no auth for reads. Throttling: delayed, not 429.

## 4. For Delphi Press

Pipeline fetches ~20-50 markets. Sequence:
1. `GET /markets` (Gamma) → get `clobTokenIds`
2. For each: `GET /prices-history?market={yes_token}&interval=1w&fidelity=60`
3. Compute: volatility (stdev of returns), trend (last-first), spread
4. Feed enriched signal to Judge
