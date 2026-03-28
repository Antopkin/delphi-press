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
- [x] **[CRITICAL]** Token bucket fix — sleep вне lock, while-loop (коммит `512aac8`)
- [x] **[CRITICAL]** Unbounded cache — eviction expired + cap 500 entries (коммит `512aac8`)
- [x] **[BUG]** Timezone — `.astimezone(UTC)` для aware datetimes (коммит `512aac8`)
- [ ] Retry 429/5xx в web search (спека требует)
- [ ] SSRF protection (валидация URL на приватные IP)
- [ ] E2E тест: запустить полный пайплайн через API

---

## Форсайт-центры и внешние прогнозы

> Ресёрч: `tasks/research/metaculus_polymarket_api.md`, `tasks/research/gdelt_api.md`

### Sprint 1 — DONE (коммит `dd46558`)

- [x] **MetaculusClient** — `GET /api2/questions/` → crowd probabilities (no auth, 30min cache)
- [x] **PolymarketClient** — `GET gamma-api.polymarket.com/markets` → market prices (no auth, 15min cache)
- [x] **GdeltDocClient** — `GET api.gdeltproject.org/api/v2/doc/doc` → article search (no auth, 1req/s)
- [x] **ForesightCollector** — 4th Stage 1 agent, asyncio.gather 3 клиента, graceful degradation
- [x] PipelineContext: foresight_events + foresight_signals slots
- [x] 33 новых теста (14 клиенты + 19 коллектор)

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

- **Ретроспективное тестирование**:
  - [x] Ground truth: `src/eval/ground_truth.py` — Wayback CDX API fetcher (коммит `512aac8`)
  - [x] Метрики (пилот): `src/eval/metrics.py` — Brier Score + bootstrap CI, Log Score, Composite Score (коммит `512aac8`)
  - [x] Схемы: `src/eval/schemas.py` — PredictionEval, EvalResult (Pydantic v2, frozen)
  - [ ] BERTScore eval: `src/eval/bertscore_eval.py` — кешированный scorer (зависимость: bert-score + torch)
  - [ ] LLM-as-judge: StyleMatch через Claude Sonnet (отдельный промпт от генерации)
  - [ ] Runner: `src/eval/runner.py` — оркестратор пайплайна оценки
  - [ ] Report: `src/eval/report.py` — reliability diagram + сводная таблица
  - [ ] Пилот: 50 runs × 3 горизонта × 3 издания, стоимость < $1
  - [ ] Калибровка порогов BERTScore на 20-30 аннотированных примерах

---

## Инфраструктура

- [ ] **Деплой на сервер** — обновить `.env` с новыми моделями, перезапустить контейнеры
- [x] **User-Agent**: `DelphiPress/1.0 (+https://delphi.antopkin.ru/about)` — в scraper и rss

---

## Общий статус проекта

| Стадия | Статус | Что готово |
|--------|--------|-----------|
| **Stage 1: Collection** | DONE | 4 коллектора, cron jobs, 16 RSS, Metaculus/Polymarket/GDELT |
| **Stage 2: Analysis** | Спеки готовы | `docs/04-analysts.md` — EventTrendAnalyzer, CrossImpactAnalyzer |
| **Stage 3: Forecasting** | Спеки готовы | `docs/05-delphi-pipeline.md` — 5 персон, медиатор, судья |
| **Stage 4: Generation** | Спеки готовы | `docs/06-generators.md` — StyleReplicator, HeadlineGenerator |
| **LLM Layer** | Спеки готовы | `docs/07-llm-layer.md` — OpenRouter + YandexGPT |
| **API + Backend** | Частично | JWT auth, predictions API, worker — работают |
| **Frontend** | Частично | Главная, about, progress, results — работают |
| **Eval** | Пилот | Brier Score, ground truth — готовы; BERTScore, runner — TODO |
| **Deploy** | Отложен | Сервер захарденен, Docker готов; ждём полный пайплайн |

*Обновлено: 2026-03-28*
