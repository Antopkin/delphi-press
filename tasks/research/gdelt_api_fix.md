# GDELT DOC 2.0 API — Диагностика и актуальный reference

## Проблема
JSON parse error при запросе с `query="news forecast 2026-03-29 ТАСС"`.

## Причины (три одновременно)

1. **Кириллица в query** → API возвращает HTML (не JSON). GDELT ищет только по английским переводам. Для русских источников: `sourcelang:russian` + `sourcecountry:RS` (FIPS, не ISO).
2. **Будущая дата в query** → GDELT ищет только в прошлом (rolling window). Дата `2026-03-29` бессмысленна.
3. **`data.get("articles", [])` не защищает от null** → `{"articles": null}` вернёт None, TypeError при итерации.

## Решение

### 1. Проверка content-type (HTML → return [])
```python
content_type = response.headers.get("content-type", "")
if "text/html" in content_type:
    logger.warning("GDELT returned HTML instead of JSON: %s", response.text[:200])
    return []
```

### 2. Защита от null
```python
# БЫЛО:
for article in data.get("articles", []):
# СТАЛО:
for article in (data.get("articles") or []):
```

### 3. Query должен быть на английском
Вызывающий код (ForesightCollector._build_query) должен генерировать английский query.

## Актуальный формат ответа
```json
{"articles": [{"url": "...", "title": "...", "seendate": "20260328T143000Z", "domain": "tass.ru", "language": "Russian", "sourcecountry": "RS"}]}
```
Формат `seendate` (`%Y%m%dT%H%M%SZ`) — текущий парсинг корректен.

## Ограничения
- Rate limit: ~1 req/sec
- `maxrecords`: max 250 (текущий код ставит 100 — можно увеличить)
- Глубина: последние 3 месяца
- Query: только английский
