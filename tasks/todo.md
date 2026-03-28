# Delphi Press — TODO

> Ресёрч-материалы: `tasks/research/`
> - `rss_feeds.md` — RSS-источники и архитектура парсинга
> - `parsing_architecture.md` — дизайн-решения по парсингу
> - `foresight_centers.md` — обзор форсайт-платформ
> - `metaculus_polymarket_api.md` — **API Metaculus + Polymarket**: эндпоинты, auth, маппинг на схемы
> - `gdelt_api.md` — **GDELT DOC 2.0 + Events CSV**: операторы, CAMEO codes, rate limits
> - `retrospective_testing.md` — **Методология ретро-тестирования**: BERTScore, Brier Score, пилот <$1

---

## Общий статус проекта

> Полный roadmap с зависимостями и критериями готовности: **`docs/11-roadmap.md`**

| Стадия | Статус | Что готово |
|--------|--------|-----------|
| **Stage 1: Collection** | DONE | 4 коллектора, cron jobs, 16 RSS, Metaculus/Polymarket/GDELT |
| **Stage 2: Event Identification** | DONE | EventTrendAnalyzer (TF-IDF + HDBSCAN + LLM) |
| **Stage 3: Trajectory Analysis** | DONE | 3 аналитика (geo, econ, media) — parallel |
| **Stage 4: Delphi R1** | DONE | 5 персон, `execute()` реализован (personas.py:269-310) |
| **Stage 5: Mediator + R2** | DONE | Mediator + двухфазный `_run_delphi_r2()` в orchestrator |
| **Stage 6: Judge** | DONE | Агрегация, калибровка, ранкинг top 7 + wildcards |
| **Stage 7: Framing** | DONE | FramingAnalyzer — editorial angles |
| **Stage 8: Generation** | DONE | StyleReplicator — headline + lede variants |
| **Stage 9: Quality Gate** | DONE | Fact-check + style conformance + dedup |
| **LLM Layer** | DONE | OpenRouter client, ModelRouter (40+ task mappings), BudgetTracker |
| **Orchestrator** | DONE | 9 стадий, SSE progress, fail-soft, R2 two-phase |
| **Schemas** | DONE | 60+ моделей в 7 файлах |
| **Prompts** | DONE | 21 prompt-класс для всех агентов |
| **API + Backend** | DONE | JWT auth, predictions API, worker |
| **Agent Registry** | DONE | 18 агентов зарегистрированы |
| **Frontend** | Частично | Главная, about, progress, results — работают |
| **Evaluation** | Пилот | Brier Score + ground truth; BERTScore, runner — TODO |
| **Deploy** | Отложен | Сервер захарденен, Docker готов |

**Вывод:** Пайплайн feature-complete (18/18 агентов, 9/9 стадий). Следующий шаг — первый реальный прогноз.

---

## Что делать дальше (по приоритету)

> Детали, зависимости, критерии готовности: **`docs/11-roadmap.md`**

### Сессия 1: First Real Prediction

- [ ] Настроить `.env` с OpenRouter ключом
- [ ] Запустить dev-сервер + worker + Redis
- [ ] Первый реальный прогноз (ТАСС RU, завтра)
- [ ] Замерить стоимость, время, количество LLM-вызовов

### Сессия 2: Hardening

- [ ] Retry 429/5xx в web search
- [ ] SSRF protection
- [ ] ARQ cron: `scrape_pending_articles`
- [ ] Мониторинг feeds

### Сессия 3: Evaluation — завершить модуль

- [ ] BERTScore evaluator (`src/eval/bertscore_eval.py`)
- [ ] LLM-as-judge: StyleMatch
- [ ] TopicMatch (3-ступенчатый)
- [ ] Runner (`src/eval/runner.py`)
- [ ] Report generator (`src/eval/report.py`)
- [ ] Пилот: 50 runs (< $1)

### Сессия 4: Frontend

- [ ] UI для API-ключей
- [ ] Фильтр "Мои прогнозы" по пользователю
- [ ] Пресеты (Light/Standard/Full)

### Сессия 5: Deploy

- [ ] Production `.env` + Docker build
- [ ] TLS + deploy на VPS
- [ ] Smoke test + мониторинг

---

## Выполненные разделы (архив)

<details>
<summary>Data Sources — Phases 1-4</summary>

### Фаза 1: Core infrastructure — DONE
- [x] Зависимости (fastfeedparser, trafilatura)
- [x] Миграция БД: `feed_sources` + `raw_articles` (коммит `50741eb`)
- [x] Каталог СМИ — 20 outlets
- [x] RSS-парсер — ETag/Last-Modified, concurrency, dedup
- [x] Кеш профилей — Redis, TTL 7 дней
- [x] Wiring — `collector_deps` в worker.py

### Фаза 2: Scheduling — DONE
- [x] ARQ cron jobs (коммит `50741eb`)

### Фаза 3: Веб-поиск и скрейпер — DONE
- [x] Web search — Exa + Jina с fallback
- [x] Scraper — TrafilaturaScraper (коммит `06550a6`)

### Фаза 4: Hardening — частично
- [x] Circuit breaker
- [x] Token bucket fix (коммит `512aac8`)
- [x] Unbounded cache fix (коммит `512aac8`)
- [x] Timezone fix (коммит `512aac8`)

</details>

<details>
<summary>Форсайт-центры — Sprint 1 DONE</summary>

- [x] MetaculusClient (коммит `dd46558`)
- [x] PolymarketClient
- [x] GdeltDocClient
- [x] ForesightCollector
- [x] 33 теста

</details>

<details>
<summary>Eval — пилот DONE</summary>

- [x] Ground truth: Wayback CDX API fetcher (коммит `512aac8`)
- [x] Метрики: Brier Score + bootstrap CI, Log Score, Composite Score
- [x] Схемы: PredictionEval, EvalResult

</details>

<details>
<summary>Фронтенд — DONE</summary>

- [x] Rebrand → Delphi Press (коммит `2f64f46`)
- [x] GitHub ссылка в footer
- [x] About-страница обновлена

</details>

---

## Backlog (после MVP)

- [ ] Foresight Sprint 2: Kalshi, OECD Data API
- [ ] Foresight Sprint 3: Think-tank RSS (RAND, Chatham House, Carnegie)
- [ ] Valdai Club / IMEMO RAN scrapers (HTML only)
- [ ] Правовая проверка: Polymarket/Metaculus data licensing
- [ ] UI: раздел "Внешние прогнозы"
- [ ] Калибровка порогов BERTScore на 20-30 аннотированных примерах

---

*Обновлено: 2026-03-28*
