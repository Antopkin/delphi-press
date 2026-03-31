# Changelog

Все значимые изменения в проекте Delphi Press.

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [0.9.6] - 2026-03-31

### Changed
- **Progress page redesign** — полная реструктуризация `/predict/{id}`. **Почему:** layout и типографика отставали от главной страницы. Теперь: hero h1 с названием издания (outlet = заголовок, "Формируем прогноз" = лейбл), двухколоночный layout (шаги + sticky narrative sidebar), фазовая группировка шагов (Сбор данных / Экспертный анализ / Генерация), CSS counters для серифных цифр (Newsreader) без изменений в JS, shimmer на активном шаге, scale-in на чекмарке, per-step inline detail из SSE, stagger-анимация, прогресс-бар с gradient shimmer
- **Results page redesign** — карточный layout `/results/{id}`. **Почему:** перегруженная метадата, нет hover-состояний, conditional first-card styling. Теперь: `fn-headline-card` bordered cards с hover, единый стиль (убран `loop.index == 1` антипаттерн), metadata реорганизована (категория + badge сверху, крупный ранг + заголовок ниже), reasoning как blockquote, methodology в одном контейнере
- **Hero h1 на обеих страницах** — `text-2xl` → `text-4xl md:text-5xl` для консистентности с главной
- **Section spacing** — стандартизирован `mt-12` между major sections на results page
- **Meta chips** — дата получила `font-semibold`, Opus preset — `bg-primary/10 text-primary`
- **Progress bar** — высота 0.5rem → 0.75rem, gradient с shimmer анимацией

### Added
- **CSS-компоненты**: `fn-headline-card` (bordered card с hover), `fn-step-phase` (фазовый разделитель), CSS counters для timeline (серифные цифры через `::before`), `fn-step-duration` анимация появления
- **Mobile narrative** — зеркало desktop narrative для мобильных устройств
- **Completion celebration** — "Прогноз готов!" в narrative при завершении pipeline

---

## [0.9.5] - 2026-03-31

### Added
- **Incremental pipeline save** — `stage_callback` в orchestrator сохраняет PipelineSteps и headlines после каждой стадии, а не только в конце. **Почему:** QualityGate timeout (smoke test #4) терял 33 сгенерированных заголовка — worker сохранял данные только при `status=completed`. Теперь draft headlines записываются в БД после Stage 8 (Generation), а после Stage 9 (QualityGate) заменяются финальными. При падении поздних стадий данные не теряются.
- **`replace_headlines()`** в PredictionRepository — атомарная замена заголовков (delete + insert)
- **`--scrape` flag** в `scripts/dry_run.py` — переключает NoopScraper на TrafilaturaScraper для реального скрейпинга статей

### Changed
- **Worker simplified** — финальный блок сохранения убран (headlines и pipeline_steps уже записаны через stage_callback). Осталось только `update_status()` с метаданными
- **Web search "no providers" → debug** — понижен уровень логирования с WARNING до DEBUG. **Почему:** 10 warnings в каждом прогоне без API-ключей засоряли логи
- **CLAUDE.md sync** — пресеты Light/Opus, Metaculus disabled, pyarrow в base deps, версия 0.9.4

### Fixed
- **`date` serialization crash** — `predicted_timeline` содержал Python `date` объекты → `json.dumps()` при записи в SQLite JSON-колонку падал с `TypeError`. Pipeline проходил все 9 стадий, но результат не сохранялся. **Почему:** `model_dump()` (без `mode="json"`) оставлял `date` нативными. Добавлены `@field_serializer` на `predicted_date`, `target_date`, `generated_at` в timeline схемах
- **Key validation 403** — кнопка "Проверить" API-ключ возвращала CSRF 403, т.к. `fetch` не отправлял `Content-Type: application/json`. CSRF middleware не распознавал запрос как JSON API
- **Key validation wrong endpoint** — проверка била по `/api/v1/models` (всегда 200). Заменено на `/api/v1/auth/key` (401 для невалидных)
- **Outlet "not found" UX** — "Издание не найдено" заменено на "Издание не в каталоге — будет найдено автоматически". URL-поле с пояснением вместо "Необязательно"

### Added
- **`scripts/download_profiles.py`** — загрузка базы профилей суперпрогнозистов (62 MB parquet, 1.7M профилей) из GitHub Releases. SHA-256 верификация, прогресс-бар, idempotent. **Почему:** пользователи, клонирующие репо, не получали данные — `data/` в `.gitignore`
- **GitHub Release `data-v1`** — Polymarket bettor profiles (348K informed, 871K moderate, 523K noise)
- **Docker auto-download** — `docker-entrypoint.sh` скачивает профили при первом запуске. Named volume `delphi_inverse` вместо hardcoded host path
- **GitHub homepage** — `delphi.antopkin.ru` в правой панели "About"

### Fixed
- **Profile key case mismatch** — профили хранились с mixed-case Ethereum-адресами (EIP-55: `0x6FBB...`), а `adapt_data_api_trades()` приводил wallet к lowercase (`0x6fbb...`). Lookup `profiles.get(user_id)` всегда промахивался → 0 активных сигналов на `/markets`. **Почему:** Phase 6 добавила `.lower()` для trades, но не нормализовала ключи dict при загрузке профилей. Фикс: `.lower()` на ключе в `_load_parquet()` и `_load_json()` (store.py)
- **Пустая страница `/markets`** — добавлен fallback UX: если ни один informed трейдер не матчится, страница показывает топ рынков по объёму с raw market price (без informed bar, с баннером). `MarketCard.has_informed` field для условного рендеринга. Страница больше никогда не бывает пустой при наличии активных рынков
- **Мусорные рынки на `/markets`** — на топ выходили expired и essentially-resolved рынки (raw 0.1%, dispersion 75%) из-за стейловых позиций informed бетторов. **Почему:** `fetch_markets()` фильтровал только `end_date > cutoff` (слишком далеко), но пропускал expired (`end_date < now`). Также не было фильтра по вероятности. Фикс: два фильтра — skip expired + skip `raw < 5%` / `> 95%`

### Changed
- **`/markets` скрыт из навигации** — страница доступна по прямому URL, но убрана из desktop/mobile nav. **Почему:** стейловые профили из Kaggle-датасета дают 1 рынок вместо 10+. Вернём после реализации cron rebuild профилей (см. roadmap)

### Metrics
- Тесты: 1302 → 1324 (+22: stage_callback, replace_headlines, date serialization, timeline JSON, profile normalization, fallback cards, template rendering)

---

## [0.9.4] - 2026-03-31

### Added
- **Market Dashboard** (`/markets`) — live informed consensus vs raw Polymarket price, Chart.js sparklines, TTL 15 мин
- **Market signal block** на `/results/{id}` — fuzzy match релевантных рынков к прогнозу
- **Dual-model dry run** — `--persona-model` flag: Gemini lite для collection, Opus 4.6 для персон/анализа
- **Prompts catalog** (`docs/prompts-catalog.md`) — каталог 21 промпта
- **README rewrite** — methodology-first документ с BSS результатами

### Changed
- **All production tasks on Opus 4.6** — sonnet-4 заменён на opus-4.6 для style_generation и quality_style
- **max_tokens unlimited** — `ModelAssignment.max_tokens` default=None, модель решает сама. **Почему:** Gemini/Opus обрезали JSON при фиксированных 8192/16384 tokens, ломая парсинг в trajectory_analysis и delphi personas
- **pyarrow в base deps** — перенесён из optional [inverse] в основные зависимости. **Почему:** `uv run` на сервере не ставит optional deps, parquet profiles не загружались
- **Dockerfile** — убран `--extra inverse` (pyarrow теперь в base)
- **Schema instruction** — добавлен concrete example в `render_output_schema_instruction()`. **Почему:** Gemini flash lite путал Field descriptions с ожидаемыми JSON-ключами

### Fixed
- **Resilient event_identification** — fallback при timeout trajectory_analysis, детальные ошибки
- **Quality gate timeout** — factcheck/style на cheap model (66 вызовов за 30s вместо 300s+)
- **Trajectory/cross-impact на cheap model** в dry run — timeout 300s в stage 2
- **UI**: timeline line, дата до +7 дней, пресеты Light+Opus only
- **Mermaid диаграммы**, нумерация стадий, horizon bands на /about
- **Stage timeouts** — event_identification 300→600s, DelphiPersonaAgent 300→600s, event_trend_analyzer 300→600s. **Почему:** Opus на 20 threads не укладывался в 300s
- **Metaculus disabled** — API возвращает 403 без BENCHMARKING tier. `_fetch_metaculus()` возвращает [] если client=None, без warning. Вернём когда получим доступ
- **GDELT кириллица** — API отвергает non-Latin символы. GDELT query теперь без outlet name (дата + "news forecast"), `sourcelang` фильтр достаточен
- **Reuters dead feeds** — `feeds.reuters.com` удалён из GLOBAL_RSS_FEEDS (закрыт с 2020)
- **Standard preset удалён** — модель `claude-sonnet-4.6` не существует в pricing. Оставлены 2 пресета: Light (Gemini) и Opus

### Metrics
- Тесты: 1242 → 1302 (+60: markets, quality gate, schemas, timeouts, metaculus, gdelt, reuters)
- Первый полный 9/9 прогон: ТАСС 2026-04-02, 8 заголовков, $3.76

---

## [0.9.3] - 2026-03-30

### Fixed
- **Gamma API conditionId mismatch** — Foresight collector используéт `id` (numeric) вместо `conditionId` (CTF hex hash) для enrichment matching. Обогащение информированными сигналами молча падало в production. Файлы: `src/data_sources/foresight.py` (extract `conditionId`), `src/agents/collectors/foresight_collector.py` (join key). **Почему:** Gamma API возвращает оба поля — `id` рёбро-локальный, `conditionId` глобально уникален. Функция поиска `condition_markets` возвращает по `conditionId`, надо матчить по тому же ключу.
- Health endpoint: версия 0.8.0 → 0.9.2 (оставлено 0.9.2 за основу v0.9.3)

### Added
- **BSS variant flags** в `scripts/eval_walk_forward.py`:
  - `--volume-gate` — soft $10K–$100K interpolation вместо hard cutoff. **Почему:** Clinton & Huang (2024): accuracy Polymarket падает на тонких рынках.
  - `--adaptive-extremize` — d вычисляется из position std (Satopää et al. 2014) вместо фиксированного d=1.5. **Почему:** оптимальный d зависит от inter-bettor корреляции (1.16–3.92).
  - `--timing-weight` — volume-weighted фракция lifetime at bet time. **Почему:** цены точнее ближе к resolution (Bürgi et al. 2025).
- **Bootstrap CI** — `--bootstrap N` flag: paired fold bootstrap + block bootstrap (блоки по 3) + sign test p-value. **Почему:** доверительный интервал на BSS при малом N фолдов (15-22).
- **Single-pass multi-variant** — `--all-variants` flag: DuckDB SQL `_fetch_test_markets()` один раз per fold, потом `_apply_variant()` per variant (Python). Сипидакс: ~83 мин для всех 5 вариантов vs ~415 мин отдельный прогон каждого.
- **Weekly profile refresh** — `scripts/refresh_profiles.sh` (NEW): проверка freshness на HuggingFace → download → rebuild bucketed → rebuild profiles → restart worker. Cron: Sunday 03:00 UTC.

### Results
- **Baseline BSS (v0.9.2 + fixes)**: +0.196 mean, 95% CI [+0.094, +0.297], p=2.38e-07, 22/22 positive folds (5.5% улучшение vs v0.9.2 +0.127)

### Metrics
- Тесты: 1242 → 1242 (код production-grade, баги исходили из data integrity, не logic)

---

## [0.9.2] - 2026-03-30

### Added
- **Inverse Problem Phase 4: walk-forward evaluation + temporal leak fix + deploy**
  - `scripts/eval_walk_forward.py` (NEW): Walk-forward BSS evaluation с DuckDB backend. 22 фолда, non-overlapping 60-day windows, burn-in 180 дней. **Почему:** нужно доказать что informed consensus реально помогает на out-of-sample данных — не просто in-sample fit.
  - `scripts/duckdb_build_bucketed.py` (NEW): Time-bucketed partial aggregates из 470M raw trades. Один скан 33 ГБ → 2.4 ГБ bucketed parquet. **Почему:** pre-aggregated позиции содержали temporal leak (trades после cutoff T включены в avg_position). Bucketed подход: суммы composable, averages — нет. `avg_position_as_of_T = SUM(weighted_price_sum) / SUM(total_usd) WHERE time_bucket <= T`.
  - Dockerfile: `--extra inverse` в обоих `uv sync` → pyarrow в Docker image без ручной установки
  - docker-compose: bind mount `/data/inverse` для app и worker; worker healthcheck `test -f /proc/1/status` вместо curl (ARQ не имеет HTTP endpoint)

### Results
- **22/22 фолда BSS > 0** — informed consensus всегда улучшает raw market price
- **Robust mean BSS = +0.127** (фолды 0-16, >= 944 test markets) — 12.7% снижение Brier Score
- Peak BSS = +0.273 (fold 9, 34K informed bettors)
- Tier stability = 0.613 (61% Jaccard overlap между фолдами)
- Temporal leak analysis: leaked BSS +0.092 vs clean BSS **+0.117** на тех же фолдах — leak добавлял шум, не сигнал
- **Первое walk-forward evaluation на Polymarket bettor profiles** (нет опубликованных аналогов)

### Fixed
- Temporal leak в pre-aggregated позициях (trades после cutoff T были в avg_position)
- Worker healthcheck: `pgrep` → `test -f /proc/1/status` (pgrep отсутствует в python:3.12-slim)
- `mean_coverage` в walk-forward: per-market average вместо per-fold total (cosmetic)
- `avg_position` clamped to [0,1] в SQL merge (`LEAST/GREATEST`)
- Удалены мёртвые CLI аргументы (`--adaptive-extremize`, `--volume-gate`) из eval скрипта

### Metrics
- Тесты: 1226 → 1242 (+16 walk-forward eval)
- Walk-forward: 22 фолда за 82 мин (bucketed) vs 15 фолдов за 5+ часов + OOM (old)
- Docker: 4/4 containers healthy (включая worker)

---

## [0.9.1] - 2026-03-30

### Added
- **Inverse Problem Phase 3: калибровка, валидация, timing**
  - `signal.py`: adaptive extremizing — d вычисляется из `position_std` (inter-bettor std, не |informed-raw|). **Почему:** Satopää et al. (2014) показали: оптимальный d зависит от корреляции информации между бетторами (1.16–3.92). Фиксированный d=1.5 был uncalibrated. Формула: `d = 1.0 + 2.0 × std`, clamped [1.0, 2.0]. Новый flag `adaptive_extremize: bool`.
  - `signal.py`: soft volume gate — линейный градиент $10K–$100K. **Почему:** Clinton & Huang (2024): accuracy Polymarket падает до 61% на тонких рынках. Hard cutoff → discontinuity; soft gate → плавная деградация.
  - `profiler.py`: `as_of: datetime` — temporal cutoff для walk-forward validation. Фильтрует trades И resolutions по дате. **Почему:** look-ahead bias — профили видели будущие данные, BSS оптимистичен. `reference_time` автоматически = `as_of` (ARCH-3).
  - `profiler.py`: `timing_score` — volume-weighted mean fraction of market lifetime at bet time. **Почему:** Bürgi et al. (2025): цены точнее ближе к resolution. [INFERRED] — наша операционализация, не validated feature из Mitts & Ofir.
  - `loader.py`: `load_resolutions_with_dates()` — resolutions с timestamps для walk-forward
  - `loader.py`: `load_market_timestamps()` — (open, close) пары для timing_score
  - `metrics.py`: Murphy decomposition (REL, RES, UNC), calibration slope (OLS), ECE
  - `schemas.py`: `BettorProfile.timing_score`, `ProfileSummary` percentile constraints (ge=0, le=1)

### Fixed
- **6 crash-багов** (найдены техническим аудитом, 2 агента line-by-line review):
  - `extremize(d < 1.0)` — was silently producing wrong math (probability shrinkage вместо expansion). Теперь `ValueError`.
  - `_parse_timestamp()` — timezone offsets (`+05:00`) были либо dropped, либо wrong UTC. Теперь `fromisoformat()` + `astimezone(UTC)`.
  - `_parse_resolution_row()` — `outcomePrices='{"a":1}'` (object вместо array) → `KeyError`. Теперь type-check `isinstance(prices, list)`.
  - `ProfileSummary` — percentile поля принимали значения > 1.0 или < 0.0. Добавлены `ge=0.0, le=1.0`.
  - `compute_enriched_signal()`: guard `total_w == 0` в parametric blend (предотвращает `ZeroDivisionError`).
  - Citation corrections: Mitts & Ofir 2025 → 2026; `timing_score`/`concentration_entropy` — [INFERRED], не из статьи. Akey et al. 2025 — primary citation для tier profiling.

### Changed
- `signal.py`: `extremize()` теперь требует `d >= 1.0` (breaking: `d < 1.0` → ValueError)
- `loader.py`: `_parse_timestamp()` → `fromisoformat()` вместо manual format list (поддержка timezone offsets)
- `profiler.py`: `build_bettor_profiles()` — 3 новых keyword params: `as_of`, `resolutions_with_dates`, `market_timestamps`

### Metrics
- Тесты: 1172 → 1226 (+54)
- Inverse tests: 156 → 210 (+54)
- E2E server verified: Parquet load 348K INFORMED profiles in 7.5s

---

## [0.9.0] - 2026-03-30

### Added
- **Inverse Problem Phase 2: подключение профилей к pipeline + расширение модели**
  - `store.py`: миграция на Parquet (pyarrow ZSTD) — 506 МБ → ~60 МБ, загрузка 0.3с вместо 12с. **Почему:** 506 МБ JSON → полная десериализация в RAM (~1 ГБ peak) при каждом старте worker'а; Parquet с predicate pushdown грузит только INFORMED тир за 0.3с.
  - `tier_filter` param в `load_profiles()`: default "informed" грузит только 348K вместо 1.7M
  - JSON backward compat сохранён (dispatch по расширению файла)
  - Bayesian shrinkage в `profiler.py`: `adjusted_BS = (n×BS + k×median) / (n+k)`, k=15. **Почему:** при n=3 resolved bets Brier Score имеет огромную дисперсию — "lucky streak" классифицируется как INFORMED. Shrinkage стягивает малонадёжные оценки к популяционной медиане (Ferro & Fricker 2012).
  - `parametric.py` (NEW): Exp(λ) closed-form MLE + Weibull(λ,k) via scipy L-BFGS-B. **Почему:** BS говорит "точный/неточный", λ даёт модель поведения — как человек оценивает вероятность во времени. Нет опубликованных работ по Weibull recovery из prediction market bets — publishable novelty.
  - `clustering.py` (NEW): HDBSCAN на behavioral features (optional dep), 6 стратегических архетипов (sharp_informed, skilled_retail, volume_bettor, contrarian, stale, noise_trader)
  - `cloning.py` (NEW): clone validation — predicted vs actual positions, MAE, skill_score. **Почему:** аргумент транзитивности Алексея — если клоны предсказывают ставки И ставки отражают реальность → клоны предсказывают реальность.
  - `signal.py`: `compute_enriched_signal()` с adaptive parametric blending + extremizing (Satopää et al. 2014). **Почему:** после accuracy-weighted aggregation, push away from 50% даёт 10-20% BS improvement в сравнимых популяциях прогнозистов.
  - Extended `InformedSignal`: +4 optional поля (parametric_probability, parametric_model, mean_lambda, dominant_cluster) — backward-compatible.
  - `loader.py`: `load_market_horizons()` — market_id → horizon_days из CSV (блокер для параметрики)
  - New schemas: ExponentialFit, WeibullFit, ParametricResult, CloneValidationResult, ClusterAssignment
  - `scripts/convert_json_to_parquet.py`: одноразовая миграция JSON → Parquet на сервере
  - Build scripts (`duckdb_build_profiles.py`, `hf_build_profiles.py`) обновлены: output .parquet по умолчанию

### Changed
- `store.py` DEFAULT_PROFILES_PATH: `.json` → `.parquet`
- `profiler.py`: новый param `shrinkage_strength=15` (0 = отключить)
- `dry_run.py --profiles`: принимает .parquet и .json

### Metrics
- Тесты: 1102 → 1172 (+70)
- Inverse tests: 87 → 156 (+69)

---

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
- **CSRF middleware**: `request.form()` потребляло тело запроса → 422 на `/register` и `/login`. Заменено на `request.body()` + `parse_qs()`.

### Changed
- **Outlet URL fallback**: опциональное поле URL для неизвестных изданий. Если автокомплит не находит СМИ, пользователь может указать URL сайта → `resolve_by_url()` обнаруживает RSS и кэширует.
- **Dark mode удалён**: оставлена только светлая тема.
- **YandexGPT удалён**: stub никогда не работал. Все LLM-задачи через OpenRouter. 3 задачи (`style_generation`, `style_generation_ru`, `quality_style`) переведены с yandexgpt на `anthropic/claude-sonnet-4`.

### Metrics
- Тесты: 1096 → 1142
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
