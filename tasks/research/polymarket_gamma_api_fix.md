# Polymarket Gamma API — Диагностика и актуальный reference

## Проблема

`HTTP 422 Unprocessable Entity` при запросе `GET /markets?order=volume_24hr`.

## Причина

Параметр `order=volume_24hr` (snake_case) невалиден для `/markets`. Endpoint принимает camelCase: `volume24hr`. Расхождение с `/events`, который принимает snake_case — нигде не задокументировано.

Подтверждено live-запросами (2026-03-28):
- `order=volume_24hr` → **422**
- `order=volume24hr` → **200**
- `order=volume` → **200**

## Решение

`src/data_sources/foresight.py`, строка 165:
```python
# БЫЛО:
"order": "volume_24hr",
# СТАЛО:
"order": "volume24hr",
```

## Актуальный reference

### Валидные значения `order` для `/markets`

| Значение | Описание |
|----------|----------|
| `volume24hr` | Объём торгов за 24ч |
| `volume` | Общий объём |
| `volumeNum` | То же, числовой тип |
| `liquidityNum` | Ликвидность |
| `endDate` | Дата закрытия рынка |

### Полный набор параметров

| Параметр | Тип | Пример |
|----------|-----|--------|
| `active` | bool-string | `"true"` |
| `closed` | bool-string | `"false"` |
| `limit` | int | `100` |
| `offset` | int | `0` |
| `order` | string | `"volume24hr"` (camelCase!) |
| `ascending` | bool-string | `"false"` |
| `tag_id` | int | `100381` |
| `liquidity_num_min` | float | `5000` |

### Ключевые поля Market объекта

```json
{
  "id": "abc123",
  "question": "Will X happen?",
  "slug": "will-x-happen",
  "outcomePrices": "[\"0.65\", \"0.35\"]",
  "volume24hr": "12000.00",
  "liquidity": "85000.00",
  "clobTokenIds": "[\"yes_token_id\", \"no_token_id\"]",
  "endDate": "2026-04-15T00:00:00Z"
}
```

## Rate limits

| Endpoint | Limit |
|----------|-------|
| `/markets` | 300 req/10s |
| `/events` | 500 req/10s |
| CLOB reads | 1500 req/10s |

Нет IP-блокировок, User-Agent фильтрации, региональных ограничений. Auth не требуется для reads.
