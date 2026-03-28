# 11 — Implementation Roadmap

> Статус на 2026-03-29. Production deployed. Обновлено: 2026-03-29 (v0.5.1 foresight bugfix).

---

## Текущее состояние: Production deployed

Все 18 агентов реализованы. **Production deploy** на `delphi.antopkin.ru` (4 Docker-контейнера, TLS). Polymarket enrichment (4 фазы): distribution metrics, CLOB API, Judge 6-я персона "market". Frontend: auth UI, settings, мои прогнозы, пресеты (Light/Standard/Full). **835 тестов** зелёные. Hardening (retry, SSRF, cron, monitoring) завершён. Foresight bugfix v0.5.1: Metaculus API migration, cache key fix, CLOB param fix.

### Реализованные компоненты

| Компонент | Агенты/модули | Статус | Тесты |
|-----------|--------------|--------|-------|
| **Stage 1: Collection** | NewsScout, EventCalendar, OutletHistorian, ForesightCollector | DONE | 104 теста |
| **Stage 2: Event Identification** | EventTrendAnalyzer (TF-IDF + HDBSCAN + LLM) | DONE | Есть |
| **Stage 3: Trajectory Analysis** | GeopoliticalAnalyst, EconomicAnalyst, MediaAnalyst (parallel) | DONE | Есть |
| **Stage 4: Delphi R1** | 5 персон (Realist, Geostrateg, Economist, MediaExpert, DevilsAdvocate) | DONE | 247 строк |
| **Stage 5: Mediator + R2** | Mediator, затем 5 персон повторно (двухфазный `_run_delphi_r2()`) | DONE | 214 строк |
| **Stage 6: Consensus** | Judge (агрегация, калибровка, top 7 + wildcards) | DONE | 199 строк |
| **Stage 7: Framing** | FramingAnalyzer | DONE | Есть |
| **Stage 8: Generation** | StyleReplicator | DONE | Есть |
| **Stage 9: Quality Gate** | QualityGate (алгоритмический, без LLM) | DONE | Есть |
| **LLM Layer** | OpenRouterClient, ModelRouter (40+ task mappings), BudgetTracker | DONE | Есть |
| **Orchestrator** | 9 стадий, SSE progress, fail-soft, `_run_delphi_r2()` | DONE | 475 строк |
| **Schemas** | 60+ Pydantic-моделей в 7 файлах | DONE | Контрактные тесты |
| **Prompts** | 21 prompt-класс для всех агентов | DONE | — |
| **API** | JWT auth, predictions CRUD, outlets, health, API keys | DONE | Есть |
| **Frontend** | Auth (login/register/logout), settings (API keys), index (мои прогнозы, пресеты), progress (SSE), results, about | DONE | 29 тестов |
| **Data Sources** | RSS, web search, scraper, foresight (Metaculus/Polymarket/GDELT) | DONE | 104 теста |
| **Evaluation (пилот)** | Brier Score + bootstrap CI, Log Score, Composite Score, Wayback CDX | DONE | 18 тестов |
| **Agent Registry** | 18 агентов зарегистрированы в `build_default_registry()` | DONE | Есть |
| **E2E Testing** | MockLLMClient + 25 fixture factories + 7 integration tests | DONE | 7 тестов |
| **Dry-Run Script** | `scripts/dry_run.py` — standalone, no Redis/DB/Docker | DONE | — |

### Единственный известный stub

| Файл | Что | Причина | Влияние |
|------|-----|---------|---------|
| `src/llm/providers.py:172-192` | YandexGPTClient | Ожидает yandex-cloud-ml-sdk | Нулевое — OpenRouter fallback полностью функционален |

### Ключевые файлы пайплайна

```
src/agents/orchestrator.py          — координация 9 стадий
src/agents/forecasters/personas.py  — 5 персон с execute()
src/agents/forecasters/mediator.py  — медиация + анонимизация
src/agents/forecasters/judge.py     — агрегация + калибровка
src/agents/registry.py              — 18 агентов, build_default_registry()
src/schemas/pipeline.py             — PipelineContext со всеми слотами
src/llm/router.py                   — 28 task-to-model mappings (DEFAULT_ASSIGNMENTS)
scripts/dry_run.py                  — standalone E2E dry run (cheap model, no infra)
tests/fixtures/mock_llm.py          — MockLLMClient (task-based dispatch)
tests/fixtures/llm_responses.py     — 25+ JSON fixture factories
tests/test_integration/             — 7 E2E integration tests
```

---

## Оставшиеся сессии

### Сессия 1: First Real Prediction

**Цель:** Запустить полный 9-стадийный пайплайн на реальных данных и получить заголовки.

#### Выполнено: E2E Dry Run (2026-03-28)

- [x] Mock E2E тест (7 integration tests, MockLLMClient, 708 total green)
- [x] Live dry run: gemini-2.5-flash, 5 threads, 9/9 стадий, $0.24, 6 мин
- [x] Fix 10 integration-багов (task names, dict/object, foresight APIs, schema validation)
- [x] Relax Pydantic constraints (17 string max_length, DisputeArea.spread, ScenarioType+wildcard)

#### Осталось: баги из dry run

| # | Задача | Файлы | Критерий |
|---|--------|-------|----------|
| 1.1 | ~~Fix: `_build_response` не извлекает headline text~~ | `src/schemas/pipeline.py`, `src/agents/orchestrator.py` | **DONE** — falsy check `[] or dict` + rank preservation |
| 1.2 | ~~Fix: Foresight APIs (Polymarket 422, GDELT parse error, Metaculus 403)~~ | `src/data_sources/foresight.py` | **DONE** — Polymarket camelCase fix, GDELT HTML guard + null articles (987260c). Metaculus: migrated `/api2/questions/` → `/api/posts/` (v0.5.1), optional Token auth, fail-soft без токена |
| 1.3 | ~~Refactor: унифицировать `ScenarioType` enum~~ | `src/schemas/events.py` | **DONE** — единый enum: BASELINE/OPTIMISTIC/PESSIMISTIC/BLACK_SWAN/WILDCARD |
| 1.4 | ~~Docs: написать architectural overview~~ | `docs/architecture.md` | **DONE** — 251 строка, 7 секций, tables-first |

#### Осталось: первый прогноз на Opus

| # | Задача | Критерий |
|---|--------|----------|
| 1.5 | Запустить dry run с Opus (20 threads, production config) | `status=completed`, 7+ headlines |
| 1.6 | Замерить стоимость и время | Записать: $X, Y минут |
| 1.7 | Запустить через API (dev-сервер + worker + Redis) | SSE progress + результат в БД |

**Ожидаемая стоимость:** ~$5-15 за один full prediction (5 персон x 2 раунда x Opus 4.6).

---

### Сессия 2: Hardening

**Цель:** Устранить оставшиеся дефекты в data layer перед production.

| # | Задача | Файлы | Спека | Критерий готовности |
|---|--------|-------|-------|---------------------|
| 2.1 | ~~Retry 429/5xx в web search + scraper~~ | `src/utils/retry.py`, `src/data_sources/web_search.py`, `src/data_sources/scraper.py` | `docs/01-data-sources.md` | **DONE** — exponential backoff, Retry-After header, 4 теста |
| 2.2 | ~~SSRF protection~~ | `src/utils/url_validator.py`, `src/data_sources/scraper.py` | OWASP SSRF | **DONE** — private IP blocklist, DNS resolution check, 9 тестов |
| 2.3 | ~~ARQ cron: scrape_pending_articles~~ | `src/worker.py`, `src/data_sources/scraper.py` | `docs/01-data-sources.md` | **DONE** — каждые 2 часа, batch 20, extract_text_from_url, 2 теста |
| 2.4 | ~~Мониторинг feeds~~ | `src/api/health.py`, `src/worker.py` | `docs/01-data-sources.md` | **DONE** — `/health/feeds` endpoint, Redis hash per-feed, 2 теста |

**Зависимости:** Сессия 1 (убедиться что пайплайн работает).

**Тесты:**
- `test_web_search_retry_429` — mock HTTP 429 с exponential backoff, retry succeeds
- `test_web_search_retry_5xx` — mock HTTP 500, retry up to 3 times
- `test_ssrf_private_ip_blocked` — `http://192.168.1.1`, `http://10.0.0.1`, `http://127.0.0.1` отклонены
- `test_ssrf_public_ip_allowed` — `https://example.com` разрешён

---

### Polymarket Enrichment: DONE (2026-03-28)

**Цель:** Обогатить Polymarket-сигналы distribution metrics и внедрить рыночную персону в Judge.

- [x] Phase 1: `src/data_sources/market_metrics.py` — volatility, trend, spread, CI, lw_probability (37 тестов)
- [x] Phase 2: CLOB API в PolymarketClient — `fetch_price_history()`, `fetch_enriched_markets()` (8 тестов)
- [x] Phase 3: ForesightCollector enrichment — distribution metrics из price history (2 теста)
- [x] Phase 4: Judge 6-я персона "market" — fuzzy matching, dynamic weight, alignment boost (13 тестов)

**Итого:** 60 новых тестов. 4 коммита на main.

---

### Сессия 3: Evaluation — завершить модуль

**Цель:** Довести evaluation-модуль до возможности запуска пилотного ретро-теста.

> Спека: `tasks/research/retrospective_testing.md`

| # | Задача | Файлы | Зависимости | Критерий готовности |
|---|--------|-------|-------------|---------------------|
| 3.1 | BERTScore evaluator | `src/eval/bertscore_eval.py` | `bert-score>=0.3.13` (+ torch ~2GB) | Тест: 2 заголовка, F1 score в диапазоне [0, 1] |
| 3.2 | LLM-as-judge (StyleMatch) | `src/eval/style_judge.py` | OpenRouter ключ | Тест: mock LLM, score 1-5 нормализован в /5 |
| 3.3 | TopicMatch (3-ступенчатый) | `src/eval/topic_match.py` | 3.1 | Тест: keyword-screening, BERTScore, LLM fallback |
| 3.4 | Runner (оркестратор оценки) | `src/eval/runner.py` | 3.1, 3.2, 3.3 | `run_eval(prediction, ground_truth)` возвращает `EvalResult` |
| 3.5 | Report generator | `src/eval/report.py` | 3.4 | Reliability diagram PNG + per-persona BS таблица |
| 3.6 | Пилот (50 runs) | — | 3.4, сессия 1 | BS < 0.20, BSS > 0.20 (цель v1.0) |

**Модели BERTScore:**
- RU: `DeepPavlov/rubert-base-cased`
- EN: `roberta-large`
- Cross-lingual: `xlm-roberta-base`

**Новые зависимости для `pyproject.toml`:**
```toml
[project.optional-dependencies]
evaluation = [
    "bert-score>=0.3.13",
    "matplotlib>=3.9",
]
```

**Стоимость пилота:** < $1 (BERTScore локально, ~350 LLM-judge вызовов через Sonnet).

---

### Сессия 4: Frontend — DONE (2026-03-28)

**Цель:** Пользователь может ввести свои API-ключи и видеть только свои прогнозы.

> Спека: `docs/09-frontend.md`

| # | Задача | Файлы | Критерий готовности |
|---|--------|-------|---------------------|
| 4.0 | ~~Auth UI (login/register/logout)~~ | `src/web/router.py`, `src/web/templates/login.html`, `register.html` | **DONE** — JWT в HttpOnly cookie, cookie fallback в `get_current_user` |
| 4.1 | ~~UI для API-ключей~~ | `src/web/templates/settings.html`, `src/web/static/js/settings.js` | **DONE** — add/delete/validate через fetch, Fernet encryption |
| 4.2 | ~~Фильтр "Мои прогнозы"~~ | `src/web/router.py`, `src/web/templates/index.html` | **DONE** — `PredictionRepository.get_by_user()`, guest prompt |
| 4.3 | ~~Пресеты (Light/Standard/Full)~~ | `src/config.py`, `src/web/templates/index.html`, `src/api/predictions.py` | **DONE** — `PresetConfig` dataclass, `ModelRouter.with_model_override()`, R2 skip для 1-round |

**Backend для пресетов:** `PresetConfig` в `src/config.py`, `with_model_override()` в `src/llm/router.py`, preset-aware orchestrator + worker + 3 агента (event_trend, judge, quality_gate).

**Коммит:** `4574c2d` feat(frontend): Session 4 — auth UI, settings, my predictions, presets (+30 тестов, 819 total).

#### Пост-деплой фиксы (уже в main)

| Коммит | Что |
|--------|-----|
| `dd500d8` | Worker `logging.basicConfig` для Docker |
| `a04b094` | `max_tokens` 4096→8192, `trajectory_analysis`→16384 |
| `d1ce04d` | `BudgetTracker._budget` attribute fix |
| `48cc4e6` | Truncated markdown JSON fence fallback в LLM parser |

---

### Сессия 5: Deploy

**Цель:** Production deployment на VPS.

> Спека: `docs/10-deployment.md`
> Сервер: `deploy@213.165.220.144`, Debian 12, Docker 29.3.1

| # | Задача | Файлы | Критерий готовности |
|---|--------|-------|---------------------|
| 5.1 | ~~Production `.env`~~ | `.env` on VPS | **DONE** — SECRET_KEY, FERNET_KEY, REDIS_PASSWORD сгенерированы, OPENROUTER_API_KEY добавлен |
| 5.2 | ~~Docker build + test~~ | `Dockerfile`, `docker-compose.yml` | **DONE** — multi-stage build, 4 контейнера healthy |
| 5.3 | ~~TLS сертификат~~ | `nginx/` | **DONE** — certbot --standalone, Let's Encrypt для `delphi.antopkin.ru` |
| 5.4 | ~~Deploy на VPS~~ | — | **DONE** — `docker compose up -d`, repo via HTTPS clone |
| 5.5 | ~~Smoke test production~~ | — | **DONE** — health: DB ok (1ms), Redis ok (0ms), frontend loads |
| 5.6 | ~~Мониторинг~~ | — | **DONE** — `/api/v1/health` endpoint, `/api/v1/health/feeds` |

**Завершено:** 2026-03-28.

---

## Backlog (после production)

| # | Задача | Приоритет | Спека |
|---|--------|-----------|-------|
| B.1 | YandexGPTClient — реализация | Средний | `docs/07-llm-layer.md` (раздел 3) |
| B.2 | Foresight Sprint 2: Kalshi, OECD | Низкий | `tasks/research/foresight_centers.md` |
| B.3 | Foresight Sprint 3: Think-tank RSS | Низкий | — |
| B.4 | Калибровка порогов BERTScore | Средний | После пилота, 20-30 аннотированных пар |
| B.5 | Platt scaling в Judge | Средний | Если Reliability > 0.05 после пилота |
| B.6 | Per-persona weight update | Средний | Если per-persona BS разброс > 0.10 |
| B.7 | UI: раздел "Внешние прогнозы" | Низкий | — |
| B.8 | Valdai Club / IMEMO RAN scrapers | Низкий | Нет API, HTML only |
| B.9 | Правовая проверка Polymarket/Metaculus licensing | Средний | До публичного деплоя |

---

## Граф зависимостей

```
Сессия 1: First Real Prediction ──── 90% DONE (Opus run pending)
    |
    +----> Сессия 2: Hardening ───── DONE
    |          |
    |          +----> Сессия 5: Deploy ── DONE
    |
    +----> Сессия 3: Evaluation ──── Core done, full eval pending
    |          |
    |          +----> Backlog: Калибровка (B.4, B.5, B.6)
    |
    +----> Сессия 4: Frontend ────── DONE
```

**Оставшийся критический путь:** 1.5-1.7 (Opus prediction) → 3 (Evaluation pilot).

**Всё остальное — backlog.**

---

*Создано: 2026-03-28. Обновлено: 2026-03-29 (v0.5.1, 835 тестов).*
