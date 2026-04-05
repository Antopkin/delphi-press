# Documentation Audit: Coverage Gaps

**Date:** 2026-04-05  
**Version:** 0.9.5  
**Documented:** 17 files in docs-site/docs/  
**Codebase Scan:** src/ (18 agents, 9 stages, 50+ modules)

---

## Executive Summary

Delphi Press has comprehensive coverage for **pipeline architecture, agents, and methodology** but significant gaps in:
- **Web UI/Frontend** implementation details
- **Database models and repository patterns**
- **Security infrastructure** (CSRF, JWT, encryption)
- **API endpoint reference** documentation
- **Script tooling and backtest infrastructure**
- **Deployment and configuration management**

**Estimated Impact:** MEDIUM (core algorithm well-documented; team integration and operations less clear)

---

## Documented Coverage (17 Files)

### ✅ Fully Documented (Excellent)

| Module | Doc File | Coverage |
|--------|----------|----------|
| Pipeline architecture | `architecture/overview.md`, `architecture/pipeline.md` | 95% |
| LLM infrastructure | `architecture/llm.md` | 95% |
| Delphi methodology | `delphi-method/delphi-rounds.md` | 95% |
| Trajectory analysis | `delphi-method/analysis.md` | 90% |
| Evaluation metrics | `evaluation/metrics.md` | 85% |
| Stages 6–9 (Judge/Framing/Generation) | `generation/stages-6-9.md` | 90% |
| Polymarket integration | `polymarket/inverse.md` | 90% |
| Data flow overview | `appendix/data-flow.md` | 80% |
| Known gotchas | `appendix/gotchas.md` | 80% |
| Agent prompts | `appendix/prompts.md` | 100% (reference only) |
| Case studies | `dead-ends/case-studies.md` | 100% |
| Roadmap & backlog | `roadmap/tasks.md`, `roadmap/discussion.md` | 90% |
| Bibliography | `bibliography.md` | 100% |

---

## Documentation Gaps (By Severity)

### CRITICAL — Core Functionality Missing

#### 1. Web UI Implementation & Templates

**What's in code:** 12 Jinja2 HTML templates + 5 JavaScript modules + Tailwind CSS

**What's documented:** Nothing

**Files affected:**
- `src/web/router.py` — 20+ route handlers
- `src/web/templates/` — base, login, register, index, progress, results, markets, settings, about, partials
- `src/web/static/js/` — form.js, progress.js, results.js, markets.js, settings.js, reveal.js
- `src/web/static/css/` — input.css (PostCSS), tailwind.css

**Content:**
- User authentication UI (login/register flows)
- Prediction creation form with outlet selector
- Real-time progress streaming (SSE)
- Results display with reasoning blocks
- Markets dashboard with signal indicators
- Settings page (API keys, profile management)
- About page with contact info
- Responsive design patterns (mobile-first Tailwind)

**Why important (CRITICAL):**
- Frontend represents 20% of user-facing codebase
- New contributors need to understand form validation, SSE architecture, template organization
- No documentation of Impeccable design system integration
- No guide to component reuse patterns

**Suggested doc page:** `frontend/implementation.md` (400–500 words)
- Overview of 12 templates and their purposes
- SSE architecture for progress streaming
- JavaScript module organization (form handling, auto-refresh, signal visualization)
- Tailwind component library and design tokens

---

#### 2. REST API Endpoint Reference

**What's in code:** 15+ API endpoints across 4 routers

**What's documented:** Overview only in `architecture/overview.md` (2 paragraphs)

**Endpoints NOT documented:**
- `POST /api/v1/auth/register` — User registration with email/password
- `POST /api/v1/auth/login` — User login, returns JWT
- `GET /api/v1/auth/me` — Get current user info
- `POST /api/v1/keys/add` — Add OpenRouter API key (encrypted storage)
- `GET /api/v1/keys` — List user's API keys
- `DELETE /api/v1/keys/{key_id}` — Revoke API key
- `POST /api/v1/keys/validate` — Test OpenRouter API key validity
- `POST /api/v1/predictions` — Create prediction (accepts outlet, target_date, optional preset, optional market_filter)
- `GET /api/v1/predictions/{id}` — Get prediction detail (includes all pipeline steps)
- `GET /api/v1/predictions` — List user's predictions (paginated)
- `GET /api/v1/predictions/{id}/stream` — Server-sent events stream for progress
- `GET /api/v1/outlets` — List supported outlets with metadata (resolution, language, bias)
- `GET /api/v1/health` — Health check (DB, Redis, ARQ status)

**Content of API reference gaps:**
- Request/response schemas (Pydantic models)
- Query parameters and filtering
- Authentication (Bearer token requirement)
- Error codes and status handling
- Rate limiting (if any)
- Example cURLs or HTTP requests
- WebSocket/SSE stream format for progress

**Why important (CRITICAL):**
- Teams integrating Delphi Press as service need endpoint reference
- No OpenAPI/Swagger spec generated
- Query string parameters for outlets endpoint not documented
- Streaming format for `/stream` endpoint unclear

**Suggested doc page:** `api/endpoints.md` (800–1000 words)
- Full endpoint list with methods, paths, status codes
- Auth endpoints (register, login, me)
- Key management endpoints (add, delete, validate)
- Prediction lifecycle endpoints (create, get, list, stream)
- Outlets endpoint with available fields
- Health check endpoint
- Example requests/responses for each

---

#### 3. Database Models and ORM Layer

**What's in code:** 8 SQLAlchemy models in `src/db/models.py`

**What's documented:** Zero

**Models NOT documented:**
- `User` — user accounts, email, password hash
- `UserAPIKey` — encrypted OpenRouter API keys per user
- `Prediction` — main result record (outlet, target_date, status, cost, created_at)
- `PipelineStep` — per-stage results (stage_name, output_data JSON, duration, cost)
- `Headline` — individual headlines (headline, probability, reasoning)
- `Outlet` — metadata about news outlets (name, language, bias, resolution)
- `FeedSource` — RSS feed URLs per outlet
- `RawArticle` — scraped articles (content, published_date, outlet)

**Content:**
- Table relationships and foreign keys
- Column types and constraints
- Unique constraints and indexes
- Enum types (PredictionStatus, PipelineStepStatus, FetchMethod)
- Cascade delete behavior
- Query patterns (filtering, sorting, pagination)

**Why important (CRITICAL):**
- Operators need to understand data model for debugging/analytics
- New features may require schema changes (migration guide missing)
- No documentation of how outlet profiles are stored/cached
- No ER diagram

**Suggested doc page:** `backend/database.md` (600–800 words)
- Entity-relationship diagram (ERD)
- Table descriptions with fields, types, constraints
- Status enums (PredictionStatus: pending, running, completed, failed)
- User authentication flow (register → password hashing → JWT)
- Prediction lifecycle (creation → stage execution → completion)
- Indexes and query optimization notes

---

#### 4. Security Infrastructure

**What's in code:** 3 security modules with 5 major components

**What's documented:** Only mentioned in passing in `appendix/gotchas.md` (1 bullet)

**Components NOT documented:**
- `src/security/csrf.py` — CSRFMiddleware that validates tokens on state-changing requests
- `src/security/jwt.py` — JWT token generation/validation with exp/iat claims
- `src/security/password.py` — bcrypt hashing with salt
- `src/security/encryption.py` — Fernet (symmetric encryption) for API key vault
- Auth dependency in `src/api/dependencies.py` — `get_current_user()`, `require_user()`

**Content:**
- CSRF token generation and validation
- JWT secret key management
- Password hashing and verification
- API key encryption/decryption
- Token expiration logic
- Cookie security flags (httponly, secure, samesite)

**Why important (CRITICAL):**
- Multi-user system with user API keys — security is non-negotiable
- Deployment team needs to understand key rotation
- No documentation of `.fernet_key` generation
- No security audit checklist

**Suggested doc page:** `backend/security.md` (500–700 words)
- CSRF protection mechanism and middleware integration
- JWT token claims and expiration
- Password hashing (bcrypt rounds, salt)
- API key encryption (Fernet symmetric key)
- Environment variable requirements (`secret_key`, `fernet_key`)
- Security best practices (HTTPS, secure cookie flags)

---

#### 5. Application Configuration & Startup

**What's in code:** `src/config.py` (Settings + PRESETS) and `src/main.py` (lifespan management)

**What's documented:** Only in internal docstrings

**Configuration items NOT documented:**
- Preset system (`light` vs `full`) — different LLM models, event thread limits, cost estimates
- Environment variables (30+): `openrouter_api_key`, `redis_url`, `database_url`, `secret_key`, `fernet_key`, `log_level`
- Default settings for dev vs production
- Lifespan setup: database initialization, Redis connection, ARQ pool, profile loading
- Settings inheritance from LLMConfig

**Content:**
- Preset configurations and use cases
- Environment variable list with descriptions
- Default values for dev mode
- Production configuration requirements
- Database initialization and migrations
- Redis and ARQ setup
- Profile loading for market dashboard

**Why important (CRITICAL):**
- Deployment and local development require understanding presets
- No `.env.example` documentation
- Hardcoded "dev-insecure-key-change-in-production-32ch" secret key risk
- New team members confused about which env vars to set

**Suggested doc page:** `backend/configuration.md` (600–800 words)
- Settings hierarchy (LLMConfig → Settings)
- Preset comparison table (light vs full)
- Full environment variable reference (40+ vars)
- Default values for development
- Production checklist (secret_key, fernet_key rotation, log levels)
- Lifespan setup sequence (DB init → Redis → ARQ → profiles)

---

### HIGH — Important Operational Features

#### 6. Worker & Background Job System

**What's in code:** `src/worker.py` (ARQ WorkerSettings + 8 job functions)

**What's documented:** Zero

**Job functions NOT documented:**
- `run_prediction_task()` — main prediction pipeline executor
- `_fetch_and_store_feeds()` — RSS feed fetch/refresh
- `fetch_rss_wire_agencies()` — TASS, Reuters, AP, Bloomberg fetch
- `fetch_rss_global()` — BBC, Al Jazeera, Guardian, etc.
- `fetch_rss_per_outlet()` — outlet-specific feed updates
- `cleanup_old_articles()` — retention cleanup (default 6 months)
- `scrape_pending_articles()` — trafilatura content extraction
- `startup()`, `shutdown()` — worker lifecycle hooks

**Content:**
- ARQ task queue architecture
- Job scheduling and execution model
- Task parameters and result serialization
- Error handling and retry logic
- Job timeout configuration
- Cron job scheduling (if any)
- Worker deployment requirements

**Why important (HIGH):**
- Background jobs are critical for production reliability
- No documentation of how predictions are queued/executed
- Cron jobs for feed refresh not explained
- No troubleshooting guide for stuck jobs

**Suggested doc page:** `backend/workers.md` (500–700 words)
- Overview of ARQ job queue architecture
- Task list with parameters and execution times
- Feed refresh pipeline (wire → global → per-outlet)
- Article scraping and cleanup
- Worker startup/shutdown hooks
- Deployment: single vs multi-worker setup
- Monitoring and debugging stuck tasks

---

#### 7. Data Sources & Feed Discovery

**What's in code:** 6 modules for data collection

**What's documented:** Partially (in collectors.md, but implementation details missing)

**NOT documented:**
- `src/data_sources/rss.py` — RSS parsing (feedparser), deduplication
- `src/data_sources/scraper.py` — Two scrapers (Noop, Trafilatura) with date parsing
- `src/data_sources/web_search.py` — ExaSearch + Jina providers with token bucket rate limiting
- `src/data_sources/wikidata_client.py` — Entity disambiguation via Wikidata (if used)
- `src/data_sources/feed_discovery.py` — Automatic feed URL discovery
- `src/data_sources/outlets_catalog.py` — Hardcoded outlet definitions with RSS URLs

**Content:**
- RSS parsing and deduplication strategy
- HTML content extraction (trafilatura)
- Date parsing for articles
- Web search provider selection (Exa vs Jina)
- Rate limiting per provider
- Entity linking (Wikidata integration)
- Fallback strategies when feeds unavailable

**Why important (HIGH):**
- RSS feed quality directly impacts signal quality
- Scraper errors cause silent data loss (no headlines = empty results)
- Rate limiting on external APIs prevents bans
- New outlets require feed discovery

**Suggested doc page:** `data-collection/sources.md` (600–800 words)
- RSS feed parsing and deduplication
- HTML scraping with trafilatura
- Date/category parsing from articles
- Web search (Exa + Jina) for supplementary signals
- Rate limiting (token bucket, per-provider)
- Feed discovery for new outlets
- Fallback strategies

---

#### 8. Inverse Problem: Bettor Profiling & Clustering

**What's in code:** 5 modules (profiler, clustering, signal, loader, store)

**What's documented:** Partially in `polymarket/inverse.md` (algorithms) but NOT implementation details

**Implementation NOT documented:**
- `src/inverse/profiler.py` — `build_bettor_profiles()` function: Brier Score computation, Bayesian shrinkage, tier classification, recency weighting
- `src/inverse/clustering.py` — `cluster_bettors()` with HDBSCAN, feature matrix construction
- `src/inverse/signal.py` — Online informed consensus computation, coverage shrinkage, extremizing
- `src/inverse/loader.py` — Load profiles from HuggingFace, Parquet, JSON
- `src/inverse/store.py` — Cache profiles locally, Parquet serialization

**Content:**
- Input data format (trade records from HF datasets)
- Profiling algorithm implementation (vectorized)
- Tier classification thresholds
- HDBSCAN clustering parameters
- Online signal computation
- Caching and serialization formats
- Performance metrics (processing time, memory)

**Why important (HIGH):**
- Inverse problem is core research contribution
- No documentation of how to run profiling pipeline
- Scripts missing: `build_bettor_profiles.py`, `hf_build_profiles.py`, `duckdb_build_profiles.py` not explained
- No guide to debugging profiling failures

**Suggested doc page:** `inverse-problem/implementation.md` (800–1000 words)
- Bettor profiling pipeline (input → Brier Score → shrinkage → tier classification)
- Tier classification thresholds (top 20%, middle 50%, bottom 30%)
- HDBSCAN clustering for archetype discovery
- Online signal computation (accuracy-weighted mean)
- Data loading from HF datasets vs Parquet
- Performance optimization (DuckDB bucketing)
- Caching and serialization

---

#### 9. Evaluation Framework

**What's in code:** 3 evaluation modules + 6 evaluation scripts

**What's documented:** Partially (metrics.md covers Brier Score, but NOT implementation)

**NOT documented:**
- `src/eval/metrics.py` — TopicMatch, SemanticSim, StyleMatch implementation
- `src/eval/ground_truth.py` — RSS snapshot collection, Wayback Machine CDX API
- `src/eval/correlation.py` — Spearman correlation, Granger causality
- 6 evaluation scripts (build_profiles, walk_forward, calibration, correlation, etc.)

**Content:**
- TopicMatch algorithm (keyword screening → BERTScore → LLM-as-judge)
- BERTScore thresholds (0.78, 0.60, 0.55)
- Ground truth collection from RSS and Wayback
- Walk-forward validation protocol (burn-in, folds, temporal cutoff)
- DuckDB bucketing for temporal correctness
- Bootstrap CI computation
- Per-market and per-persona Brier Score tracking

**Why important (HIGH):**
- Evaluation is how we measure real performance
- No guide to running retrospective evaluation
- Walk-forward protocol not reproducible without code comments
- Scripts require HuggingFace access, not documented

**Suggested doc page:** `evaluation/implementation.md` (800–1000 words)
- TopicMatch algorithm (3-step: keyword, BERTScore, LLM-arbitration)
- Ground truth sources (RSS snapshots, Wayback Machine)
- Walk-forward validation (burn-in, fold structure, temporal cutoff)
- DuckDB bucketing for temporal correctness
- Brier Score computation and bootstrap CI
- Running evaluation scripts locally
- Interpreting results and diagnostics

---

### MEDIUM — Nice-to-Have Documentation

#### 10. Utility Modules & Helper Functions

**What's in code:** 5 utility modules

**What's documented:** Zero

**Modules:**
- `src/utils/retry.py` — Exponential backoff with jitter (used for LLM retries)
- `src/utils/fuzzy_match.py` — Fuzzy string matching (outlet names, event matching)
- `src/utils/url_validator.py` — URL validation and canonicalization
- `src/api/dependencies.py` — FastAPI dependency injection helpers

**Why MEDIUM:** These are internal tools, not user-facing; but helpful for contributors

**Suggested doc page:** `backend/utilities.md` (300–400 words)
- Retry strategy (exponential backoff formula)
- Fuzzy matching thresholds (used for outlet/market matching)
- URL canonicalization

---

#### 11. Outlet Resolver & Dynamic Outlet Support

**What's in code:** `src/data_sources/outlet_resolver.py` (OutletResolver class)

**What's documented:** Only referenced in passing

**Content:**
- Outlet metadata (language, timezone, editorial bias, resolution)
- Dynamic resolution via Wikidata
- Caching strategy (30-day TTL)
- Fallback to hardcoded catalog

**Why MEDIUM:** Needed for operators adding new outlets

**Suggested doc page:** (part of `data-collection/sources.md` or separate `data-collection/outlets.md`)

---

#### 12. Model Router & Provider Fallback

**What's in code:** `src/llm/router.py` (ModelRouter class)

**What's documented:** Architecture/llm.md covers concept but NOT implementation

**Content:**
- Task-based model assignment (28 task IDs)
- Primary vs fallback model selection
- Exponential backoff retry logic
- HTTP status code handling (429, 500, 502, 503, 504)
- Rate limit headers (Retry-After)

**Why MEDIUM:** Helpful for debugging model failures, cost optimization

**Suggested doc page:** (extend `architecture/llm.md` with "Implementation" section)

---

#### 13. Market Signal Dashboard (MarketSignalService)

**What's in code:** `src/web/market_service.py` (MarketSignalService class + templates)

**What's documented:** Only mentioned in passing on markets.html

**Content:**
- Loading bettor profiles from Parquet/JSON
- Matching predictions to Polymarket markets
- Computing market signals (confidence, dispersion, coverage)
- Rendering cards with signal indicators
- Refresh logic for live updates

**Why MEDIUM:** Useful for understanding dashboard feature

**Suggested doc page:** (part of `frontend/implementation.md`)

---

#### 14. Scripts & CLI Tools

**What's in code:** 10+ scripts in `scripts/` directory

**What's documented:** Only `dry_run.py` mentioned in main CLAUDE.md

**Scripts NOT documented:**
- `dry_run.py` — E2E test without infrastructure
- `build_bettor_profiles.py` — Build Brier Score profiles from HF
- `eval_walk_forward.py` — Walk-forward validation
- `eval_market_calibration.py` — Per-market Brier Score tracking
- `eval_news_correlation.py` — Spearman + Granger correlation
- `duckdb_build_bucketed.py` — Temporal bucketing for walk-forward
- `hf_build_profiles.py` — Download from HuggingFace
- `convert_json_to_parquet.py` — Format conversion
- `download_profiles.py` — Download profiles from server
- Additional evaluation scripts

**Why MEDIUM:** Operators need to run these for evaluation/monitoring

**Suggested doc page:** `operations/scripts.md` (600–800 words)
- Each script: purpose, parameters, example usage
- Output format and interpretation
- Data requirements (HuggingFace API, local parquet)

---

### LOW — Internal Details (Document if Time Permits)

#### 15. LLM Prompt Structure & Customization

**What's in code:** 7 prompt modules in `src/llm/prompts/`

**What's documented:** `appendix/prompts.md` is reference-only (lists file locations, not content)

**Why LOW:** Prompts change frequently; full documentation would require constant updates

**Suggested approach:** Keep reference-style doc + code comments in prompt files

---

#### 16. Test Fixtures & Mock Objects

**What's in code:** Multiple test fixtures, MockLLMClient

**What's documented:** Zero

**Why LOW:** Developers learn from existing tests; full fixture docs unnecessary

---

---

## Gap Summary Table

| Category | Module | Severity | Impact | Estimated Words |
|----------|--------|----------|--------|------------------|
| Frontend | Templates + JS | CRITICAL | UI implementation unclear | 400–500 |
| API | Endpoints reference | CRITICAL | Integration guide missing | 800–1000 |
| Database | SQLAlchemy models | CRITICAL | Data model opaque | 600–800 |
| Security | CSRF/JWT/encryption | CRITICAL | Operations risk | 500–700 |
| Config | Settings + presets | CRITICAL | Deployment unclear | 600–800 |
| Workers | ARQ + background jobs | HIGH | Operations reliability | 500–700 |
| Data | RSS/scraper/web search | HIGH | Signal quality | 600–800 |
| Inverse | Profiling/clustering | HIGH | Research reproducibility | 800–1000 |
| Evaluation | Metrics/scripts | HIGH | Performance measurement | 800–1000 |
| Utilities | Helpers + retry | MEDIUM | Contributor experience | 300–400 |
| Outlets | Outlet resolver | MEDIUM | Operator onboarding | 300–400 |
| LLM | Model router | MEDIUM | Debugging/optimization | 200–300 (extend existing) |
| Markets | Dashboard service | MEDIUM | Feature understanding | 200–300 |
| Scripts | CLI tools | MEDIUM | Operations runbooks | 600–800 |

**Total estimated additional words:** 7,200–9,700 words  
**Current documentation:** ~15,000 words (estimated)  
**Target documentation:** ~22,000–25,000 words

---

## Recommended Implementation Order

### Phase 1: CRITICAL (Must-Have)
1. **Frontend Implementation** (400–500 words)
2. **REST API Reference** (800–1000 words)
3. **Database Schema & Models** (600–800 words)
4. **Security Infrastructure** (500–700 words)
5. **Application Configuration** (600–800 words)

**Effort:** ~4–5 days  
**Impact:** Unblocks 80% of team onboarding

### Phase 2: HIGH (Important)
6. **Worker & Background Jobs** (500–700 words)
7. **Data Sources & Feed Collection** (600–800 words)
8. **Inverse Problem Implementation** (800–1000 words)
9. **Evaluation Framework** (800–1000 words)

**Effort:** ~3–4 days  
**Impact:** Enables operators, improves reproducibility

### Phase 3: MEDIUM (Nice-to-Have)
10. **Utility Modules** (300–400 words)
11. **Outlet Resolver** (300–400 words)
12. **Model Router** (extend existing, 200–300 words)
13. **Market Dashboard** (200–300 words)
14. **Scripts & CLI Tools** (600–800 words)

**Effort:** ~2 days  
**Impact:** Improves developer experience

---

## Documentation Architecture Recommendation

Create new doc structure:

```
docs-site/docs/
├── index.md (existing)
├── architecture/ (existing)
├── delphi-method/ (existing)
├── evaluation/ (existing, extend)
├── polymarket/ (existing)
├── generation/ (existing)
├── appendix/ (existing)
├── dead-ends/ (existing)
├── roadmap/ (existing)
├── data-collection/ (NEW)
│   ├── sources.md
│   └── outlets.md
├── frontend/ (NEW)
│   └── implementation.md
├── backend/ (NEW)
│   ├── api-endpoints.md
│   ├── database.md
│   ├── security.md
│   ├── configuration.md
│   ├── workers.md
│   └── utilities.md
├── inverse-problem/ (NEW)
│   └── implementation.md
└── operations/ (NEW)
    └── scripts.md
```

---

## Metrics & Quality Gates

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Total doc pages | 17 | 25–30 | ❌ |
| API coverage | 0% | 100% | ❌ |
| Database schema doc | 0% | 100% | ❌ |
| Frontend overview | 0% | 100% | ❌ |
| Security guide | <5% | 100% | ❌ |
| Deployment guide | ~50% | 100% | ⚠️  |
| Evaluation scripts | 0% | 100% | ❌ |
| Code example count | 20 | 50+ | ⚠️  |
| Search index coverage | ~60% | >90% | ⚠️  |

---

## Conclusion

**Strengths:**
- Excellent coverage of algorithm, methodology, and research (95%+)
- Dead ends documented (good for preventing rework)
- Architecture decisions explained

**Weaknesses:**
- Operational/implementation details poorly documented
- API not documented (blocker for integration)
- Security infrastructure undocumented (risk)
- No end-to-end deployment guide

**Recommendation:** Prioritize CRITICAL phase (5 docs) for immediate ROI. Target: 22–25K total words of documentation by next release.
