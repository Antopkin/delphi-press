# Changelog

Все значимые изменения в проекте Delphi Press.

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [0.8.0] - 2026-03-29

### Added
- **OutletResolver**: динамическая резолюция СМИ через Wikidata SPARQL + RSS autodiscovery
  - `wikidata_client.py`: SPARQL-клиент для Wikidata (name → website + language + country)
  - `feed_discovery.py`: двухпроходная RSS-автоподборка (HTML link tags → path probing)
  - `outlet_resolver.py`: 3-layer resolver (catalog → DB cache 30d → Wikidata + RSS)
  - Drop-in replacement для OutletsCatalog — реализует `OutletCatalogProto`
  - Worker pre-resolves outlet перед pipeline (обогащает неизвестные СМИ)
  - API autocomplete: combined search (static catalog 20 + DB dynamic)
  - `POST /predictions`: новые поля `outlet_resolved`, `outlet_language`, `outlet_url` в ответе
  - Frontend: "Издание не найдено" hint + 2s warning при unresolved outlet
- Telegram @Antopkin в футере сайта и README

### Fixed
- **Cache-busting (M26)**: все статические ассеты (CSS, JS, favicon) получили `?v=0.8.0` query param. nginx: убран `immutable` из `Cache-Control`. При деплое новой версии браузеры сразу загружают свежие файлы.

### Metrics
- Тесты: 1096 → 1105
- Security audit: 40/40 findings closed

---

## [0.7.1] - 2026-03-29

Security audit + bugfixes + code quality. Полное ревью кодовой базы (10 параллельных агентов, 214 файлов) выявило 80+ находок. Закрыто 40/40 (M26 cache-busting перенесён в v0.8.0).

**Почему:** Production deploy (v0.7.0) содержал захардкоженные dev-секреты в дефолтах конфигурации, отсутствие CSRF-защиты, IDOR на прогнозах, блокирующий DNS в async-контексте, race condition в бюджет-трекере и рассинхронизацию анонимизации в медиаторе Дельфи. Все critical/high security и correctness issues закрыты перед следующим деплоем.

### Security (12 исправлений)

- **Hardcoded secrets** — Fernet key и JWT secret_key больше не работают в production (`DELPHI_PRODUCTION=1` env). Fail-fast при старте с dev-дефолтами.
- **CORS** — дефолт `["*"]` → `["http://localhost:8000"]`; wildcard запрещён в production.
- **CSRF** — Double Submit Cookie middleware (`src/security/csrf.py`). Hidden field `csrf_token` во всех POST-формах (login, register, logout, prediction). JSON API exempt.
- **IDOR** — `GET /predictions/{id}` и web-маршруты проверяют ownership (`prediction.user_id == user.id`). Анонимные predictions доступны всем.
- **Rate limiting** — nginx zone `auth:5r/m` для `/login`, `/register`, `/api/v1/auth/*`.
- **`is_active` check** — деактивированный пользователь отклоняется в `get_current_user`.
- **Health info leak** — `/health` возвращает `"unavailable"` вместо `str(exc)`.
- **CSP header** — `Content-Security-Policy` в `nginx/security-headers.conf` (include-паттерн для location inheritance).
- **HSTS** — `includeSubDomains; preload` добавлен.
- **Cookie secure** — `secure=True` в non-debug mode.
- **Open redirect** — `_safe_redirect_url()` валидирует `next` (только relative paths).
- **JWT `jti`** — UUID claim для будущей token revocation.

### Fixed (7 багов)

- **Mediator anonymization** — единый `_build_label_map()` гарантирует consistent Expert A/B/C между `_anonymize_assessments` и `_build_positions`. Ранее: shuffle без seed давал разные метки → противоречивая R2 обратная связь.
- **BudgetTracker race condition** — `check_budget()` теперь под `async with self._lock` (TOCTOU fix).
- **Worker HTTP leak** — закрытие всех 6 HTTP-клиентов (scraper, metaculus, polymarket, gdelt, web_search, rss) после pipeline.
- **Scraper timezone** — `astimezone(UTC)` вместо `replace(tzinfo=UTC)` для tz-aware datetime (ошибка до 12ч).
- **Judge init(None)** — logger и tracking attributes инициализируются даже без LLM-клиента.
- **Blocking DNS** — `validate_url_safe_async()` через `asyncio.to_thread` (не блокирует event loop).
- **ground_truth window** — `datetime.combine()` для корректного `window_hours < 24`.

### Changed (13 улучшений)

- **Async bcrypt** — `hash_password_async` / `verify_password_async` через `asyncio.to_thread`. Callers обновлены.
- **Model-specific pricing** — бюджет-оценка использует `calculate_cost()` из `pricing.py` вместо flat $0.02/1K.
- **Truncated response warning** — `finish_reason="length"` логируется как WARNING.
- **Parallel framing** — `asyncio.gather` в FramingAnalyzer (5-7x speedup, было 35-45с).
- **GDELT rate limiter** — `asyncio.Lock` предотвращает concurrent bypass 1 req/sec.
- **Worker config** — `max_jobs` / `job_timeout` из Settings, не hardcoded.
- **Worker retry** — `max_tries=2` (было 1).
- **Cache eviction** — bounded cache (200 items) в MetaculusClient, PolymarketClient, GdeltDocClient.
- **Password max_length** — `max_length=128` на RegisterRequest (bcrypt truncates at 72).
- **PII masking** — email маскируется в логах (`j***@example.com`), DB URL — `hide_password=True`.
- **Stop words** — убран `stop_words="english"` из TfidfVectorizer (бесполезен для русских СМИ).
- **`aggregate_position`** — public API (убран `_` prefix), callers обновлены.
- **PipelineContext typing** — `list[Any]` → `list[dict[str, Any]]` для 16 слотов.
- **Logout** — POST вместо GET (защита от prefetch/img abuse).

### Metrics

- Тесты: **1044 → 1080** (+36 новых)
- Коммиты: ~40
- Закрыто: 12 CRITICAL+HIGH security, 7 bugs, 13 medium, 7 infra+perf = **39/40**
- Отложено: M26 (cache busting) — см. roadmap

---

## [0.7.0] - 2026-03-29

Архитектурный рефактор: двухуровневые предсказания (event-level timeline) + horizon-aware промпты.

**Почему:** Judge смешивал event aggregation и headline scoring в одном шаге. Event-level predictions терялись, блокируя market eval (E.1). Промпты не адаптировались к горизонту прогноза — одни инструкции для 1 дня и 7 дней, что противоречит литературе (Tetlock/GJP, AIA Forecaster, Scalable Delphi).

### Added

- **`src/schemas/timeline.py`** (NEW) — `HorizonBand` (immediate/near/medium), `TimelineEntry` (event-level prediction с temporal fields), `PredictedTimeline` (промежуточный артефакт Judge 6a), `compute_horizon_band()`.
- **PredictionItem**: +4 Optional поля — `predicted_date`, `uncertainty_days`, `causal_dependencies`, `confidence_interval_95` (Barrett et al., RAND 2025). Backward-compatible через defaults.
- **PipelineContext**: `predicted_timeline` slot + dedicated merge branch для Judge (два ключа: `ranked_predictions` + `predicted_timeline`).
- **Horizon-aware промпты персон** (английский, 3 bands):
  - IMMEDIATE (1-2d): operational mode, overestimation warning, signals-first evidence priority
  - NEAR (3-4d): mixed mode, scope sensitivity check, Devil's Advocate circuit breaker hunt
  - MEDIUM (5-7d): structural mode, anti-hedge-to-0.5 warning, base rates first
  - Per-band probability constraints: [0.05,0.95] / [0.06,0.94] / [0.07,0.93]
  - Temporal output format: `predicted_date`, `uncertainty_days`, `confidence_interval_95`
- **Horizon-aware промпт медиатора**: scheduled events audit (immediate), equal weight (near), news decay check (medium).
- **Horizon-weighted persona weights в Judge**: Media Expert/Economist↑ (immediate), Devil's Advocate↑ (near), Realist/Geostrateg↑ (medium). Источник: arXiv 2511.18394, Tetlock/GJP.
- **Media saturation propagation**: threads с saturation > 0.6 получают warning в промптах персон (guard against definition drift, arXiv 2511.18394).
- 56 новых тестов, итого **958/958** зелёных.

### Changed

- **Judge** (`src/agents/forecasters/judge.py`) — execute() разделён на два шага:
  - `_aggregate_timeline()` → `PredictedTimeline` (deterministic, no LLM)
  - `_select_headlines(timeline)` → `RankedPrediction[]` (temporal proximity factor)
- **Judge**: удалён неиспользуемый LLM-вызов (строки 217-232 старого кода — response дискардился, только cost tracking). Экономия $0.005-0.02/run.
- **Judge**: fix conditional `super().__init__` (partial init для unit tests).
- **Judge**: extracted `_parse_assessments()`, `_aggregate_date()`, `_aggregate_causal_deps()`.
- **RankedPrediction output contract**: сохранён без изменений → Stages 7-9 не затронуты.

### Доказательная база (14 источников)

| Источник | Влияние |
|----------|---------|
| AIA Forecaster (arXiv 2511.07678) | Anti-hedge инструкция для medium band |
| Halawi et al. (NeurIPS 2024) | Scratchpad protocol |
| arXiv 2511.18394 | Evidence priority по горизонту, saturation propagation |
| Scalable Delphi (RAND 2025) | Evidence type determines calibration |
| Tetlock/GJP | Scope sensitivity, bias stratification by horizon |
| arXiv 2410.06707 | Two-phase extraction (deferred — Step 10) |
| Boydstun et al. 2014 | Media storm cycle 7-21d |

### Deferred

- **Two-phase probability extraction** (Step 10) — opt-in feature, doubles LLM cost per Delphi round. Отложен в отдельный PR.

---

## [0.6.0] - 2026-03-29

Market-calibrated eval (Direction B) + news↔market correlation (Direction C).

### Added

- **`fetch_resolved_markets()`** в PolymarketClient — запрос resolved markets из Gamma API (`active=false&closed=true`). Resolution через `outcomePrices[0]=="1"` (поля `resolvedAt`/`resolution` не существуют в API). Timestamp: `closedTime`.
- **`fetch_historical_price()`** в PolymarketClient — цена на конкретный timestamp через `startTs/endTs` (обход бага CLOB `interval=max`, который возвращает пустой ответ для resolved markets с fidelity < 720).
- **`market_brier_comparison()`** в `src/eval/metrics.py` — сравнение BS на 3 горизонтах (T-24h, T-48h, T-7d), BSS Delphi vs Market.
- **4 Pydantic-схемы** в `src/eval/schemas.py`: `ResolvedMarket`, `BrierComparison`, `PriceMovement`, `CorrelationResult`.
- **`src/eval/correlation.py`** — `detect_sharp_movements()`, `collect_news_in_window()`, `compute_spearman_correlation()`, `compute_granger_causality()`. Granger: `statsmodels` optional dep в `[eval]` extras.
- **`src/utils/fuzzy_match.py`** — 3-tier fuzzy matching извлечён из Judge для переиспользования в eval pipeline.
- **`scripts/eval_market_calibration.py`** — standalone скрипт: BS рынка по горизонтам на resolved markets.
- **`scripts/eval_news_correlation.py`** — standalone скрипт: Spearman/Granger корреляция news↔price, генерирует markdown отчёт.
- 49 новых тестов, итого **902/902** зелёных.

### Changed

- **Judge** (`src/agents/forecasters/judge.py`) — `_match_market_to_thread()` делегирует в `fuzzy_match_to_market()` утилиту. Поведение не изменилось, регрессионные тесты зелёные.

---

## [0.5.2] - 2026-03-29

Delphi pipeline parse-error fix: personas fallback + orchestrator quorum relaxation.

### Fixed

- **Persona PromptParseError** — `parse_response()` в `personas.py:305` бросал `PromptParseError` на обрезанном JSON (дешёвые модели). Первый фикс (fallback `{}`) оказался неверным: пустой assessment попадал в judge → `PersonaAssessment.model_validate({})` → ValidationError. Финальный фикс: re-raise исключения → `BaseAgent.run()` ловит → `AgentResult(success=False)` → `merge_agent_result()` пропускает (строка 223). Judge получает только валидные assessments.

### Changed

- **Delphi quorum 4→3** — `min_successful` для DELPHI_R1 (StageDefinition) и DELPHI_R2 (hardcoded threshold) снижен с 4 до 3 (majority quorum). При 2 упавших персонах из 5 pipeline продолжает работу — медиатор синтезирует то, что есть.
- 4 новых теста, итого 853/853 зелёных.

---

## [0.5.1] - 2026-03-29

Foresight module bugfix: Metaculus API migration + cache fix + CLOB fix.

### Fixed

- **Metaculus API migration** — `/api2/questions/` (deprecated, HTTP 403) → `/api/posts/` с новым парсингом `question.aggregations.recency_weighted.latest.centers[0]`. Опциональный `Token` auth через `METACULUS_TOKEN` env var (бесплатный, metaculus.com/aib).
- **Cache key collision** — `query` параметр не входил в cache key для Metaculus и Polymarket → разные запросы возвращали кеш��рованные данные первого вызова. GDELT был корректен.
- **CLOB price history param** — `"market"` → `"token_id"` в params запроса к `clob.polymarket.com/prices-history`. Price history enrichment молча не работал.
- **Metaculus `query` игнорировался** — параметр принимался но не передавался в API. Теперь отправляется как `search`.
- **Metaculus `status` hardcoded** — параметр shadowed литералом `"open"`. Теперь forwarded как `statuses`.
- **`price_history` key отсутствовал** — при ошибке CLOB `_enrich` в `fetch_enriched_markets()` market мог остаться без `price_history` key. Добавлен default `[]` перед `gather`.

### Changed

- `number_of_forecasters` → `nr_forecasters` — новое имя поля в Metaculus API v3. Обновлено в client, collector mapping, тестах.
- `resolve_time` → `scheduled_resolve_time` — новое имя в Metaculus API.
- 14 новых тестов в `test_foresight.py`, итого 835/835 зелёных.

---

## [0.5.0] - 2026-03-28

Polymarket enrichment (4 фазы) + production deploy на VPS.

### Added

- **Distribution metrics module** (`src/data_sources/market_metrics.py`) — volatility (logit-returns), trend (EMA-delta), spread (sigmoid uncertainty), liquidity-weighted probability, empirical CI. Чистая математика, zero I/O.
- **CLOB API в PolymarketClient** — `fetch_price_history()`, `fetch_enriched_markets()`, параллельное обогащение с semaphore(10), кеш 15 мин.
- **ForesightCollector enrichment** — `_map_polymarket()` вычисляет distribution metrics из price history, добавляет volatility_7d, trend_7d, lw_probability, CI к foresight signals.
- **Judge: 6-я виртуальная персона "market"** — fuzzy matching (rapidfuzz, 3-tier), dynamic weight (liquidity × volatility × reliability), alignment boost (+0.04), longshot safeguard (<0.10).
- **60 новых тестов**, итого 789/789 зелёных.

### Milestone

- **Production deploy** на VPS `delphi.antopkin.ru` (213.165.220.144).
- 4 Docker-контейнера: app (FastAPI/uvicorn), worker (ARQ), redis 7.4, nginx (TLS).
- TLS через Let's Encrypt, security headers, rate limiting.
- Health endpoint: DB ok (1ms), Redis ok (0ms).

---

## [0.4.0] - 2026-03-28

Первый E2E dry run pipeline. 10 integration-багов найдено и пофикшено. 9/9 стадий пройдены (gemini-2.5-flash, 5 threads, $0.24, 6 мин).

### Added

- **E2E mock test suite** — 7 integration-тестов: full pipeline, context verification, progress events, partial failure, schema contract (`tests/test_integration/`)
- **MockLLMClient** — Protocol-based drop-in для ModelRouter с task-based dispatch и call logging (`tests/fixtures/mock_llm.py`)
- **25+ JSON fixture factories** — валидные ответы для всех LLM-задач pipeline (`tests/fixtures/llm_responses.py`)
- **Dry-run script** — standalone E2E без Redis/DB/Docker, cheap model override, progress bar, cost report (`scripts/dry_run.py`)
- `style_generation_ru` в DEFAULT_ASSIGNMENTS — отсутствовал, KeyError для русских СМИ
- `WILDCARD` в ScenarioType enum — LLM использует, валидация падала
- `GdeltDocClient.fetch_articles()` — Protocol-compliant wrapper вокруг `search_articles()`

### Fixed

- **quality_gate.py** — task names `"factual_check"` → `"quality_factcheck"`, `"style_check"` → `"quality_style"` (KeyError на стадии 9)
- **media_analyst.py** — `context.outlet_profile` хранится как dict (после `model_dump()`), не как `OutletProfile` (AttributeError)
- **orchestrator._build_response** — `getattr()` на dict'ах из `final_predictions` → `_get_field()` helper
- **MetaculusClient.fetch_questions** — добавлен `query: str` параметр (Protocol mismatch → TypeError)
- **PolymarketClient.fetch_markets** — добавлен `query: str` параметр (Protocol mismatch → TypeError)

### Changed

- **DisputeArea.spread** — `ge=0.15` → `ge=0.0` (LLM не контролирует числовые пороги)
- **17 string `max_length`** убрано из `events.py` (LLM не контролирует длину символов) — `SignalRecord`, `ScheduledEvent`, `EventThread`, `Scenario`, `EventTrajectory`, `CrossImpactEntry`, `GeopoliticalAssessment`, `EconomicAssessment`, `MediaAssessment`
- Тесты: 701 → 708 (7 новых E2E)

## [0.3.1] - 2026-03-27

Раунд 2 evidence-based prompt improvements. Ревизия research-материалов выявила пропущенные высокоценные компоненты.

### Added

- **Calibration Check** (все 5 персон) — pre-output sanity check для extreme values (Halawi et al. 2024, NeurIPS)
- **Update Trigger** (все 5 персон) — поле `update_trigger` в predictions[], pre-commitment к фальсифицируемости (Mellers et al. 2014, scaffold component 5/5)
- **Base rate principle** для economist (принцип 0) и geostrateg (усиление шага 3) — Mellers et al. 2014: +6–11% Brier
- **CWM upgrade path** в dev notes judge.md — документация перехода к Contribution-Weighted Model (Budescu & Chen, 2015, +28%)
- **Entman 4-function framing** для media-expert — операционализация framing theory (Entman, 1993)

### Не добавлено (с обоснованием)

- Full 5-step scaffold для всех персон — гомогенизирует domain frameworks; cherry-pick компонентов лучше
- Narrative framing prohibition — текущие промпты не используют narrative framing
- CI fields в PersonaAssessment — schema change без LLM-валидации
- IQR в mediator output — все позиции уже показаны для 5 агентов
- KAC как отдельная секция — `key_assumptions` уже required в output

## [0.3.0] - 2026-03-27

Систематический обзор академической литературы по методам форсайтинга. Evidence-based улучшение промптов.

### Added

**Академическое исследование: 80+ источников по 13 темам** (`research/`)

Методология: параллельные research-агенты (13 агентов) с cross-verification через arXiv, Google Scholar, SSRN, Semantic Scholar, Polymarket data.

| Тема | Статей | Ключевые авторы |
|---|---|---|
| Classical Delphi & variants | 6 | Dalkey 1963, Rowe & Wright 1999/2001/2005, Turoff 1975, Gordon 2006 |
| LLM-based forecasting | 8 | Halawi 2024, Schoenegger 2024, AIA 2024, Lorenz 2025, Nel 2025 |
| Superforecasting | 3 | Tetlock 2005, Mellers 2014/2015 |
| Prediction markets | 4 | Arrow 2008, Atanasov 2017/2024, Reichenbach 2025 |
| Scenario planning | 2 | Schoemaker 1993, Gordon & Hayward 1968 |
| Calibration & aggregation | 6 | Brier 1950, Baron 2014, Satopää 2014, Gneiting 2007, Budescu 2015, Guo 2017 |
| Multi-agent AI | 5 | Du 2024, Liang 2024, Wang 2024, Chan 2024, Qian 2025 |
| Political forecasting | 1 | Ye 2024 (Mirai) |
| Cognitive biases & debiasing | 18 src | Lou 2024, Cheung 2025, Malmqvist 2024 |
| Prompt engineering for forecasting | 18 src | Lu 2025, Sacilotto 2025, Xiong 2024 |
| Intelligence analysis (SATs) | 22 src | CIA Tradecraft 2009, Heuer & Pherson 2019, Klein 1989 |
| Media framing & news prediction | 12 src | Entman 1993, Boydstun 2014, Soroka 2015, Tohidi 2025 |
| Wisdom of crowds theory | 13 src | Galton 1907, Condorcet 1785, Page 2007, Kim 2025 |

**Артефакты исследования:**
- 34 индивидуальных конспекта (MD, по шаблону: метаданные → findings → applicability → BibTeX)
- 4 литобзора (~3000–4000 слов каждый): Delphi evolution, LLM forecasting SOTA, Calibration & aggregation, Multi-agent AI
- 5 тематических сводок: cognitive biases, prompt engineering, intelligence SATs, media framing, wisdom of crowds
- `prompt-modification-map.md` — маппинг всех findings → конкретные изменения в 7 промптах
- `README.md` — сводная таблица + кросс-тематический синтез

**Ключевые findings (LLM-validated):**

| Finding | Источник | LLM-validated? | Expected impact |
|---|---|---|---|
| Extremization α=√3≈1.73 | AIA Forecaster 2024 (Brier 0.1076) | Да | Superforecaster parity |
| Anti-rounding (no multiples of 5/10) | Schoenegger 2024 (12 LLM) | Да | Reduces acquiescence bias |
| Factual questions > statistics in mediator | Lorenz & Fritz 2025 (r=0.87–0.95) | Да | Genuine deliberation |
| DoT guard (no "reconsider") | Liang 2024 (EMNLP) | Да (LLM-specific) | Prevents degeneration |
| Anti-sycophancy Independence Guard | Malmqvist 2024 (bandwagon 0.524) | Да (LLM-specific) | Preserves R2 diversity |
| Long-horizon penalty >14d | Ye 2024 (GPT-4o on GDELT) | Да | Honest uncertainty |
| Longshot bias: sub-10% = 14% actual | Reichenbach 2025 (Polymarket) | Да (market data) | Wild cards warranted |
| Narrative framing = prohibited | Lu 2025 (12 models, 464 questions) | Да | Prevent calibration collapse |
| Superforecasting scaffold | Mellers 2014 + Lu 2025 | Частично | +6–41% Brier |
| CWM > Brier weighting (+28%) | Budescu & Chen 2015 | Нет (humans) | Upgrade path |

### Changed

- `docs/prompts/judge.md` — extremization α 1.5→1.73; temporal decay; long-horizon penalty; CWM upgrade path
- `docs/prompts/mediator.md` — DoT guard; minority protection; reasoning chains; DeLLMphi+Lorenz citations
- `docs/prompts/realist.md` — explicit Tetlock citation with empirical numbers; fox-style instruction
- `docs/prompts/geostrateg.md` — Red Team adversary frame; superforecasting scaffold
- `docs/prompts/economist.md` — superforecasting scaffold; anti-rounding
- `docs/prompts/media-expert.md` — Boydstun saturation thresholds; task-split newsworthiness vs event probability
- `docs/prompts/devils-advocate.md` — longshot bias reference; retrospective premortem framing
- Все 5 персон — Brier criterion; anti-rounding; calibration check; Independence Guard для R2

---

## [0.2.0] - 2026-03-27

Архитектурное решение: два режима работы продукта.

### Added

**Два режима работы (dual mode)**

| | Web UI | Claude Code mode |
|---|---|---|
| Стоимость | ~$5-50/прогноз (ключи пользователя) | ~$0 (подписка Max) |
| Model diversity | Да (5 разных моделей) | Нет (промптовая diversity, Opus 4.6) |
| Автоматизация | Да (cron, API) | Нет (ручной запуск) |
| Персистентность | Да (БД, история) | Нет (markdown отчёт) |

**Web UI — пользовательские API-ключи:**
- Пользователи вводят свои ключи OpenRouter / YandexGPT
- Fernet-шифрование at rest (cryptography)
- JWT-авторизация (PyJWT + bcrypt)
- Три пресета: Light ($5-10), Standard ($15-25), Full ($30-50)
- Обновлены спеки: `docs/07-llm-layer.md` (§12), `docs/08-api-backend.md` (§12)

**Claude Code mode — skill `/predict`:**
- Пользователь клонирует репо, запускает Claude Code
- Skill оркестрирует через субагентов (5 персон параллельно)
- Основная сессия = медиатор + судья
- Opus 4.6 для всех вызовов, покрыто подпиской Max
- Реализация: `.claude/skills/predict/SKILL.md` (сессия 12)

**Обновлённый план: 13 сессий** (добавлена сессия 12: Claude Code predict skill)

### Changed

- `docs/07-llm-layer.md` — добавлен §12: per-request API keys, фабрика провайдеров, пресеты
- `docs/08-api-backend.md` — добавлен §12: аутентификация, User/UserAPIKey таблицы, KeyVault
- `openrouter_api_key` в config.py — из required в optional (fallback)
- План сессий: 12 → 13

---

## [0.1.0] - 2026-03-27

Инициализация проекта. Документация, инфраструктура, сервер.

### Added

**Документация (25 файлов, ~17K строк)**
- Спецификации всех 9 стадий пайплайна (`docs/00-10`)
- Промпты 7 экспертных персон (`docs/prompts/`)
- Ресёрч по best practices Claude Code (`docs/research/`)

**GitHub**
- Репозиторий: [Antopkin/delphi-press](https://github.com/Antopkin/delphi-press) (public)
- Ветка: `main`

**Claude Code инфраструктура**
- `.claude/settings.json` — проектные permissions (uv, pytest, ruff, git, docker)
- `.claude/rules/` — 4 файла правил (async, pydantic, agents-llm, testing)
- `.claude/skills/implement-module/` — скилл автономной реализации модулей
- `GLOSSARY.md` — доменный глоссарий (40+ терминов)

**Docker-конфигурация**
- `Dockerfile` — multi-stage build (python:3.12-slim + uv, non-root user)
- `docker-compose.yml` — 4 сервиса (app, worker, redis, nginx)
- `nginx/nginx.conf` — reverse proxy, SSE support, rate limiting, security headers
- `.env.example` — шаблон переменных окружения
- `scripts/deploy.sh` — скрипт быстрого деплоя на VPS

**Yandex Cloud сервер**
- VM: `delphi-press`, Debian 12, Intel Ice Lake
- Ресурсы: 4 vCPU (20%), 8 GB RAM, 40 GB SSD
- Зона: `ru-central1-b`
- IP: `213.165.220.144` (статический)
- SSH: `deploy@213.165.220.144` (ed25519)
- Security group: default (22, 80, 443 in; all out)
- Стоимость: ~3 600 ₽/мес

### Решения по инфраструктуре

| Вопрос | Решение | Альтернативы | Причина |
|---|---|---|---|
| Хостинг | Yandex Cloud VM | Hetzner, DO | Русские LLM, локализация, грант 4000 ₽ |
| ОС | Debian 12 | Ubuntu 24.04 | Выбор пользователя |
| Оркестрация | docker compose | K8s, COI, Serverless | Простота для 4 контейнеров |
| Redis | Контейнер | Managed Valkey | Экономия ~3 500 ₽/мес |
| БД | SQLite | Managed PostgreSQL | Zero-config, один writer |
| Frontend | Jinja2 + Pico.css + Vanilla JS | React, Vue | Нет build step, SSE нативно |
| Package manager | uv | pip, poetry | 10-50x быстрее, lockfile |

**Домен**
- Домен: `antopkin.ru` (reg.ru, до 27.03.2027)
- Поддомен: `delphi.antopkin.ru` → A-запись на 213.165.220.144
- DNS: ns1.reg.ru, ns2.reg.ru
- `antopkin.com` — в redemption на Njalla (истёк 22.01.2026, освободится ~12-17.04.2026)

### Аудит и фиксы (27.03.2026, вечер)

**Найденные и исправленные проблемы:**
- `/implement-module` — добавлен Шаг 0: Bootstrap (pyproject.toml, uv sync, conftest)
- `agents-llm.md` — определён LLMClient Protocol + LLMResponse с полными сигнатурами
- `settings.json` — добавлены git push, docker build/run permissions
- `testing.md` — fixture scope mock_llm изменён на `function` (предотвращение интерференции тестов)
- `GLOSSARY.md` — уточнена анонимизация медиатора (Expert A-E)

**Установленные скиллы (Matt Pocock):**
- `/triage-issue` — структурированный баг-триаж
- `/ubiquitous-language` — авто-генерация доменного глоссария из кода
- `/request-refactor-plan` — план рефакторинга с granular коммитами

**Обновлённый план: 12 сессий** (Delphi разбита на 2: персоны+медиатор, judge+калибровка)

**Исследованные, но отложенные:**
- wshobson/agents (85 агентов) — нет совместимого installer'а
- Trail of Bits skills (40+ плагинов) — нет совместимого installer'а
- agent-observability — установить после сессии 2 (LLM-слой)

### План разработки (12 сессий)

```
Сессия 1:  src/schemas/ + src/config.py + pyproject.toml
Сессия 2:  src/llm/
Сессия 3:  src/agents/base.py + registry + orchestrator
Сессия 4:  src/agents/collectors/
Сессия 5:  src/agents/analysts/
Сессия 6:  src/agents/forecasters/ (персоны + медиатор)
Сессия 7:  src/agents/forecasters/ (judge + калибровка)
Сессия 8:  src/agents/generators/
Сессия 9:  src/data_sources/
Сессия 10: src/api/ + src/db/
Сессия 11: src/web/
Сессия 12: Docker + интеграция + e2e тесты + deploy
```

### Server Hardening (27.03.2026, день)

**Полный аудит и настройка безопасности VPS:**

| Компонент | Конфигурация |
|---|---|
| SSH | Drop-in hardening: ed25519 only, AllowUsers deploy, no root, VERBOSE logging |
| fail2ban | SSH jail (systemd backend), 24h ban, recidive jail (7d) |
| Kernel (sysctl) | rp_filter, no redirects, SYN cookies, ASLR, IPv6 disabled |
| Swap | 4 GB `/swapfile`, swappiness=10 |
| NTP | ntpsec localhost only |
| Docker | CE 29.3.1, Compose plugin, hardened daemon.json (no-new-privileges, icc=false, log rotation) |
| Firewall | iptables INPUT DROP (22/80/443 allowed), DOCKER-USER chain, persisted |
| auditd | SSH, identity, Docker, sudo monitoring |
| Unattended upgrades | Active, Docker/kernel blacklisted |
| TLS | Let's Encrypt `delphi.antopkin.ru`, auto-renewal via certbot timer |

**Скрипт:** `scripts/server-hardening.sh` — 12 шагов, идемпотентный, с верификацией.

### Что осталось до деплоя

- [x] Купить домен
- [x] Настроить DNS A-запись
- [x] Аудит конфигурации + фиксы
- [x] Установить скиллы (Pocock)
- [x] Захарденить сервер (SSH, firewall, sysctl, fail2ban, auditd)
- [x] Установить Docker на сервер
- [x] Получить SSL-сертификат (Let's Encrypt)
- [ ] Зарезервировать статический IP (перед продакшном)
- [ ] Написать код (12 сессий)
- [ ] Деплой: `git clone` + `.env` + `docker compose up -d`
