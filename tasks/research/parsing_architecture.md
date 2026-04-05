# Архитектура парсинга — рекомендации

*Ресёрч: 2026-03-28*

## Новые зависимости (только 2 пакета)

```
fastfeedparser>=0.5.7   # async-compatible RSS/Atom/RDF парсер (Kagi, 25x быстрее feedparser)
trafilatura>=1.12       # full-text extraction (F1=0.937, лучший по бенчмарку Sandia 2024)
```

## Новые таблицы БД

### `feed_sources` — состояние инкрементального фетчинга

| Поле | Тип | Назначение |
|------|-----|------------|
| url | str UNIQUE | URL фида |
| outlet_name | str | Привязка к СМИ |
| priority | str | "high" / "standard" / "outlet" |
| etag | str? | Последний ETag от сервера |
| last_modified | str? | Последний Last-Modified |
| last_body_hash | str? | SHA-256 тела фида |
| consecutive_errors | int | Для circuit-breaker |
| is_active | bool | Вкл/выкл |

### `raw_articles` — спарсенные статьи

| Поле | Тип | Назначение |
|------|-----|------------|
| url_hash | str UNIQUE | SHA-256(normalized_url) — dedup key |
| url | str | Оригинальный URL |
| source_name | str | "Reuters", "ТАСС" |
| title | str | Заголовок |
| summary | str | RSS description / первые 500 символов |
| cleaned_text | str? | trafilatura output (NULL если не скрейпили) |
| published_at | datetime? | Дата публикации |
| fetched_at | datetime | Когда ингестировали |
| language | str | ISO 639-1 |
| categories | JSON | Теги из RSS |
| content_hash | str? | SHA-256(cleaned_text) — detect updates |
| source_type | str | "rss" / "scraper" / "wire" |

**Retention**: 30 дней (ARQ cron daily cleanup).

## Scheduling (ARQ cron)

```python
cron_jobs = [
    cron(fetch_rss_high_priority, minute={0, 15, 30, 45}),   # wire: каждые 15 мин
    cron(fetch_rss_standard, minute=5),                        # global: каждый час
    cron(fetch_rss_outlet_feeds, minute={10, 40}),            # outlet-specific: 30 мин
    cron(scrape_pending_articles, hour={0,2,4,...,22}, minute=20),  # backfill: 2 часа
    cron(cleanup_old_articles, hour=3, minute=0),              # retention: daily 03:00
]
```

## Data flow

```
RSS Feeds ──► httpx GET (ETag/304) ──► fastfeedparser ──► INSERT OR IGNORE raw_articles
                                                                    │
Web Search (Exa/Jina) ──► SearchResult ──► INSERT OR IGNORE ───────┤
                                                                    │
Article scraper (on-demand) ──► httpx GET ──► trafilatura ──────────┤
                                                                    ▼
                                                          raw_articles table
                                                                    │
                                                     SELECT WHERE published_at >= -7d
                                                                    ▼
                                                     NewsScout → SignalRecord[]
                                                                    ▼
                                                     Delphi forecast pipeline
```

## Фазы реализации

1. **Core** — migration (feed_sources + raw_articles), outlet_catalog.py, rss_fetcher.py
2. **Scheduling** — ARQ cron jobs, retention cleanup
3. **Full-text** — article_scraper.py с trafilatura + thread pool
4. **Hardening** — per-domain semaphores, circuit breaker, monitoring

## Ключевые решения
- **fastfeedparser** (не feedparser) — async-совместимый, 25x быстрее
- **trafilatura** (не newspaper3k) — F1=0.937 vs 0.912, лучше с русским
- **Не хранить raw HTML** — только cleaned_text (экономия 10x по объёму)
- **3-уровневая дедупликация**: HTTP 304 → url_hash UNIQUE → content_hash
- **ARQ cron** (не APScheduler) — уже в стеке, zero new infrastructure
