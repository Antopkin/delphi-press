# RSS-фиды для Delphi Press

*Ресёрч: 2026-03-28*

## Tier-1 (обязательные, 8 источников)

| # | Источник | RSS URL | Язык | Контент |
|---|----------|---------|------|---------|
| 1 | TASS (EN) | `https://tass.com/rss/v2.xml` | EN | Summary |
| 2 | TASS (RU) | `https://tass.ru/rss/v2.xml` | RU | Summary |
| 3 | RIA Novosti | `https://ria.ru/export/rss2/index.xml` | RU | Summary |
| 4 | Interfax | `https://www.interfax.ru/rss.asp` | RU | Summary |
| 5 | Meduza | `https://meduza.io/rss/all` | RU | **Full text** |
| 6 | BBC News | `https://feeds.bbci.co.uk/news/rss.xml` | EN | Summary |
| 7 | Al Jazeera | `https://www.aljazeera.com/xml/rss/all.xml` | EN | Summary |
| 8 | The Guardian | `https://www.theguardian.com/world/rss` | EN | Summary |

## Tier-2 (желательные, 8 источников)

| # | Источник | RSS URL | Язык | Примечание |
|---|----------|---------|------|------------|
| 9 | Kommersant | `https://www.kommersant.ru/RSS/main.xml` | RU | Бизнес/экономика |
| 10 | Vedomosti | `https://www.vedomosti.ru/rss/news.xml` | RU | Финансы, ~30 рубрик |
| 11 | RBC | `https://rssexport.rbc.ru/rbcnews/news/30/full.rss` | RU | Бизнес |
| 12 | Reuters (proxy) | `https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en` | EN | Через Google News |
| 13 | AP (proxy) | `https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com&ceid=US:en` | EN | Через Google News |
| 14 | Xinhua | `http://www.xinhuanet.com/english/rss/worldrss.xml` | EN | Китай/АТР |
| 15 | BBC Russian | `https://feeds.bbci.co.uk/russian/rss.xml` | RU | Западный взгляд |
| 16 | Moscow Times | `https://www.themoscowtimes.com/rss/news` | EN | Независимый взгляд |

## Дополнительные фиды по категориям

### BBC
- World: `https://feeds.bbci.co.uk/news/world/rss.xml`
- Business: `https://feeds.bbci.co.uk/news/business/rss.xml`
- Tech: `https://feeds.bbci.co.uk/news/technology/rss.xml`

### Vedomosti (рубрики)
- Экономика: `https://www.vedomosti.ru/rss/rubric/economics.xml`
- Политика: `https://www.vedomosti.ru/rss/rubric/politics.xml`
- Технологии: `https://www.vedomosti.ru/rss/rubric/technology.xml`

### TASS (категории EN)
- World: `https://tass.com/rss/v2.xml` (общий)
- Доступны подкатегории: Politics, Economy, Defense, Science, Sports

## Технические решения

### Библиотеки
- **fastfeedparser** (Kagi) — основной парсер, 5-50x быстрее feedparser
- **feedparser** — fallback для невалидного XML
- **httpx.AsyncClient** — HTTP (уже в стеке)
- **aiometer** — rate limiting для asyncio

### Politeness
- Полинг: 1 раз в 15 мин (tier-1), 1 раз в 30 мин (tier-2)
- Conditional GET: ETag + Last-Modified
- User-Agent: `DelphiPress/1.0 (+https://delphi.antopkin.ru/about)`
- Max 2 параллельных запроса к одному домену
- Exponential backoff при 429/5xx

### Дедупликация (3 ступени)
1. URL-хэш (sha256) — точные дубли
2. MinHash на заголовке (Jaccard > 0.7) — переформулировки
3. Embedding similarity — только в Stage 2 (EventTrendAnalyzer)

## Ограничения
- Reuters/AP: Google News proxy не гарантирует полноту
- Xinhua: URL может быть нестабильным
- NYT: paywall, не включён
- Vedomosti/Kommersant: часть статей за paywall
