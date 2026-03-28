# Delphi Press — TODO

> Ресёрч-материалы: `tasks/research/`
> - `rss_feeds.md` — RSS-источники и архитектура парсинга
> - `parsing_architecture.md` — дизайн-решения по парсингу
> - `foresight_centers.md` — обзор форсайт-платформ
> - `metaculus_polymarket_api.md` — **API Metaculus + Polymarket**: эндпоинты, auth, маппинг на схемы
> - `gdelt_api.md` — **GDELT DOC 2.0 + Events CSV**: операторы, CAMEO codes, rate limits
> - `retrospective_testing.md` — **Методология ретро-тестирования**: BERTScore, Brier Score, пилот <$1

## Фронтенд

- [x] **Сменить название сервиса** — "Foresighting News" → "Delphi Press" (коммит `2f64f46`)
- [x] **Добавить ссылку на GitHub** — footer с SVG octicon
- [x] **Обновить about-страницу**:
  - [x] Все 5 персон = Claude Opus 4.6
  - [x] Два режима (Web UI + Claude Code)
  - [x] Техстек обновлён
- [ ] **"Последние прогнозы"** — показывать только прогнозы текущего пользователя (сейчас глобальные)
- [ ] **UI для API-ключей** — добавить поля ввода OpenRouter/YandexGPT ключей (бэкенд готов: JWT + Fernet)
- [ ] **Редизайн фронтенда** — продумать новый дизайн

---

## Парсинг и Data Sources

> Спека: `docs/01-data-sources.md`
> Протоколы: `src/agents/collectors/protocols.py`

### Фаза 1: Core infrastructure — DONE

- [x] **1.1** Зависимости (fastfeedparser, trafilatura)
- [x] **1.2** Миграция БД: `feed_sources` (circuit breaker) + `raw_articles` (URL dedup, 30-day retention) — коммит `50741eb`
- [x] **1.3** Каталог СМИ — 20 outlets (10 tier-1, 10 tier-2)
- [x] **1.4** RSS-парсер — ETag/Last-Modified, concurrency, dedup
- [x] **1.5** Кеш профилей — Redis, TTL 7 дней
- [x] **1.6** Wiring — `collector_deps` в worker.py

### Фаза 2: Scheduling — DONE

- [x] ARQ cron jobs: wire agencies (15мин), global (1ч), per-outlet (30мин), cleanup (daily 03:00) — коммит `50741eb`
- [ ] Мониторинг: Redis pub/sub для feed fetch events

### Фаза 3: Веб-поиск и скрейпер — DONE

- [x] **3.1** Web search — Exa + Jina с fallback
- [x] **3.2** Scraper — TrafilaturaScraper (httpx + trafilatura, robots.txt, per-domain semaphore) — коммит `06550a6`
- [ ] ARQ cron: `scrape_pending_articles` каждые 2 часа (backfill cleaned_text)

### Фаза 4: Hardening

- [x] Circuit breaker — `FeedSource.error_count`, disable при 5 ошибках
- [ ] **[CRITICAL]** Token bucket fix — sleep под локом в `web_search.py` (сериализует запросы)
- [ ] **[CRITICAL]** Unbounded cache — `web_search.py` кеш растёт без ограничений
- [ ] **[BUG]** Timezone — `.replace(tzinfo=UTC)` → `.astimezone(UTC)` в `rss.py`
- [ ] Retry 429/5xx в web search (спека требует)
- [ ] SSRF protection (валидация URL на приватные IP)
- [ ] E2E тест: запустить полный пайплайн через API

---

## Форсайт-центры и внешние прогнозы

> Ресёрч: `tasks/research/metaculus_polymarket_api.md`, `tasks/research/gdelt_api.md`

### Sprint 1 — IN PROGRESS

- [ ] **MetaculusClient** — `GET /api2/questions/?status=open&forecast_type=binary` → `ScheduledEvent[]`
  - `community_prediction.full.q2` → certainty (no auth, 120 req/min)
- [ ] **PolymarketClient** — `GET gamma-api.polymarket.com/markets?active=true` → `SignalRecord[]`
  - `outcomePrices[0]` → YES probability (no auth, 300 req/10s)
- [ ] **GdeltDocClient** — `GET api.gdeltproject.org/api/v2/doc/doc?mode=artlist` → `SignalRecord[]`
  - Операторы: `theme:`, `sourcelang:`, `sourcecountry:` (no auth, ~1 req/s)
- [ ] **ForesightCollector** — Stage 1 agent, asyncio.gather 3 клиента
- [ ] Тесты для всех клиентов и коллектора

### Sprint 2

- [ ] **Kalshi** — US-regulated event markets
- [ ] **OECD Data API** — экономические прогнозы (квартальная загрузка)

### Sprint 3

- [ ] **Think-tank RSS bundle** — RAND, Chatham House, Carnegie, McKinsey

### Deferred

- [ ] Valdai Club / IMEMO RAN scrapers (нет API, HTML only)
- [ ] Правовая проверка: data display licensing для Polymarket/Metaculus
- [ ] UI: раздел "Внешние прогнозы" на сайте

---

## Тестирование

> Ресёрч: `tasks/research/retrospective_testing.md` — полная методология

- [ ] **Ретроспективное тестирование**:
  - [ ] Ground truth: Wayback CDX API по 16 RSS URLs (бесплатно, без auth)
  - [ ] Метрики: CompositeScore = 0.40×TopicMatch + 0.35×BERTScore + 0.25×StyleMatch
  - [ ] Калибровка: Brier Score < 0.20 = цель v1.0 (уровень Metaculus)
  - [ ] Пилот: 50 runs × 3 горизонта, стоимость < $1
  - [ ] Модуль: `src/eval/` (ground_truth.py, bertscore_eval.py, metrics.py, runner.py)

---

## Инфраструктура

- [ ] **Деплой на сервер** — обновить `.env` с новыми моделями, перезапустить контейнеры
- [x] **User-Agent**: `DelphiPress/1.0 (+https://delphi.antopkin.ru/about)` — в scraper и rss

---

*Обновлено: 2026-03-28*
