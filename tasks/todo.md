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

| Стадия | Статус | Что готово |
|--------|--------|-----------|
| **Stage 1: Collection** | DONE | 4 коллектора, cron jobs, 16 RSS, Metaculus/Polymarket/GDELT |
| **Stage 2: Event Identification** | DONE | EventTrendAnalyzer (TF-IDF + HDBSCAN + LLM) |
| **Stage 3: Trajectory Analysis** | DONE | 3 аналитика (geo, econ, media) — parallel |
| **Stage 4: Delphi R1** | **STUB** | 5 персон определены, `execute()` пустой |
| **Stage 5: Mediator + R2** | **90%** | Mediator DONE; R2 = повторный вызов персон с feedback |
| **Stage 6: Judge** | DONE | Агрегация, калибровка, ранкинг top 7 + wildcards |
| **Stage 7: Framing** | DONE | FramingAnalyzer — editorial angles |
| **Stage 8: Generation** | DONE | StyleReplicator — headline + lede variants |
| **Stage 9: Quality Gate** | DONE | Fact-check + style conformance + dedup |
| **LLM Layer** | DONE | OpenRouter client, ModelRouter (40+ task mappings), BudgetTracker |
| **Orchestrator** | DONE | 9 стадий, SSE progress, fail-soft (min_successful) |
| **Schemas** | DONE | 60+ моделей в 7 файлах |
| **Prompts** | DONE | 14 файлов промптов для всех агентов |
| **API + Backend** | DONE | JWT auth, predictions API, worker |
| **Frontend** | Частично | Главная, about, progress, results — работают |
| **Eval** | Пилот | Brier Score + ground truth; BERTScore, runner — TODO |
| **Deploy** | Отложен | Сервер захарденен, Docker готов |

**Вывод:** Единственный блокер для запуска end-to-end пайплайна — `ExpertPersona.execute()` (1 файл, ~50 строк).

---

## Что делать дальше (по приоритету)

### Сессия 1: Запуск пайплайна end-to-end 🔴 КРИТИЧЕСКИЙ ПУТЬ

**Цель:** Реализовать `ExpertPersona.execute()` → пайплайн работает от Stage 1 до Stage 9.

- [ ] **1.1** Реализовать `ExpertPersona.execute()` — `src/agents/forecasters/personas.py:~200`
  - Загрузить system prompt персоны (уже определён в модуле)
  - Branch: `mediator_feedback is None` → R1; иначе → R2 (добавить feedback в user prompt)
  - LLM вызов: `self.llm.complete(task=f"delphi_r{round}_{self.task_prefix}", messages=[...], json_mode=True)`
  - Парсинг ответа → `PersonaAssessment` (из `src/schemas/agent.py`)
  - `self.track_llm_usage(...)`
  - ~50 строк кода

- [ ] **1.2** Архитектурное решение: R2 после медиатора
  - Сейчас: `DELPHI_R2 = ["mediator"]` → после него сразу Judge
  - Нужно: Mediator → 5 персон R2 (с feedback) → Judge
  - Варианты: (a) добавить stage DELPHI_R2_PERSONAS; (b) mediator внутренне запускает R2; (c) расширить delphi.py как composite agent
  - Решение повлияет на `ProgressStage` enum + orchestrator.py

- [ ] **1.3** Реализовать `delphi.py` — оркестрация R1→Mediator→R2 (или скорректировать Orchestrator)
  - `src/agents/forecasters/delphi.py` — сейчас только dataclasses
  - Нужно: `DelphiOrchestrator` или новые stage definitions

- [ ] **1.4** Тесты персон (mock LLM)
  - `test_persona_r1_returns_assessment` — mock LLM → PersonaAssessment
  - `test_persona_r2_includes_mediator_feedback` — feedback передаётся в prompt
  - `test_delphi_full_flow` — R1 → Mediator → R2 → Judge (integration)

- [ ] **1.5** E2E smoke test — запустить полный пайплайн через API с mock LLM
  - `PredictionRequest` → 9 стадий → `PredictionResponse`

### Сессия 2: Hardening + первый реальный прогноз

- [ ] **2.1** Retry 429/5xx в web search (`src/data_sources/web_search.py`)
- [ ] **2.2** SSRF protection — валидация URL на приватные IP
- [ ] **2.3** Первый реальный прогноз (с OpenRouter ключом)
  - ТАСС RU, target_date = завтра
  - Проверить: все 9 стадий, стоимость, время выполнения
- [ ] **2.4** ARQ cron: `scrape_pending_articles` каждые 2 часа

### Сессия 3: Eval — завершить модуль

- [ ] **3.1** BERTScore eval: `src/eval/bertscore_eval.py` — кешированный scorer
  - Зависимость: `bert-score>=0.3.13` + torch (~2GB)
  - RU: `DeepPavlov/rubert-base-cased`; EN: `roberta-large`; cross: `xlm-roberta-base`
- [ ] **3.2** LLM-as-judge: StyleMatch через Claude Sonnet
  - Отдельный промпт от генерации (избежать self-enhancement bias)
- [ ] **3.3** Runner: `src/eval/runner.py` — оркестратор: ground truth → BERTScore → TopicMatch → BS
- [ ] **3.4** Report: `src/eval/report.py` — reliability diagram + per-persona BS таблица
- [ ] **3.5** Пилот: 50 runs × 3 горизонта × 3 издания (< $1)

### Сессия 4: Frontend

- [ ] **4.1** UI для API-ключей — поля ввода OpenRouter/YandexGPT (бэкенд готов: Fernet)
- [ ] **4.2** "Последние прогнозы" — фильтр по текущему пользователю
- [ ] **4.3** Редизайн фронтенда

### Сессия 5: Deploy

- [ ] **5.1** Деплой на `deploy@213.165.220.144`
  - `.env` с OpenRouter ключом
  - Docker Compose: app + worker + redis + nginx
  - TLS via Let's Encrypt
- [ ] **5.2** Мониторинг: Redis pub/sub для feed fetch events

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
