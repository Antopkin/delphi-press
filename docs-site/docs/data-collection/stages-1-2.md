# Stages 1-2: Data Collection & Event Identification

## Stage 1: NewsScout & Structured Data Collection

The first stage of the Delphi Press pipeline aggregates multi-channel signals from diverse sources into a unified dataset for downstream processing.

### Dual-Source Collection Strategy

**NewsScout** implements a two-pronged approach:

**1. RSS Feed Aggregation**
- Parallel loading of 20–30 RSS feeds from global, regional, and thematic sources
- Global sources (Reuters, AP, BBC, Al Jazeera, etc.) — 10–15 feeds
- Regional sources (TASS, RIA for Russian; CNN, NYT for English) — 5–10 feeds  
- Thematic feeds (finance, politics, science) — 5–10 feeds

**2. Web Search**
- Parallel execution of 3–5 search queries via Exa/Jina MCP API
- General query: *major news events {target_date} world*
- Regional query: *news {region_of_outlet} {target_date}*
- Thematic query: *scheduled events politics economy {target_date}*
- Outlet-specific query: *topics covered by {outlet} this week*
- Trending query: *breaking news today {current_date}* (for context)

Both sources are processed in parallel using `asyncio.gather()`. If one source is unavailable (e.g., RSS feed timeout after 30 seconds), the pipeline continues with the other source while logging the error. Critical condition: if both sources are completely unavailable, an exception is raised.

!!! warning "RSS Feed Timeout"
    Timeouts are set conservatively at 30 seconds per feed to avoid blocking the entire collection stage.

### Deduplication & Relevance Scoring

After merging results from both sources, deduplication is performed on URL:

- Each signal's URL is normalized (lowercase, remove trailing slashes)
- On duplicate detection, the signal with higher `relevance_score` is retained

Relevance is calculated based on:

| Source Type | Scoring Basis |
|---|---|
| RSS signals | Publication freshness (date) + source credibility |
| Web search | API `score` field, normalized to [0.0, 1.0] |

**Optional LLM Classification**: Signals without categories trigger LLM classification using `openai/gpt-4o-mini` with batch processing (batches of 20). The prompt requires classification by domain (politics, economy, science, etc.) and extraction of named entities (people, organizations, locations).

### SignalRecord Schema

The output of **NewsScout** is a list of `SignalRecord` objects (100–200 records) defined in `src/schemas/events.py`:

| Field | Type | Purpose |
|---|---|---|
| `id` | str | Unique ID: `sig_{hash8}` |
| `title` | str | Headline (max 500 chars) |
| `summary` | str | Brief summary (max 1000 chars) |
| `url` | str | Source URL |
| `source_name` | str | Source name (Reuters, TASS, BBC, etc.) |
| `source_type` | Enum | RSS, WEB_SEARCH, SOCIAL, WIRE |
| `published_at` | datetime \| None | Publication date/time (UTC) |
| `language` | str | ISO 639-1 code (ru, en, zh, etc.) |
| `categories` | list[str] | Tags/categories (politics, economy, science, etc.) |
| `entities` | list[str] | Named entities (Trump, ECB, NATO, etc.) |
| `relevance_score` | float | Relevance score (0.0–1.0) |

Signal IDs are generated as SHA-256 hashes of the concatenated URL and title, truncated to the first 8 characters. This ensures determinism: the same signal encountered twice receives identical IDs.

Final processing: signals are sorted by `relevance_score` (descending) and capped at 200 records.

---

## Event Calendar: Structured Event Discovery

The second data source in Stage 1, **EventCalendar**, identifies scheduled events for the target date using web search and LLM-driven structuring.

### Event Search Logic

The process unfolds across five stages:

**1. Search Query Generation (5–8 queries)**

- **Politics**: *political events scheduled {date}*, *parliamentary sessions votes {date}*
- **Economics**: *economic data releases {date}*, *central bank meetings {date}*, *earnings reports {date}*
- **Diplomacy**: *international summits meetings {date}*, *UN sessions {date}*
- **Judicial**: *major court hearings verdicts {date}*
- **Culture/Sports**: *major events conferences {date}*

For Russian-language outlets, some queries are duplicated in Russian.

**2. Parallel Web Search** — All queries executed asynchronously via Exa/Jina API

**3. LLM Structuring** — Using `openai/gpt-4o-mini`, extract structured events from raw results with fields: title, description, event_type, certainty, location, participants, potential_impact

**4. Deduplication** — Fuzzy matching by headlines (Levenshtein ratio > 0.8), with matching event type and date

**5. Newsworthiness Ranking** — Using `anthropic/claude-sonnet-4`, rank by `newsworthiness` considering coverage probability in the selected outlet and event exceptionality

### Event Typology & Certainty Levels

Event types span the major domains of public life:

$$\text{EventType} \in \{\text{POLITICAL, ECONOMIC, DIPLOMATIC, JUDICIAL, MILITARY, CULTURAL, SCIENTIFIC, SPORTS, OTHER}\}$$

Each event includes a confidence assessment reflecting information reliability:

| Level | Interpretation |
|---|---|
| **CONFIRMED** | Officially announced (website schedule, press release) |
| **LIKELY** | High probability (on schedule, announced) |
| **POSSIBLE** | Possible (rumors, preliminary announcements) |
| **SPECULATIVE** | Speculative (inferred from patterns: monthly reports) |

### ScheduledEvent Schema

The output of **EventCalendar** is a list of `ScheduledEvent` objects (typically 3–10 per day, up to 50 on high-activity days):

| Field | Type | Purpose |
|---|---|---|
| `id` | str | Unique ID: `evt_{hash}` |
| `title` | str | Event title (max 300 chars) |
| `description` | str | Detailed description (max 500 chars) |
| `event_date` | date | Event date (matches target_date) |
| `event_type` | EventType | Event category (political, economic, etc.) |
| `certainty` | EventCertainty | Confidence level (confirmed/likely/possible/speculative) |
| `location` | str | Location |
| `participants` | list[str] | Key participants/organizations |
| `potential_impact` | str | Potential impact on news agenda |
| `source_url` | str | Source URL |
| `newsworthiness` | float | Newsworthiness score (0.0–1.0) |

A `newsworthiness` value of 1.0 indicates guaranteed top-news placement in the selected outlet.

---

## Outlet Historian: Editorial Profile Analysis

The third Stage 1 data source, **OutletHistorian**, analyzes stylistic characteristics and editorial positioning of the target media outlet based on historical publications.

### Analysis Methodology

Analysis unfolds in three parallel LLM calls:

1. **Headline Style Analysis** — 30 most recent headlines
2. **Writing Style Analysis** — First paragraphs of 10 articles
3. **Editorial Position Analysis** — Full context of 50–100 articles over 30 days

All three calls run simultaneously via `asyncio.gather()`, minimizing total execution time. Model used: `anthropic/claude-sonnet-4` (for linguistic precision).

**Caching**: If a profile was created less than 7 days ago, it's returned from cache without reanalysis. This is justified because media outlets' stylistic characteristics change slowly.

### HeadlineStyle: Form & Content Metrics

Headline style characteristics evaluated for form and content:

| Metric | Type | Description |
|---|---|---|
| `avg_length_chars` | int | Average headline length (characters) |
| `avg_length_words` | int | Average headline length (words) |
| `uses_colons` | bool | Colons for topic/detail separation |
| `uses_quotes` | bool | Quotations in headlines |
| `uses_questions` | bool | Interrogative headlines |
| `uses_numbers` | bool | Frequent numbers (5 reasons...) |
| `capitalization` | str | Style: sentence_case, title_case, all_caps_first_word, lowercase |
| `vocabulary_register` | str | Register: formal, neutral, colloquial, technical, mixed |
| `emotional_tone` | str | Tone: neutral, alarming, optimistic, dramatic, ironic, dry |
| `common_patterns` | list[str] | 3+ recurring patterns (e.g., {Name}: statement...) |

### WritingStyle: Content Characteristics

Stylistic features of article bodies:

| Field | Type | Description |
|---|---|---|
| `first_paragraph_style` | str | inverted_pyramid, narrative, analytical, quote_lead |
| `avg_first_paragraph_sentences` | int | Average sentences in first paragraph |
| `avg_first_paragraph_words` | int | Average words in first paragraph |
| `attribution_style` | str | source_first, source_last, inline |
| `uses_dateline` | bool | Dateline presence (MOSCOW, April 2 —) |
| `paragraph_length` | str | short, medium, long |

*Inverted pyramid* — the classic journalistic style where the most critical information (who-what-where-when) is placed in the first paragraph.

### EditorialPosition: Newsroom Values & Framing

Editorial positioning and preferences determine which topics receive priority and how they're presented:

| Field | Type | Content |
|---|---|---|
| `tone` | ToneProfile | neutral, conservative, liberal, sensationalist, analytical, official, oppositional |
| `focus_topics` | list[str] | Priority topics (domestic politics, Russian economy, etc.) |
| `avoided_topics` | list[str] | Systematically sidelined topics |
| `framing_tendencies` | list[str] | Typical frames: pro_government, market_oriented, human_interest, conflict_frame |
| `source_preferences` | list[str] | Preferred sources (officials, Foreign Ministry, anonymous) |
| `stance_on_current_topics` | dict | Position on key topics (topic: position) |
| `omissions` | list[str] | Systematically omitted topics |

### OutletProfile: Complete Structure

The complete outlet profile combines all three analyses:

| Field | Type | Purpose |
|---|---|---|
| `outlet_name` | str | Canonical outlet name |
| `outlet_url` | str | Primary outlet URL |
| `language` | str | ISO 639-1 code (ru, en, etc.) |
| `headline_style` | HeadlineStyle | Headline metrics object |
| `writing_style` | WritingStyle | Text metrics object |
| `editorial_position` | EditorialPosition | Editorial positioning object |
| `sample_headlines` | list[str] | 10–30 recent headlines |
| `sample_first_paragraphs` | list[str] | 5–10 opening paragraph examples |
| `analysis_period_days` | int | 30 (analysis period) |
| `articles_analyzed` | int | Number of analyzed articles |
| `analyzed_at` | datetime | Analysis timestamp |

The profile is cached in the SQLite `outlet_profiles` table with key `outlet_name` (normalized) and 7-day TTL.

---

## Foresight Collector: Prediction Markets Integration

A supplementary Stage 1.5 data source, **ForesightCollector**, enriches the forecast context with prediction market data.

### Polymarket CLOB API

The primary source is *Polymarket* — a decentralized prediction market platform built on blockchain. Access is via HTTP REST API without authentication requirements.

**Key API Parameters**:
- **URL**: `https://clob.polymarket.com`
- **Endpoints**: `/markets`, `/prices`, `/trades`
- **Rate limit**: ~200 requests per 10 seconds
- **Timeout**: 10 seconds

Market matching uses `conditionId` — a unique blockchain event condition identifier. For example, "Will Trump win 2024?" might have `conditionId = 0x1234...`. This ID serves as the primary join key for data aggregation.

### Collected Market Metrics

For each relevant market, the following metrics are collected:

| Metric | Source | Purpose |
|---|---|---|
| `conditionId` | markets endpoint | Unique identifier |
| `question` | markets | Prediction statement |
| `volume` | prices | Total trading volume |
| `open_interest` | prices | Active positions |
| `bid_price` | prices | Best buy price (YES) |
| `ask_price` | prices | Best sell price (YES) |
| `mid_price` | computed | (bid + ask) / 2 |
| `spread` | computed | ask - bid (liquidity indicator) |
| `resolution_date` | markets | Market closing date |
| `last_updated` | prices | Last update timestamp |

**Spread** (the difference between bid and ask prices) serves as a liquidity indicator: a tight spread signals active trading and participant confidence.

### Graceful Degradation

*Metaculus API* (alternative source) is currently unavailable due to BENCHMARKING-tier access requirements (requested 2026-03-29). The pipeline code is ready for integration but returns an empty list on access attempts.

If Polymarket API is unavailable (HTTP 5xx, timeout, rate limit):

1. Retry with exponential backoff (3 attempts, max 30 sec)
2. On continued errors: log warning and return empty list `[]`
3. Pipeline continues without market data (quality degradation, not critical)

A successful API call returns markets with metrics. Market relevance is determined by matching question/description against EventCalendar events (cosine similarity of embeddings or simple keyword matching).

---

## Stage 2: Event Identification via HDBSCAN Clustering

Stage 2 consolidates 100–200 signals and 3–10 scheduled events into 20 structured event threads via density-based clustering.

### Process Logic

The clustering process unfolds in the following stages:

1. **Text Preparation** — Concatenate title + summary for each SignalRecord
2. **Embedding** — Batch embedding via LLM API (OpenAI embeddings or Voyage AI); result: matrix of shape (N, 1536) where N = signal count
3. **HDBSCAN Clustering** — Density clustering of embeddings in cosine similarity space
4. **LLM Labeling** — For each cluster, generate title and summary via LLM
5. **ScheduledEvent Integration** — Bind scheduled events to clusters via semantic similarity
6. **Scoring** — Compute `significance_score` using multi-factor formula
7. **Ranking** — Select top-20 by significance_score
8. **Trajectory Analysis** — For each thread, analyze current state, momentum, three scenarios
9. **Cross-Impact Matrix** — Assess cross-impacts between event threads

### HDBSCAN Hyperparameters

| Parameter | Value | Interpretation |
|---|---|---|
| `min_cluster_size` | 3 | Minimum cluster size (events mentioned in 3+ signals) |
| `min_samples` | 2 | Minimum neighborhood size for density |
| `metric` | cosine | Distance metric in embedding space |

`min_cluster_size = 3` means a cluster forms only if it contains at least 3 signals with similar embeddings (cosine similarity). This filters noise (random one-or-two-headline matches) and isolates events with sufficient multi-source coverage.

### Significance Score Formula

Event significance is computed as a weighted sum of five components:

$$\text{significance\_score} = 0.30 \times \text{importance} + 0.25 \times \text{cluster\_size\_norm} + 0.20 \times \text{recency} + 0.15 \times \text{source\_diversity} + 0.10 \times \text{entity\_prominence}$$

Components are defined as:

1. **importance** (weight 0.30) — LLM assessment of media importance in the outlet context (0.0–1.0). High value for events guaranteed top-news placement.

2. **cluster_size_norm** (weight 0.25) — Normalized cluster size. If cluster contains $k$ signals and max cluster size is $k_{\max}$, then this component = $k / k_{\max}$ (0.0–1.0). Larger clusters indicate high news activity.

3. **recency** (weight 0.20) — Signal freshness in the cluster. Signals published in the last 24 hours score 1.0. Older signals are penalized exponentially: $\exp(-t / \tau)$ where $t$ = age (days), $\tau = 3$ (time constant).

4. **source_diversity** (weight 0.15) — Number of unique sources in cluster, normalized: $\min(1.0, |\text{sources}| / 5)$. Events covered by 5+ different sources score maximum.

5. **entity_prominence** (weight 0.10) — Count of high-profile entity mentions (heads of state, ECB, UN, etc.) in cluster signals, normalized to [0, 1]. For typical clusters this component is modest but can be decisive for major political events.

### Output: EventThread[]

The clustering result is a list of `EventThread` objects (up to 20 records), ordered by `significance_score`:

| Field | Type | Content |
|---|---|---|
| `id` | str | Unique thread ID |
| `title` | str | Event title (LLM-generated from cluster) |
| `summary` | str | Event thread summary |
| `signal_ids` | list[str] | IDs of constituent signals |
| `scheduled_events` | list[str] | IDs of bound scheduled events |
| `cluster_size` | int | Number of signals in cluster |
| `significance_score` | float | Final significance (0.0–1.0) |
| `sources` | list[str] | Unique signal sources |
| `entities` | list[str] | Aggregated named entities |
| `published_at` | datetime | Oldest signal publication time |
| `last_updated` | datetime | Newest signal publication time |
| `trajectory` | EventTrajectory \| None | Trajectory analysis (Stage 3) |

Each EventThread represents a cohesive set of news items about a single event or process, ready for downstream analysis (Stage 3: trajectory analysis, Stages 4–5: Delphi forecasting).

### Error Handling & Edge Cases

| Situation | Action |
|---|---|
| <10 signals on input | Return as-is + warning; HDBSCAN may not form clusters |
| Embedding API unavailable | Fallback: use simple text distance (Jaccard) |
| 0 clusters found | Treat each signal as separate EventThread |
| LLM JSON parsing fails on labeling | Retry once; use generic title on failure |

!!! note "HDBSCAN Resilience"
    The pipeline continues gracefully if clustering fails or produces fewer clusters than expected. Signal-level granularity is preserved as a fallback.

---

## Pipeline Context Slots

The `PipelineContext` object carries mutable shared state throughout the pipeline. Understanding each slot is critical for integration.

### Stage 1 Slots

**`signals`** (List[SignalRecord])
- **Type**: list of dicts / SignalRecord Pydantic models
- **Cardinality**: 100–200 per prediction
- **Filled by**: NewsScout agent
- **Read by**: EventTrendAnalyzer (Stage 2)
- **Purpose**: Raw signal aggregation from RSS + web search
- **Validation**: Each signal must have url, title, source_name, published_at (UTC), relevance_score in [0, 1]

**`scheduled_events`** (List[ScheduledEvent])
- **Type**: list of dicts / ScheduledEvent models
- **Cardinality**: 3–50 per day
- **Filled by**: EventCalendar agent
- **Read by**: EventTrendAnalyzer (Stage 2) for event thread binding
- **Purpose**: Scheduled events (press conferences, economic data releases, etc.)
- **Validation**: Each must have event_date (matches target_date), event_type, certainty level

**`outlet_profile`** (OutletProfile)
- **Type**: single object (dict or Pydantic model)
- **Cardinality**: 1 per prediction
- **Filled by**: OutletHistorian agent
- **Read by**: All analyst agents (Stage 3), Delphi personas (Stages 4–5), Judge (Stage 6)
- **Purpose**: Editorial positioning, headline/writing style, tone
- **Validation**: Must include headline_style, writing_style, editorial_position; analyzed_at should be recent (< 7 days)

**`foresight_events`** (List[MetaculusQuestion])
- **Type**: list of dicts / Metaculus prediction questions
- **Cardinality**: 0–30 (often empty due to API restrictions)
- **Filled by**: ForesightCollector agent
- **Read by**: Judge (Stage 6) for context enrichment
- **Purpose**: Prediction market data (Metaculus, Polymarket)
- **Validation**: Each must have question, probability, resolution_date

**`foresight_signals`** (List[PolymarketMetric])
- **Type**: list of dicts / market metric objects
- **Cardinality**: 0–50 (depends on market availability)
- **Filled by**: ForesightCollector agent
- **Read by**: Judge (Stage 6)
- **Purpose**: Polymarket CLOB API metrics (bid, ask, volume)
- **Validation**: Each must have conditionId, question, mid_price in [0, 1]

### Stage 2 Slots

**`event_threads`** (List[EventThread])
- **Type**: list of dicts / EventThread models
- **Cardinality**: up to 20
- **Filled by**: EventTrendAnalyzer (Stage 2, via clustering)
- **Read by**: All analyst agents (Stage 3), Delphi personas (Stages 4–5), Judge (Stage 6)
- **Purpose**: Clustered and ranked event threads
- **Validation**: Each must have id, title, significance_score, cluster_size; signal_ids must reference existing signals

### Stage 3 Slots

**`trajectories`** (List[EventTrajectory])
- **Type**: list of dicts / EventTrajectory models
- **Cardinality**: up to 20 (one per event_thread)
- **Filled by**: Analyst agents (GeopoliticalAnalyst, EconomicAnalyst, MediaAnalyst) enrich event_threads with trajectory data
- **Read by**: Judge (Stage 6), Delphi personas (Stages 4–5)
- **Purpose**: Scenarios, momentum, key drivers for each event
- **Validation**: Each must include current_state, momentum, three scenarios (baseline, optimistic/pessimistic, wildcard) with probabilities summing to 1.0

**`cross_impact_matrix`** (CrossImpactMatrix)
- **Type**: single object
- **Cardinality**: 1 per prediction
- **Filled by**: EventTrendAnalyzer (computed during Stage 2)
- **Read by**: Delphi personas (Stages 4–5)
- **Purpose**: Sparse adjacency matrix of event dependencies
- **Validation**: Each impact_score must be in [-1, 1]; source_id and target_id must reference event_threads

### Stages 4–5 Slots

**`round1_assessments`** (List[PersonaAssessment])
- **Type**: list of dicts / PersonaAssessment models
- **Cardinality**: 3–5 (one per successful persona)
- **Filled by**: Five Delphi personas (Realist, Geostrateg, Economist, MediaExpert, DevilsAdvocate) in parallel
- **Read by**: Mediator (Stage 5a)
- **Purpose**: Independent expert judgments from each persona
- **Validation**: Each must have persona_id, predictions[], confidence_self_assessment in [0, 1]

**`mediator_synthesis`** (MediatorSynthesis)
- **Type**: single object
- **Cardinality**: 1 per prediction
- **Filled by**: Mediator agent (Stage 5a)
- **Read by**: All Delphi personas during Round 2
- **Purpose**: Structured synthesis of disagreements, gaps, consensus areas with key questions
- **Validation**: consensus_areas, disputes, gaps must all reference event_thread_ids; key_question must be present for each DisputeArea

**`round2_assessments`** (List[PersonaAssessment])
- **Type**: list of dicts / PersonaAssessment models (with revisions_made, revision_rationale fields)
- **Cardinality**: 3–5 (one per persona that completed Round 2)
- **Filled by**: Five Delphi personas again, informed by mediator_synthesis
- **Read by**: Judge (Stage 6)
- **Purpose**: Revised expert judgments after mediation
- **Validation**: Same as round1_assessments, plus revisions_made[] and revision_rationale must be present

---

## Source Code References

- **Collection stage**: `src/agents/collectors/news_scout.py`, `src/agents/collectors/event_calendar.py`, `src/agents/collectors/outlet_historian.py`, `src/agents/collectors/foresight_collector.py`
- **Event identification**: `src/agents/analysts/event_trend_analyzer.py`
- **Data schemas**: `src/schemas/events.py`, `src/schemas/pipeline.py`
- **API clients**: `src/data_sources/` (RSS, web search, Polymarket)

For complete specifications, see `docs/03-collectors.md` and `docs/04-analysts.md`.
