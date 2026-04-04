# Case Studies: Dead Ends & Lessons

This section documents 21 case studies from 6 months of Delphi Press development, organized by category: 4 API issues, 4 architectural failures, 8 critical bugs, and 5 deferred directions.

## API Dead Ends

### Case Study 1: Metaculus 403 API Deprecation and Tier Lock (v0.5.1)

**Problem:** Metaculus serves as a source of structured community forecasts. On production server v0.5.1, all API requests returned HTTP 403 Forbidden, but tests passed locally.

**What was done:** Fixed endpoint migration from `/api2/questions/` to `/api/posts/`, added required `Authorization: Token` header, renamed parameters (`status` → `statuses`, `resolve_time__gt` → `scheduled_resolve_time__gt`), rewrote response parsing. Token generated at https://www.metaculus.com/aib/ (free, non-expiring).

**Lesson learned:** Never assume backward compatibility in third-party APIs. Even if legacy endpoints work for 10+ months, they may be deprecated. Subscribe to official API channels, save documentation locally, fix rate limits conservatively (120 req/min for Metaculus), and make credentials configurable from environment.

!!! tip "Урок"
    **Никогда не предполагай обратную совместимость внешней API**, даже если старый endpoint работает 10+ месяцев. Это может быть legacy layer, а не гарантия. 

    - Подписывайся на изменения API через официальные каналы (RSS, email newsletters, GitHub releases)
    - При интеграции сохраняй последнюю документацию локально (в проекте: `tasks/research/`)
    - Зафиксируй rate limit консервативно (для Metaculus: 120 req/min без официального публикованного лимита)
    - При auth-требовании явно документируй, как получить credentials, и сделай их конфигурируемыми из окружения
    - Версия v0.9.4: API отключена из-за tier lock (BENCHMARKING tier требуется)

---

### Case Study 2: GDELT Cyrillic Query Crash (pre-v0.5.1, v0.9.4)

**Problem:** ForesightCollector called GDELT with Cyrillic queries like "news forecast 2026-03-29 ТАСС", causing JSON parse errors when ElasticSearch returned HTML instead of JSON.

**What was done:** Added Content-Type header check before JSON parsing, implemented null-safe articles handling (`(data.get("articles") or [])`), switched to English queries, used GDELT language operators (`sourcelang:russian + sourcecountry:RS`).

**Lesson learned:** Never trust charset support without explicit testing. Filter languages through operators rather than query text. Check Content-Type headers before parsing JSON. Protect against null values with `(field or [])` rather than `get(field, [])`. Rate limit GDELT at ~1 req/sec.

!!! tip "Урок"
    **Никогда не доверяй charset-поддержке без явного тестирования**, даже если документация не упоминает ограничения.

    - Запрашиваемые языки фильтруй через операторы API (e.g., `sourcelang:russian`), а не через текст query
    - Проверяй `content-type` заголовок перед парсингом JSON — спасает от HTML error pages
    - Защищайся от null values: `(data.get("field") or [])` вместо `data.get("field", [])`
    - Rate limit GDELT: ~1 req/sec, добавь exponential backoff на 429
    - Граничные случаи (non-ASCII characters, будущие даты): всегда тестируй живо

---

### Case Study 3: Polymarket camelCase Parameter Mismatch (pre-v0.5.1)

**Problem:** ForesightCollector sent `GET /markets?order=volume_24hr` (snake_case), receiving HTTP 422 Unprocessable Entity on production, though not reproducible locally.

**What was done:** Changed to `order=volume24hr` (camelCase). Discovered `/markets` endpoint requires camelCase while `/events` requires snake_case — undocumented inconsistency.

**Lesson learned:** Always test all endpoints live before production deploy. Do not assume consistency between similar endpoints. Create local reference documentation for external APIs with examples. When receiving 422, check each parameter against docs.

!!! tip "Урок"
    **API inconsistency — это дизайн-баг, но при интеграции нужно быть готовым.** Polymarket `/markets` требует camelCase, а `/events` — snake_case.

    - Тестируй все endpoints той же API живо перед production deploy
    - Не полагайся на consistency между похожими endpoints
    - Создай локальный reference документ для каждого внешнего API (pattern: `tasks/research/`)
    - При 422 Unprocessable Entity: проверь каждый параметр через документацию
    - Для Polymarket: `volume24hr` (camelCase), не `volume_24hr`

---

### Case Study 4: Reuters RSS Feed Deprecation (v0.9.4)

**Problem:** Historical GLOBAL_RSS_FEEDS included Reuters URLs returning 404. Pipeline failed at stage 1 when fetching news signals.

**What was done:** Removed all Reuters feeds from `src/agents/collectors/news_scout.py`. Alternative sources (BBC, AP, Bloomberg) remain.

**Lesson learned:** RSS feeds are live resources requiring periodic health checks. Large publishers may close public feeds without warning. Maintain fallback sources. Do not rely on single publisher. Track 404/410 errors in logs as signals of dead feeds.

!!! tip "Урок"
    **RSS feeds — живые ресурсы. Периодически проверяй их здоровье.**  Reuters (feeds.reuters.com) закрыт полностью с 2020 года.

    - Добавь health-check для RSS feeds в мониторинг (попытка fetch за последнюю неделю)
    - Имей fallback источники (если один закрывается, pipeline не ломается)
    - Не полагайся на одного издателя — diversify через BBC, AP, Bloomberg и others
    - Отслеживай 404/410 в логах как сигнал мёртвого feed
    - При dead feed обновление могут приуроченить к release (v0.9.4)

---

## Architectural Failures

### Case Study 5: YandexGPT Stub (v0.8.0)

**Problem:** v0.7.0 contained fallback logic to YandexGPT when OPENROUTER_API_KEY absent. Integration threw NotImplementedError on every call (never implemented beyond stub). Server had VPN access but single-provider fallback created single point of failure.

**What was done:** Completely removed YandexGPT. Migrated three tasks (`style_generation`, `style_generation_ru`, `quality_style`) to OpenRouter with Claude Sonnet 4.6.

**Lesson learned:** Do not architect fallback to unreliable second provider. Single well-tested provider beats two half-implemented ones. Choose one primary provider and stick with it. If redundancy needed, fully test both.

!!! tip "Урок"
    **Не строй архитектуру на наличии двух провайдеров, если один не работает.** Single LLM provider лучше, чем fallback на неработающего second.

    - Выбери один primary провайдер и придерживайся его
    - Если нужна redundancy, выбери два провайдера, оба fully tested и integrated
    - Не добавляй условную логику "если API key отсутствует, используй другого" — это скрывает problems
    - Документируй, какой провайдер primary, в CLAUDE.md
    - Все 28 LLM-задач на одном провайдере (OpenRouter) проще, чем сплит

---

### Case Study 6: Non-Existent Preset Sonnet 4.6 (v0.9.4)

**Problem:** v0.9.3 contained 3 presets: Light (Gemini Flash), Standard (Claude Sonnet 4.6), Opus (Claude Opus 4.6). Standard preset referenced non-existent model `claude-sonnet-4.6` (OpenRouter offers `claude-3.5-sonnet` only). Pipeline crashed on first LLM call with "model not found".

**What was done:** Removed Standard preset. Kept Light (Gemini 2.5 Flash) and Opus (Claude Opus 4.6). Updated UI.

**Lesson learned:** Validate model names before deploy. Add CI/CD step testing each preset with real API calls. Maintain current list of available models per provider. Better 1 working preset than 3 broken ones.

!!! tip "Урок"
    **Валидируй model names до production deploy.** Confusion между Sonnet версиями: есть `claude-3.5-sonnet`, но нет `claude-sonnet-4.6`.

    - Добавь CI/CD step, который тестирует каждый пресет с real API call перед deploy
    - Держи актуальный список доступных моделей на каждом провайдере в wiki
    - Лучше иметь 1 пресет, который работает, чем 3, из которых 2 сломаны
    - Синхронизируй `src/config.py` presets с OpenRouter pricing docs
    - v0.9.4: оставлены только 2 пресета — Light (Gemini 2.5 Flash) и Opus (Claude Opus 4.6)

---

### Case Study 7: Dark Mode Complexity (v0.8.0)

**Problem:** v0.7.0 implemented dark mode with toggle button, localStorage, and system preference detection. Added CSS duplication, JS complexity, testing burden, and user confusion (toggle not discoverable).

**What was done:** Removed dark mode completely. Kept light theme with OKLCH palette optimized for contrast and accessibility.

**Lesson learned:** Do not add features without user request. YAGNI principle. Even "nice to have" features cost maintenance. Gather feedback before adding UI features. One well-done theme beats two poorly-done ones.

!!! tip "Урок"
    **Не добавляй features без спроса. YAGNI.** Даже если feature кажется "nice to have", цена maintenance высока.

    - Собирай feedback перед добавлением UI features
    - Если feature не используется, удали её (dead code — source of bugs)
    - Лучше одна хорошо-сделанная тема с OKLCH палитрой, чем две плохо-сделанные
    - CSS и JS complexity для dark mode дублировали код и тестирование
    - User confusion: toggle не discoverable → feature не используется

---

### Case Study 8: Pico.css → Tailwind CSS Migration (v0.8.0)

**Problem:** Classless CSS (Pico.css) worked for prototypes but product grew beyond its limits: OKLCH color space unsupported, no custom components, limited responsive utilities, no animations.

**What was done:** Migrated to Tailwind CSS v4.2.2 with PostCSS build pipeline. Implemented Impeccable design system with 17 JS-referenced `fn-*` components. Used Newsreader/Source Sans 3/JetBrains Mono from Google Fonts.

**Lesson learned:** Classless frameworks are trap for anything more complex than landing page. Evaluate UI ceiling at project start, not by current needs. Migration cost grows non-linearly with template count. Utility framework scales; classless doesn't.

!!! tip "Урок"
    **Classless CSS-фреймворки — ловушка для всего, что сложнее landing page.** Требования выросли за потолок Pico.css: OKLCH-палитра, компоненты, анимации.

    - Оценивай потолок UI-требований на старте проекта (dashboard, timeline, cards), а не по текущим потребностям
    - Стоимость миграции CSS растёт нелинейно с количеством шаблонов
    - Утилитарный фреймворк (Tailwind) масштабируется; classless нет
    - Миграция выявила потребность в дизайн-системе (Impeccable с 17 `fn-*` компонентами)
    - Новая типография: Newsreader (заголовки) + Source Sans 3 (body) + JetBrains Mono (code)

---

## Critical Bugs

### Case Study 9: Temporal Leak in Walk-Forward Evaluation (v0.9.2)

**Problem:** Walk-forward validation used pre-aggregated bettor positions covering entire dataset. At cutoff $T$, positions contained average of trades dated $T + 30$ days. Information leak: model saw future signals.

**What was done:** Rewrote aggregation into 30-day bucketed parquet. Walk-forward now computes `avg_position_as_of_T` using only `time_bucket <= T`. DuckDB with predicate pushdown: 225× speedup, memory from 7.4 GB to 4.6 GB.

**Result:** Leaked BSS +0.092 vs clean BSS +0.117 on same folds. Leak added noise, not signal.

!!! tip "Урок"
    **Temporal cutoff требует временного измерения в данных, не глобального агрегирования.** Это критично для walk-forward evaluation.

    - Никогда не используй pre-aggregated data для temporal validation
    - Bucketed/timestamped aggregates позволяют point-in-time queries: `avg_position_as_of_T WHERE time_bucket <= T`
    - Всегда проверяй: есть ли trades/signals с датой > cutoff T? Если да, это leak
    - Unit test: add explicit check что `as_of_date < cutoff_date` для всех test data
    - Дизайн-паттерн: SUM(weighted_price_sum) / SUM(total_usd) для composable aggregates
    - Результат: на тех же фолдах clean BSS = +0.117 (vs leaked +0.092); robust mean по 22 фолдам = +0.127

---

### Case Study 10: conditionId Mismatch (v0.9.3)

**Problem:** Polymarket has dual IDs: `id` (numeric, local to Gamma API) and `conditionId` (CTF hex hash, global in CLOB + Data API). ForesightCollector joined on `id`, loader.py on `conditionId`. 99% signal loss due to no matches.

**What was done:** Changed join key to `conditionId`. Added documentation comments explaining both IDs.

!!! tip "Урок"
    **Когда third-party API имеет несколько IDs, документируй purpose каждого в code comments.**

    - Добавь inline comment: `# conditionId: global (CLOB + Data API), id: local (Gamma marketplace)`
    - Test: fetch market через оба endpoints, verify оба ID'а возвращаются
    - Unit test: join на wrong ID должен вернуть 0 matches (catch этот конкретный баг)
    - Добавь assertion: `assert len(matches) > 0, "No markets matched! Check join keys."`
    - Версия v0.9.3: 99% signal loss из-за неправильного join key
    - Дизайн-паттерн: для multi-ID API создай separate test, используя wrong ID

---

### Case Study 11: Date Serialization Crash (v0.9.5)

**Problem:** Timeline schemas added `predicted_date` and `target_date` fields. Pipeline completed 9 stages (40 min, \$5-15 cost), but worker crashed on save with `TypeError: Object of type date is not JSON serializable`. Result lost.

**What was done:** Added `@field_serializer` decorators converting `datetime.date` to ISO format. Alternative: use `model_dump(mode="json")` explicitly.

!!! tip "Урок"
    **Serialization должна быть unit-tested. Никогда не предполагай, что `model_dump()` даст JSON-ready dict.**

    - Pydantic v2 требует explicit `mode="json"` для JSON serialization (не default mode)
    - Add test: `model_dump() → json.dumps() → json.loads()` round-trip для каждого schema с date/datetime
    - При добавлении новых date/datetime fields, immediately add `@field_serializer`
    - Используй `model_dump(mode="json")` в production code (explicit, не default)
    - Pipeline проходит 9 стадий за 40 мин, crash на save = полная потеря результата (\$5-15 cost)
    - Алтернатива: `model_dump(mode="json")` везде, но `@field_serializer` более локален

---

### Case Study 12: PromptParseError Silently Dropped (v0.5.2–v0.9.4)

**Problem:** EventTrendAnalyzer requests JSON from LLM (e.g., Gemini Flash). When LLM returns truncated JSON (`finish_reason="length"`), catch-all exception handler returned empty dict `{}`. Downstream expected `EventThreads` (required fields), got `{}` → ValidationError → silent assessment drop → empty timeline.

**What was done:** Distinguished JSON parse errors from validation errors. For parse errors: log and fallback to raw headlines. For validation errors: return structured default `EventThreads(threads=[])`.

!!! tip "Урок"
    **Никогда не swallow exceptions молча. Either fail-fast или graceful fallback с logged reason.**

    - Distinguish error types: parse errors vs validation errors имеют разные fix strategies
    - Fallback value должен иметь корректную структуру (не `{}`, а `Model(field1=[], field2=None)`)
    - Логируй exception content (e.g., `str(e)` или `e.json()`), не только message
    - Unit test: LLM возвращает truncated JSON (`finish_reason="length"`), verify fallback works
    - Дизайн-паттерн: distinguish JSON decode error (fallback to raw) vs validation error (return default)
    - Версия v0.5.2: первый fix PromptParseError; v0.9.4: добавлен resilient event_identification с proper fallback

---

### Case Study 13: BudgetTracker Race Condition (v0.7.1)

**Problem:** BudgetTracker checked and incremented budget in async context without synchronization. Race condition: Agent 1 reads total_cost=48, Agent 2 reads 48, Agent 1 writes 49.5, Agent 2 writes 50.0 (could exceed max). Budget check bypassed.

**What was done:** Wrapped check-and-update with `asyncio.Lock()`.

!!! tip "Урок"
    **Shared state в async code требует synchronization primitives (asyncio.Lock).**

    - Используй `asyncio.Lock()` для защиты read-modify-write операций (TOCTOU fix)
    - Никогда не предполагай, что single-threaded code безопасен в async context
    - Unit test: запусти с `asyncio.gather()` несколько concurrent calls, verify atomicity
    - Code review: флаг на любое `self.field = ...` в async function — potential race condition
    - Race condition: Agent 1 reads, Agent 2 reads (оба видят 48), потом оба пишут → check bypassed
    - Паттерн: `async with self._lock: [check and write]`

---

### Case Study 14: Timeout Cascade (v0.9.4)

**Problem:** Default agent timeout 300 seconds. Heavy prompts (Opus multi-agent mediation) exceeded limits regularly. Cascading failure: one stage timeout dropped entire pipeline after 40+ minutes compute.

**What was done:** Raised default from 300s to 600s (2x p95 latency). Per-stage tuning: `outlet_historian` 300s (lightweight), `delphi_r2` 900s (complex multi-agent), others 600s.

!!! tip "Урок"
    **Дефолтные таймауты должны базироваться на 2× наблюдаемый p95 latency, а не на оптимистичных средних.**

    - Мониторь реальные latency перед выставлением порогов (заведи метрики per stage)
    - Настраивай таймауты per stage — одна стадия может быть 10× тяжелее другой
    - Каскадный отказ от таймаута хуже, чем дополнительные 5 минут ожидания
    - Версия v0.9.4: outlet_historian 300s, delphi_r2 900s (5 персон в медиации), остальные 600s
    - Правило: `timeout = max(p95_latency) × 2`, не средние значения

---

### Case Study 15: max_tokens Evolution (v0.5.1–v0.9.5)

**Problem:** Parameter went through iterations: 4096 (truncated Delphi R1) → 8192 (still insufficient) → 16384 (OpenRouter reserved this from credit balance, blocking parallel calls) → unlimited (current). Setting 16384 reserved \$5+ per call despite 2000-token actual output.

**What was done:** Removed cap entirely. Discovered OpenRouter's credit reservation mechanism: `max_tokens` amount reserved upfront.

!!! tip "Урок"
    **LLM API pricing модели неочевидны. Тестируй cost impact параметра `max_tokens` перед production deploy.**

    - Проверяй, как провайдер обрабатывает `max_tokens`: billing по фактическому output или по зарезервированному?
    - Для OpenRouter: unlimited `max_tokens` дешевле, чем высокий фиксированный cap (credit reservation gotcha)
    - Документируй pricing gotchas для каждого LLM-провайдера в проектной wiki
    - Версия v0.9.4: `max_tokens` установлен как None (unlimited)
    - Обнаружено: `max_tokens=16384` резервирует \$5+ за call, даже если фактический выход 2000 tokens

---

### Case Study 16: Incremental Checkpoint Saving (v0.9.5)

**Problem:** Pipeline saved results only on completion of all 9 stages. If stage 9 timeout after 40+ minutes, all results (\$5-15 cost) lost. User sees blank page despite massive compute.

**What was done:** Implemented per-stage incremental save. Each completed stage persists to `PipelineStep.output_data`. Worker can resume from last checkpoint.

!!! tip "Урок"
    **Долгоживущие pipeline обязаны делать checkpoint после каждого дорогого шага. "Всё или ничего" неприемлемо.**

    - Стоимость потерянной работы пропорциональна количеству стадий без checkpoint'ов
    - Checkpoint recovery позволяет retry с последней точки, экономя и время, и деньги
    - Паттерн: каждый stage записывает `PipelineStep.output_data` сразу после успешного завершения
    - Версия v0.9.5: stage_callback в orchestrator сохраняет headlines после каждой стадии
    - Если timeout на stage 8 (40 мин, \$5-15), пользователь всё равно видит draft headlines из stage 1-7

---

## Deferred Directions

### Case Study 17: Domain-Specific Brier Scores

**Idea:** Different market types (crypto, politics, sports) have different accuracy characteristics. Compute per-domain BS weights for adaptive extremizing.

**Why deferred:** Data sparsity. Only ~100 of 348K informed bettors have >5 resolved bets per domain. BS on small N has huge variance. Stratifying drops 99% of bettors.

!!! tip "Урок"
    **Не добавляй complexity для marginal gains на limited data.** 1–3% улучшение требует 10× больше данных.

    - Domain-specific BS обещает 1–3% BSS gain, но requires stratification
    - Из 348K informed бетторов, только ~100 имеют >5 resolved bets per domain
    - BS на малом N имеет огромную дисперсию (lucky streak классифицируется как INFORMED)
    - Cost-benefit: effort > benefit

---

### Case Study 18: Bettor-Level News Correlation

**Idea:** Informed bettors react quickly to breaking news. Build predictive model of position changes vs GDELT signals.

**Why deferred:** Speculative hypothesis needs special pipeline: working GDELT API, per-outlet RSS, temporal alignment (complex time model), validation unclear.

!!! tip "Урок"
    **Research hypotheses требуют pilot data перед full engineering effort.** Не начинай building без evidence.

    - Спекулятивная гипотеза требует специального pipeline: GDELT API (fixed в v0.9.4, но limited), RSS per outlet, temporal alignment (complex)
    - Validation unclear: есть ли реальная correlation между news и bettor positions?
    - Процесс: hypothesis → pilot data collection → evidence → full engineering
    - Без pilot data это speculative, не engineering task

---

### Case Study 19: Hierarchical Trader Belief Models

**Idea:** Build Bayesian hierarchical model of bettor beliefs for better aggregate forecast.

**Why deferred:** Pure research project, not engineering task. Requires novel statistical methods, publication-quality validation, large dataset, clear "belief" definition.

!!! tip "Урок"
    **Distinguish между engineering (solve known problem) и research (formulate new problem).** Не заполняй product roadmap research ideas.

    - Иерархические модели требуют новых statistical methods (Bayesian hierarchical modeling)
    - Publication-quality validation: peer review, reproducibility, novel methods
    - Требуется четкое определение "belief" в контексте prediction markets
    - Это research project, не engineering task (product roadmap != research agenda)

---

### Case Study 20: Kalshi API Integration

**Idea:** Kalshi is second major US prediction market. Expand coverage?

**Why deferred:** US-only, low ROI. ~500 active markets (vs Polymarket ~5000+), no public bettor profiles, higher regulation. Integration cost 3 days, result +200 low-quality markets, 0 new signals.

!!! tip "Урок"
    **Evaluate ROI перед adding new data source.** Не все API'ов стоят интегрирования.

    - Kalshi: ~500 active markets (vs Polymarket ~5000+)
    - US-only coverage, higher regulation, no public bettor profiles (vs Polymarket on-chain transparency)
    - Integration cost: ~3 days (API, schema changes, tests)
    - Result: +200 рынков (низкое качество), 0 новых signals
    - Cost-benefit: effort > benefit

---

### Case Study 21: BigQuery for GDELT Historical Data

**Idea:** Use BigQuery's 2.65 TB/year GDELT dataset for batch retrospective testing.

**Why deferred:** Cost-prohibitive. Unoptimized query: \$1.94/query. Optimized: \$0.04/query. 100-query batch: \$200-\$400. Alternative: free 15-minute CSV polling + local DuckDB. Total cost \$0, speed acceptable for monitoring.

!!! tip "Урок"
    **Evaluate cloud costs vs local alternatives. Free polling beats paid queries.** BigQuery viable для retrospective, но не для real-time.

    - BigQuery pricing: \$6.25/TB (после 1 TB free/месяц)
    - Unoptimized query: 311 GB scanned = \$1.94 per query
    - Optimized query: 6.28 GB scanned = \$0.04 per query
    - 100-query batch retrospective: \$200-\$400 (depends on optimization)
    - Alternative: 15-minute CSV polling (free, 2–5 MB per batch) + local DuckDB
    - Total cost: \$0, speed: достаточна для production monitoring

---

## Summary Table

| # | Category | Case Study | Status | Version | Impact |
|---|---|---|---|---|---|
| 1 | API | Metaculus 403 | Fixed, Disabled | v0.5.1, v0.9.4 | Auth-required tier lock |
| 2 | | GDELT Cyrillic | Fixed | pre-v0.5.1, v0.9.4 | HTML crashes prevented |
| 3 | | Polymarket camelCase | Fixed | pre-v0.5.1 | 422 error resolved |
| 4 | | Reuters RSS | Removed | v0.9.4 | 404 dead feed |
| 5 | Architecture | YandexGPT | Removed | v0.8.0 | Consolidated to OpenRouter |
| 6 | | Sonnet 4.6 | Removed | v0.9.4 | Non-existent model |
| 7 | | Dark mode | Removed | v0.8.0 | Unmaintained feature |
| 8 | | Pico.css → Tailwind | Migrated | v0.8.0 | Classless CSS limit |
| 9 | Critical Bugs | Temporal leak | Fixed | v0.9.2 | BSS +0.092→+0.127 |
| 10 | | conditionId | Fixed | v0.9.3 | 99% signal loss |
| 11 | | Date serialization | Fixed | v0.9.5 | Complete data loss |
| 12 | | PromptParseError | Fixed | v0.5.2–v0.9.4 | Silent assessment drop |
| 13 | | BudgetTracker race | Fixed | v0.7.1 | Budget bypass |
| 14 | | Timeout cascade | Fixed | v0.9.4 | Cascading stage failures |
| 15 | | max_tokens evolution | Fixed | v0.5.1–v0.9.5 | Credit reservation bloat |
| 16 | | Incremental save | Fixed | v0.9.5 | \$5-15 result loss |
| 17 | Deferred | Domain-specific BS | Deferred | — | 1–3% gain, high sparsity |
| 18 | | Bettor-news correlation | Deferred | — | Speculative hypothesis |
| 19 | | Hierarchical beliefs | Deferred | — | Pure research |
| 20 | | Kalshi API | Deferred | — | US-only, low ROI |
| 21 | | BigQuery GDELT | Deferred | — | Cost-prohibitive (\$0.04–\$1.94/query) |

## Key Takeaways

1. **External APIs require continuous monitoring.** Breaking changes happen (Metaculus, Reuters). Subscribe to official channels.
2. **Single-provider architecture better than unreliable fallbacks.** YandexGPT was removed, OpenRouter is sole LLM provider.
3. **Serialization and temporal correctness are non-negotiable.** Date serialization crash and temporal leak both caused complete data loss/model degradation.
4. **Distinguish engineering from research.** Hierarchical models are research; bettor signals are engineering.
5. **ROI analysis prevents feature creep.** Domain-specific BS, Kalshi, BigQuery all deferred because cost > benefit.
