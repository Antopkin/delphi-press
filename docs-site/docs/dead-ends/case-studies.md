# Case Studies: Dead Ends & Lessons

This section documents 21 case studies from 6 months of Delphi Press development, organized by category: 4 API issues, 4 architectural failures, 8 critical bugs, and 5 deferred directions.

## API Dead Ends

### Case Study 1: Metaculus 403 API Deprecation and Tier Lock (v0.5.1)

**Problem:** Metaculus serves as a source of structured community forecasts. On production server v0.5.1, all API requests returned HTTP 403 Forbidden, but tests passed locally.

**What was done:** Fixed endpoint migration from `/api2/questions/` to `/api/posts/`, added required `Authorization: Token` header, renamed parameters (`status` → `statuses`, `resolve_time__gt` → `scheduled_resolve_time__gt`), rewrote response parsing. Token generated at https://www.metaculus.com/aib/ (free, non-expiring).

**Lesson learned:** Never assume backward compatibility in third-party APIs. Even if legacy endpoints work for 10+ months, they may be deprecated. Subscribe to official API channels, save documentation locally, fix rate limits conservatively (120 req/min for Metaculus), and make credentials configurable from environment.

---

### Case Study 2: GDELT Cyrillic Query Crash (pre-v0.5.1, v0.9.4)

**Problem:** ForesightCollector called GDELT with Cyrillic queries like "news forecast 2026-03-29 ТАСС", causing JSON parse errors when ElasticSearch returned HTML instead of JSON.

**What was done:** Added Content-Type header check before JSON parsing, implemented null-safe articles handling (`(data.get("articles") or [])`), switched to English queries, used GDELT language operators (`sourcelang:russian + sourcecountry:RS`).

**Lesson learned:** Never trust charset support without explicit testing. Filter languages through operators rather than query text. Check Content-Type headers before parsing JSON. Protect against null values with `(field or [])` rather than `get(field, [])`. Rate limit GDELT at ~1 req/sec.

---

### Case Study 3: Polymarket camelCase Parameter Mismatch (pre-v0.5.1)

**Problem:** ForesightCollector sent `GET /markets?order=volume_24hr` (snake_case), receiving HTTP 422 Unprocessable Entity on production, though not reproducible locally.

**What was done:** Changed to `order=volume24hr` (camelCase). Discovered `/markets` endpoint requires camelCase while `/events` requires snake_case — undocumented inconsistency.

**Lesson learned:** Always test all endpoints live before production deploy. Do not assume consistency between similar endpoints. Create local reference documentation for external APIs with examples. When receiving 422, check each parameter against docs.

---

### Case Study 4: Reuters RSS Feed Deprecation (v0.9.4)

**Problem:** Historical GLOBAL_RSS_FEEDS included Reuters URLs returning 404. Pipeline failed at stage 1 when fetching news signals.

**What was done:** Removed all Reuters feeds from `src/agents/collectors/news_scout.py`. Alternative sources (BBC, AP, Bloomberg) remain.

**Lesson learned:** RSS feeds are live resources requiring periodic health checks. Large publishers may close public feeds without warning. Maintain fallback sources. Do not rely on single publisher. Track 404/410 errors in logs as signals of dead feeds.

---

## Architectural Failures

### Case Study 5: YandexGPT Stub (v0.8.0)

**Problem:** v0.7.0 contained fallback logic to YandexGPT when OPENROUTER_API_KEY absent. Integration threw NotImplementedError on every call (never implemented beyond stub). Server had VPN access but single-provider fallback created single point of failure.

**What was done:** Completely removed YandexGPT. Migrated three tasks (`style_generation`, `style_generation_ru`, `quality_style`) to OpenRouter with Claude Sonnet 4.6.

**Lesson learned:** Do not architect fallback to unreliable second provider. Single well-tested provider beats two half-implemented ones. Choose one primary provider and stick with it. If redundancy needed, fully test both.

---

### Case Study 6: Non-Existent Preset Sonnet 4.6 (v0.9.4)

**Problem:** v0.9.3 contained 3 presets: Light (Gemini Flash), Standard (Claude Sonnet 4.6), Opus (Claude Opus 4.6). Standard preset referenced non-existent model `claude-sonnet-4.6` (OpenRouter offers `claude-3.5-sonnet` only). Pipeline crashed on first LLM call with "model not found".

**What was done:** Removed Standard preset. Kept Light (Gemini 2.5 Flash) and Opus (Claude Opus 4.6). Updated UI.

**Lesson learned:** Validate model names before deploy. Add CI/CD step testing each preset with real API calls. Maintain current list of available models per provider. Better 1 working preset than 3 broken ones.

---

### Case Study 7: Dark Mode Complexity (v0.8.0)

**Problem:** v0.7.0 implemented dark mode with toggle button, localStorage, and system preference detection. Added CSS duplication, JS complexity, testing burden, and user confusion (toggle not discoverable).

**What was done:** Removed dark mode completely. Kept light theme with OKLCH palette optimized for contrast and accessibility.

**Lesson learned:** Do not add features without user request. YAGNI principle. Even "nice to have" features cost maintenance. Gather feedback before adding UI features. One well-done theme beats two poorly-done ones.

---

### Case Study 8: Pico.css → Tailwind CSS Migration (v0.8.0)

**Problem:** Classless CSS (Pico.css) worked for prototypes but product grew beyond its limits: OKLCH color space unsupported, no custom components, limited responsive utilities, no animations.

**What was done:** Migrated to Tailwind CSS v4.2.2 with PostCSS build pipeline. Implemented Impeccable design system with 17 JS-referenced `fn-*` components. Used Newsreader/Source Sans 3/JetBrains Mono from Google Fonts.

**Lesson learned:** Classless frameworks are trap for anything more complex than landing page. Evaluate UI ceiling at project start, not by current needs. Migration cost grows non-linearly with template count. Utility framework scales; classless doesn't.

---

## Critical Bugs

### Case Study 9: Temporal Leak in Walk-Forward Evaluation (v0.9.2)

**Problem:** Walk-forward validation used pre-aggregated bettor positions covering entire dataset. At cutoff $T$, positions contained average of trades dated $T + 30$ days. Information leak: model saw future signals.

**What was done:** Rewrote aggregation into 30-day bucketed parquet. Walk-forward now computes `avg_position_as_of_T` using only `time_bucket <= T`. DuckDB with predicate pushdown: 225× speedup, memory from 7.4 GB to 4.6 GB.

**Result:** Leaked BSS +0.092 vs clean BSS +0.127 on same folds. Leak added noise, not signal.

**Lesson learned:** Temporal cutoff requires time dimension in data, not global aggregation. Never use pre-aggregated data for temporal validation. Bucketed aggregates enable point-in-time queries. Always verify: no trades/signals dated > cutoff $T$.

---

### Case Study 10: conditionId Mismatch (v0.9.3)

**Problem:** Polymarket has dual IDs: `id` (numeric, local to Gamma API) and `conditionId` (CTF hex hash, global in CLOB + Data API). ForesightCollector joined on `id`, loader.py on `conditionId`. 99% signal loss due to no matches.

**What was done:** Changed join key to `conditionId`. Added documentation comments explaining both IDs.

**Lesson learned:** When third-party API has multiple IDs, document purpose of each. Add code comments: "market.id: local (Gamma), market.conditionId: global (CLOB)". Test: fetch via both endpoints, verify both IDs return. Unit test: join on wrong ID must return 0 matches. Add assertion checking match count > 0.

---

### Case Study 11: Date Serialization Crash (v0.9.5)

**Problem:** Timeline schemas added `predicted_date` and `target_date` fields. Pipeline completed 9 stages (40 min, $5-15 cost), but worker crashed on save with `TypeError: Object of type date is not JSON serializable`. Result lost.

**What was done:** Added `@field_serializer` decorators converting `datetime.date` to ISO format. Alternative: use `model_dump(mode="json")` explicitly.

**Lesson learned:** Serialization must be unit-tested. Never assume `model_dump()` yields JSON-ready dict. Test: `model_dump() → json.dumps() → json.loads()` round-trip. When adding date/datetime fields, immediately add serializer. Use `model_dump(mode="json")` in production (more explicit). Remember: Pydantic v2 requires explicit mode for JSON types.

---

### Case Study 12: PromptParseError Silently Dropped (v0.5.2–v0.9.4)

**Problem:** EventTrendAnalyzer requests JSON from LLM (e.g., Gemini Flash). When LLM returns truncated JSON (`finish_reason="length"`), catch-all exception handler returned empty dict `{}`. Downstream expected `EventThreads` (required fields), got `{}` → ValidationError → silent assessment drop → empty timeline.

**What was done:** Distinguished JSON parse errors from validation errors. For parse errors: log and fallback to raw headlines. For validation errors: return structured default `EventThreads(threads=[])`. 

**Lesson learned:** Never silently swallow exceptions. Either fail-fast or graceful fallback with logged reason. Distinguish error types (parse vs validation) — different fix strategies. Fallback value must have correct structure, not empty `{}`. Log exception content, not just message. Unit test: LLM returns truncated JSON, verify fallback works.

---

### Case Study 13: BudgetTracker Race Condition (v0.7.1)

**Problem:** BudgetTracker checked and incremented budget in async context without synchronization. Race condition: Agent 1 reads total_cost=48, Agent 2 reads 48, Agent 1 writes 49.5, Agent 2 writes 50.0 (could exceed max). Budget check bypassed.

**What was done:** Wrapped check-and-update with `asyncio.Lock()`.

**Lesson learned:** Shared state in async code requires synchronization primitives. Use `asyncio.Lock()` for read-modify-write. Never assume single-threaded safety in async context. Unit test: run concurrent calls with `asyncio.gather()`, verify atomicity. Code review: flag any `self.field =` in async function — potential race condition.

---

### Case Study 14: Timeout Cascade (v0.9.4)

**Problem:** Default agent timeout 300 seconds. Heavy prompts (Opus multi-agent mediation) exceeded limits regularly. Cascading failure: one stage timeout dropped entire pipeline after 40+ minutes compute.

**What was done:** Raised default from 300s to 600s (2x p95 latency). Per-stage tuning: `outlet_historian` 300s (lightweight), `delphi_r2` 900s (complex multi-agent), others 600s.

**Lesson learned:** Default timeouts must be based on 2x observed p95 latency, not optimistic averages. Monitor real latency before setting thresholds. Tune per-stage — one stage can be 10x heavier than another. Cascading timeout failure worse than extra 5 minutes wait.

---

### Case Study 15: max_tokens Evolution (v0.5.1–v0.9.5)

**Problem:** Parameter went through iterations: 4096 (truncated Delphi R1) → 8192 (still insufficient) → 16384 (OpenRouter reserved this from credit balance, blocking parallel calls) → unlimited (current). Setting 16384 reserved $5+ per call despite 2000-token actual output.

**What was done:** Removed cap entirely. Discovered OpenRouter's credit reservation mechanism: `max_tokens` amount reserved upfront.

**Lesson learned:** LLM API pricing models are non-obvious. Test cost impact of `max_tokens` before production. Check how provider handles it: billing by actual output or reserved cap? For OpenRouter: unlimited `max_tokens` cheaper than high fixed cap. Document pricing gotchas per provider.

---

### Case Study 16: Incremental Checkpoint Saving (v0.9.5)

**Problem:** Pipeline saved results only on completion of all 9 stages. If stage 9 timeout after 40+ minutes, all results ($5-15 cost) lost. User sees blank page despite massive compute.

**What was done:** Implemented per-stage incremental save. Each completed stage persists to `PipelineStep.output_data`. Worker can resume from last checkpoint.

**Lesson learned:** Long-running pipelines must checkpoint after expensive steps. "All-or-nothing" unacceptable when each step costs dollars. Lost work cost proportional to stages without checkpoints. Checkpoint recovery saves time and money.

---

## Deferred Directions

### Case Study 17: Domain-Specific Brier Scores

**Idea:** Different market types (crypto, politics, sports) have different accuracy characteristics. Compute per-domain BS weights for adaptive extremizing.

**Why deferred:** Data sparsity. Only ~100 of 348K informed bettors have >5 resolved bets per domain. BS on small N has huge variance. Stratifying drops 99% of bettors.

**Lesson:** Don't add complexity for marginal gains (1–3% improvement) on limited data.

---

### Case Study 18: Bettor-Level News Correlation

**Idea:** Informed bettors react quickly to breaking news. Build predictive model of position changes vs GDELT signals.

**Why deferred:** Speculative hypothesis needs special pipeline: working GDELT API, per-outlet RSS, temporal alignment (complex time model), validation unclear.

**Lesson:** Research hypotheses need pilot data before full engineering effort.

---

### Case Study 19: Hierarchical Trader Belief Models

**Idea:** Build Bayesian hierarchical model of bettor beliefs for better aggregate forecast.

**Why deferred:** Pure research project, not engineering task. Requires novel statistical methods, publication-quality validation, large dataset, clear "belief" definition.

**Lesson:** Distinguish engineering (solve known problem) from research (formulate new problem). Don't fill product roadmap with research ideas.

---

### Case Study 20: Kalshi API Integration

**Idea:** Kalshi is second major US prediction market. Expand coverage?

**Why deferred:** US-only, low ROI. ~500 active markets (vs Polymarket ~5000+), no public bettor profiles, higher regulation. Integration cost 3 days, result +200 low-quality markets, 0 new signals.

**Lesson:** Evaluate ROI before adding data source. Not all APIs worth integrating.

---

### Case Study 21: BigQuery for GDELT Historical Data

**Idea:** Use BigQuery's 2.65 TB/year GDELT dataset for batch retrospective testing.

**Why deferred:** Cost-prohibitive. Unoptimized query: $1.94/query. Optimized: $0.04/query. 100-query batch: $200-$400. Alternative: free 15-minute CSV polling + local DuckDB. Total cost $0, speed acceptable for monitoring.

**Lesson:** Evaluate cloud costs vs local alternatives. Free polling beats paid queries.

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
| 16 | | Incremental save | Fixed | v0.9.5 | $5-15 result loss |
| 17 | Deferred | Domain-specific BS | Deferred | — | 1–3% gain, high sparsity |
| 18 | | Bettor-news correlation | Deferred | — | Speculative hypothesis |
| 19 | | Hierarchical beliefs | Deferred | — | Pure research |
| 20 | | Kalshi API | Deferred | — | US-only, low ROI |
| 21 | | BigQuery GDELT | Deferred | — | Cost-prohibitive ($0.04–$1.94/query) |

## Key Takeaways

1. **External APIs require continuous monitoring.** Breaking changes happen (Metaculus, Reuters). Subscribe to official channels.
2. **Single-provider architecture better than unreliable fallbacks.** YandexGPT was removed, OpenRouter is sole LLM provider.
3. **Serialization and temporal correctness are non-negotiable.** Date serialization crash and temporal leak both caused complete data loss/model degradation.
4. **Distinguish engineering from research.** Hierarchical models are research; bettor signals are engineering.
5. **ROI analysis prevents feature creep.** Domain-specific BS, Kalshi, BigQuery all deferred because cost > benefit.
