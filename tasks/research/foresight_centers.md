# Форсайт-центры и prediction markets для Delphi Press

*Ресёрч: 2026-03-28*

## Tier 1 — Easy (REST API, no auth, JSON)

| # | Источник | API | Что даёт | Язык |
|---|----------|-----|----------|------|
| 1 | **Metaculus** | `metaculus.com/api/posts/` — REST JSON, optional Token auth | Crowd probability distributions, geopolitics/AI/bio | EN |
| 2 | **Polymarket** | `clob.polymarket.com` — REST JSON, no auth, 60 req/min | Real-time market probabilities на текущие события | EN |
| 3 | **Kalshi** | `api.elections.kalshi.com` — REST JSON, no auth | US-regulated markets: политика, экономика, климат | EN |
| 4 | **GDELT DOC 2.0** | `analysis.gdeltproject.org` — HTTP JSON, no auth | 15-мин news event stream, фильтры по теме/стране | EN |
| 5 | **OECD Data API** | `data.oecd.org/api/` — SDMX/JSON, no auth | Структурированные экономические прогнозы (GDP, инфляция) | EN |

## Tier 2 — Medium (регистрация/токен/RSS)

| # | Источник | Доступ | Примечание |
|---|----------|--------|------------|
| 6 | **ACLED** | OAuth token, REST JSON, 5K rows/page | Конфликтные события; нужна коммерческая лицензия |
| 7 | **MediaCloud** | API key, 1K calls/7 дней | Объём новостного внимания по темам |
| 8 | **Think-tank RSS** | RSS (RAND, Chatham House, Carnegie, McKinsey) | Анализы, не прогнозы; фоновый сигнал |
| 9 | **Manifold Markets** | REST JSON, 500 req/min | Более нишевые рынки; нужна коммерческая лицензия |

## Tier 3 — Hard (scraping/paywall)

| # | Источник | Почему сложно |
|---|----------|---------------|
| 10 | Valdai Club / IMEMO RAN | Нет API/RSS, только HTML; публикации раз в месяц/квартал |
| 11 | Carnegie Politika | Частично через Carnegie RSS; двуязычный контент |
| 12 | Stratfor (RANE) | Enterprise paywall |
| 13 | Good Judgment Open | Нет public API; FutureFirst — платная подписка |
| 14 | WEF / Eurasia Group | PDF only, ежегодные |

## Рекомендация

**Sprint 1**: Metaculus + Polymarket + GDELT DOC → парсить в `SignalRecord[]`
**Sprint 2**: Kalshi + OECD (квартальная загрузка)
**Sprint 3**: Think-tank RSS bundle (6-8 фидов, один парсер)
**Deferred**: Valdai/IMEMO scrapers (после стабилизации core pipeline)

## Правовые замечания
- Polymarket: data partnership с Dow Jones (янв 2026) — display agreements доступны
- Metaculus: Public Benefit Corporation — гибкость для attributive use
- ACLED: бесплатно для non-commercial; commercial license через data@acled.com
