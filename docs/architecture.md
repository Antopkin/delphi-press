# Pipeline Architecture

> Last updated: 2026-03-28 · Commit: see `git log --oneline -1`
>
> Canonical source: code in `src/agents/orchestrator.py`, `src/llm/router.py`, `src/schemas/pipeline.py`

## 1. Quick Reference

18 agents, 9 stages, 28 LLM task IDs. Orchestrator runs stages sequentially; agents within a stage run parallel or sequential per config.

| Agent | Registry Key | Stage | Task ID(s) | Context Slot(s) | Source |
|---|---|---|---|---|---|
| NewsScout | `news_scout` | 1 COLLECTION | `news_scout_search` | `signals` | `src/agents/collectors/news_scout.py` |
| EventCalendar | `event_calendar` | 1 COLLECTION | `event_calendar`, `event_assessment` | `scheduled_events` | `src/agents/collectors/event_calendar.py` |
| OutletHistorian | `outlet_historian` | 1 COLLECTION | `outlet_historian` | `outlet_profile` | `src/agents/collectors/outlet_historian.py` |
| ForesightCollector | `foresight_collector` | 1 COLLECTION | _(none — pure data)_ | `foresight_events`, `foresight_signals` | `src/agents/collectors/foresight_collector.py` |
| EventTrendAnalyzer | `event_trend_analyzer` | 2 EVENT_ID | `event_clustering`, `trajectory_analysis`, `cross_impact_analysis` | `event_threads`, `trajectories`, `cross_impact_matrix` | `src/agents/analysts/event_trend.py` |
| GeopoliticalAnalyst | `geopolitical_analyst` | 3 TRAJECTORY | `geopolitical_analysis` | `event_threads[].assessments` | `src/agents/analysts/geopolitical.py` |
| EconomicAnalyst | `economic_analyst` | 3 TRAJECTORY | `economic_analysis` | `event_threads[].assessments` | `src/agents/analysts/economic.py` |
| MediaAnalyst | `media_analyst` | 3 TRAJECTORY | `media_analysis` | `event_threads[].assessments` | `src/agents/analysts/media.py` |
| DelphiRealist | `delphi_realist` | 4/5 DELPHI | `delphi_r1_realist`, `delphi_r2_realist` | `round1_assessments`, `round2_assessments` | `src/agents/forecasters/personas.py` |
| DelphiGeostrategist | `delphi_geostrategist` | 4/5 DELPHI | `delphi_r1_geostrateg`, `delphi_r2_geostrateg` | `round1_assessments`, `round2_assessments` | `src/agents/forecasters/personas.py` |
| DelphiEconomist | `delphi_economist` | 4/5 DELPHI | `delphi_r1_economist`, `delphi_r2_economist` | `round1_assessments`, `round2_assessments` | `src/agents/forecasters/personas.py` |
| DelphiMediaExpert | `delphi_media_expert` | 4/5 DELPHI | `delphi_r1_media`, `delphi_r2_media` | `round1_assessments`, `round2_assessments` | `src/agents/forecasters/personas.py` |
| DelphiDevilsAdvocate | `delphi_devils_advocate` | 4/5 DELPHI | `delphi_r1_devils`, `delphi_r2_devils` | `round1_assessments`, `round2_assessments` | `src/agents/forecasters/personas.py` |
| Mediator | `mediator` | 5 DELPHI_R2 | `mediator` | `mediator_synthesis` | `src/agents/forecasters/mediator.py` |
| Judge | `judge` | 6 CONSENSUS | _(deterministic — no LLM)_ | `predicted_timeline`, `ranked_predictions` | `src/agents/forecasters/judge.py` |
| FramingAnalyzer | `framing` | 7 FRAMING | `framing` | `framing_briefs` | `src/agents/generators/framing.py` |
| StyleReplicator | `style_replicator` | 8 GENERATION | `style_generation`, `style_generation_ru`, `style_generation_en` | `generated_headlines` | `src/agents/generators/style_replicator.py` |
| QualityGate | `quality_gate` | 9 QUALITY_GATE | `quality_factcheck`, `quality_style` | `final_predictions` | `src/agents/generators/quality_gate.py` |

---

## 2. Pipeline Stages

Defined in `src/agents/orchestrator.py:58-115` as `Orchestrator.STAGES`.

| # | ProgressStage | Agents | Parallel | min_successful | Timeout |
|---|---|---|---|---|---|
| 1 | `COLLECTION` | news_scout, event_calendar, outlet_historian, foresight_collector | Yes | 2/4 | 600s |
| 2 | `EVENT_IDENTIFICATION` | event_trend_analyzer | No | — | 300s |
| 3 | `TRAJECTORY` | geopolitical_analyst, economic_analyst, media_analyst | Yes | 2/3 | 600s |
| 4 | `DELPHI_R1` | 5 delphi_* personas | Yes | 4/5 | 600s |
| 5 | `DELPHI_R2` | mediator (seq) → 5 delphi_* personas (par, min=4) | Mixed | 4/5 | 900s |
| 6 | `CONSENSUS` | judge (6a: timeline, 6b: headlines) | No | — | 300s |
| 7 | `FRAMING` | framing | No | — | 300s |
| 8 | `GENERATION` | style_replicator | No | — | 300s |
| 9 | `QUALITY_GATE` | quality_gate | No | — | 300s |

**Stage 5 special logic**: `StageDefinition` lists only `["mediator"]`, but `_run_delphi_r2()` (line ~249) has custom two-phase logic: runs mediator sequentially first, then runs all 5 persona agents in parallel with `min_successful=4`. If mediator fails, the entire stage aborts.

---

## 3. LLM Task IDs

Defined in `src/llm/router.py:28-221` as `DEFAULT_ASSIGNMENTS`. All tasks default to `max_tokens=4096`.

### Collectors

| Task ID | Agent | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| `news_scout_search` | NewsScout | gemini-3.1-flash-lite | gemini-2.5-flash | 0.3 | No |
| `event_calendar` | EventCalendar | gemini-3.1-flash-lite | gemini-2.5-flash | 0.3 | Yes |
| `event_assessment` | EventCalendar | claude-opus-4.6 | claude-sonnet-4.5 | 0.4 | Yes |
| `outlet_historian` | OutletHistorian | claude-opus-4.6 | claude-sonnet-4.5 | 0.4 | Yes |

### Analysts

| Task ID | Agent | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| `event_clustering` | EventTrendAnalyzer | gemini-3.1-flash-lite | gemini-2.5-flash | 0.2 | Yes |
| `trajectory_analysis` | EventTrendAnalyzer | claude-opus-4.6 | claude-sonnet-4.5 | 0.6 | Yes |
| `cross_impact_analysis` | EventTrendAnalyzer | claude-opus-4.6 | claude-sonnet-4.5 | 0.4 | Yes |
| `geopolitical_analysis` | GeopoliticalAnalyst | claude-opus-4.6 | claude-sonnet-4.5 | 0.5 | Yes |
| `economic_analysis` | EconomicAnalyst | claude-opus-4.6 | claude-sonnet-4.5 | 0.5 | Yes |
| `media_analysis` | MediaAnalyst | claude-opus-4.6 | claude-sonnet-4.5 | 0.5 | Yes |

### Delphi R1

| Task ID | Persona | Temp | JSON |
|---|---|---|---|
| `delphi_r1_realist` | REALIST | 0.7 | Yes |
| `delphi_r1_geostrateg` | GEOSTRATEG | 0.7 | Yes |
| `delphi_r1_economist` | ECONOMIST | 0.7 | Yes |
| `delphi_r1_media` | MEDIA_EXPERT | 0.7 | Yes |
| `delphi_r1_devils` | DEVILS_ADVOCATE | 0.9 | Yes |

All R1: primary `claude-opus-4.6`, fallback `claude-sonnet-4.5`.

### Mediator + Delphi R2

| Task ID | Agent/Persona | Temp | JSON |
|---|---|---|---|
| `mediator` | Mediator | 0.5 | Yes |
| `delphi_r2_realist` | REALIST | 0.6 | Yes |
| `delphi_r2_geostrateg` | GEOSTRATEG | 0.6 | Yes |
| `delphi_r2_economist` | ECONOMIST | 0.6 | Yes |
| `delphi_r2_media` | MEDIA_EXPERT | 0.6 | Yes |
| `delphi_r2_devils` | DEVILS_ADVOCATE | 0.6 | Yes |

All R2: primary `claude-opus-4.6`, fallback `claude-sonnet-4.5`.

### Judge + Generators

| Task ID | Agent | Primary Model | Fallback | Temp | JSON |
|---|---|---|---|---|---|
| ~~`judge`~~ | Judge | _(deterministic since v0.7.0 — no LLM call)_ | — | — | — |
| `framing` | FramingAnalyzer | claude-opus-4.6 | claude-sonnet-4.5 | 0.5 | Yes |
| `style_generation` | StyleReplicator | yandexgpt | claude-opus-4.6 | 0.8 | No |
| `style_generation_ru` | StyleReplicator | yandexgpt | claude-opus-4.6 | 0.8 | No |
| `style_generation_en` | StyleReplicator | claude-opus-4.6 | claude-sonnet-4.5 | 0.8 | No |
| `quality_factcheck` | QualityGate | claude-opus-4.6 | claude-sonnet-4.5 | 0.2 | Yes |
| `quality_style` | QualityGate | yandexgpt | claude-opus-4.6 | 0.3 | Yes |

---

## 4. Data Flow — PipelineContext Slots

Defined in `src/schemas/pipeline.py`. Merge logic: `PipelineContext.merge_agent_result()` (line 196).

| Slot | Type | Written by | Read by | Stage |
|---|---|---|---|---|
| `signals` | `list[SignalRecord]` | NewsScout | EventTrendAnalyzer | 1→2 |
| `scheduled_events` | `list[ScheduledEvent]` | EventCalendar | EventTrendAnalyzer | 1→2 |
| `outlet_profile` | `OutletProfile` | OutletHistorian | MediaAnalyst, FramingAnalyzer, StyleReplicator, QualityGate | 1→3,7,8,9 |
| `foresight_events` | `list` | ForesightCollector | EventTrendAnalyzer | 1→2 |
| `foresight_signals` | `list` | ForesightCollector | EventTrendAnalyzer | 1→2 |
| `event_threads` | `list[EventThread]` | EventTrendAnalyzer | Analysts (enrich), Delphi personas | 2→3,4,5 |
| `trajectories` | `list[EventTrajectory]` | EventTrendAnalyzer | Delphi personas | 2→4,5 |
| `cross_impact_matrix` | `CrossImpactMatrix` | EventTrendAnalyzer | Delphi personas, Mediator | 2→4,5 |
| `round1_assessments` | `list[PersonaAssessment]` | 5 Delphi personas (R1) | Mediator | 4→5 |
| `mediator_synthesis` | `MediatorSynthesis` | Mediator | Delphi personas (R2), Judge | 5→5,6 |
| `round2_assessments` | `list[PersonaAssessment]` | 5 Delphi personas (R2) | Judge | 5→6 |
| `predicted_timeline` | `PredictedTimeline` | Judge (6a) | _(persisted for eval, not consumed by stages 7-9)_ | 6a |
| `ranked_predictions` | `list[RankedPrediction]` | Judge (6b) | FramingAnalyzer, StyleReplicator, QualityGate | 6b→7,8,9 |
| `framing_briefs` | `list[FramingBrief]` | FramingAnalyzer | StyleReplicator, QualityGate | 7→8,9 |
| `generated_headlines` | `list[GeneratedHeadline]` | StyleReplicator | QualityGate | 8→9 |
| `final_predictions` | `list[FinalPrediction]` | QualityGate | Orchestrator._build_response() | 9→output |
| `stage_results` | `list[StageResult]` | Orchestrator | Orchestrator._build_response() | all→output |

### Merge routing (pipeline.py:221-295)

| Agent name pattern | Merge strategy |
|---|---|
| `news_scout`, `event_calendar`, `framing`, `style_replicator`, `quality_gate` | Direct slot mapping: `data[slot_name]` → `context.slot` |
| `judge` | Multi-key: `data["ranked_predictions"]` + `data["predicted_timeline"]` |
| `outlet_historian` | Direct: `data["outlet_profile"]` → `context.outlet_profile` |
| `foresight_collector` | Multi-key: `data["foresight_events"]` + `data["foresight_signals"]` |
| `event_trend_analyzer` | Multi-key: `data["event_threads"]` + `data["trajectories"]` + `data["cross_impact_matrix"]` |
| `delphi_*` | Branch: `"revised_assessment"` in data → `round2_assessments`; else `"assessment"` → `round1_assessments` |
| `mediator` | Direct: `data["synthesis"]` → `context.mediator_synthesis` |
| `*_analyst` | Enrich: iterate `data["assessments"]`, match `thread_id`, add to `event_threads[i].assessments[agent_name]` |

---

## 5. Collector Dependencies

Registry built in `src/agents/registry.py:build_default_registry()`.

| Collector | Dependencies (Protocol) | Implementation | Data Sources |
|---|---|---|---|
| NewsScout | `RSSFetcherProto`, `WebSearchProto`, `OutletCatalogProto` | `src/data_sources/rss.py`, `src/data_sources/web_search.py`, `src/data_sources/outlet_resolver.py` | RSS feeds + web search |
| EventCalendar | `WebSearchProto` | `src/data_sources/web_search.py` | Web search queries |
| OutletHistorian | `ArticleScraperProto`, `OutletCatalogProto`, `ProfileCacheProto` | `src/data_sources/scraper.py`, `src/data_sources/outlet_resolver.py`, `src/data_sources/profile_cache.py` | Article scraping, 7-day TTL cache |
| ForesightCollector | `MetaculusClientProto`, `PolymarketClientProto`, `GdeltClientProto` | All in `src/data_sources/foresight.py` | Metaculus API, Polymarket API, GDELT API |

**Note**: ForesightCollector is only registered if all three foresight clients are present in `collector_deps`.

**OutletResolver** (pre-Stage 1): Worker создаёт `OutletResolver` как drop-in replacement для `OutletsCatalog`. Resolver реализует `OutletCatalogProto` (sync `get_outlet()`, `get_rss_feeds()`) + async `resolve()` для enrichment. Цепочка: static catalog (20 outlets) → DB cache (TTL 30d) → Wikidata SPARQL + RSS autodiscovery. Файлы: `src/data_sources/outlet_resolver.py`, `src/data_sources/wikidata_client.py`, `src/data_sources/feed_discovery.py`.

---

## 6. Schema Files

| File | Key Models | Used by Stages |
|---|---|---|
| `src/schemas/agent.py` | AgentResult, StageResult, PersonaAssessment, MediatorSynthesis, PredictionItem, ScenarioType (re-export) | All |
| `src/schemas/events.py` | SignalRecord, ScheduledEvent, OutletProfile, EventThread, EventTrajectory, CrossImpactMatrix, ScenarioType (canonical), *Assessment | 1-5 |
| `src/schemas/headline.py` | RankedPrediction, FramingBrief, GeneratedHeadline, FinalPrediction, QualityScore | 6-9 |
| `src/schemas/pipeline.py` | PipelineContext (shared mutable state, 16 slots, merge logic) | All |
| `src/schemas/llm.py` | LLMMessage, LLMResponse, ModelAssignment, CostRecord | All (via LLM client) |
| `src/schemas/prediction.py` | PredictionRequest, PredictionResponse, HeadlineOutput | Input/Output |
| `src/schemas/progress.py` | ProgressStage, SSEProgressEvent, STAGE_PROGRESS_MAP | Orchestrator |

---

## 7. Known Gotchas

### 7.1 Dict vs Pydantic everywhere

Context slots are typed `list[Any]`. Agents write `model_dump()` dicts, but downstream agents may receive either dicts or Pydantic models. Every consuming agent must handle both: `isinstance(raw, dict)` check + `Model.model_validate(raw)`.

**Affected**: every agent's `execute()`, `Orchestrator._get_field()` helper.

### 7.2 max_tokens=4096 default for all tasks

`ModelAssignment` defaults to `max_tokens=4096`. Delphi persona assessments with 5-15 PredictionItems (~200 tokens each) can exceed this. If truncated, `parse_response()` returns `None` → agent falls back to empty data. Check `finish_reason="length"` in logs.

**Affected**: `src/schemas/llm.py::ModelAssignment`, `src/llm/router.py::DEFAULT_ASSIGNMENTS`.

### 7.3 EventTrendAnalyzer fills 3 context slots

Despite being Stage 2, it fills `event_threads`, `trajectories`, AND `cross_impact_matrix` — the latter two logically belong to Stage 3. Stage 3 analysts read these and also enrich `event_threads` with their own assessments.

**Affected**: `src/agents/analysts/event_trend.py`, `src/schemas/pipeline.py:254-266`.

### 7.4 Stage 5 definition is misleading

`StageDefinition` lists only `["mediator"]` in `agent_names`, but `_run_delphi_r2()` also runs 5 persona agents via custom logic that bypasses normal `_run_stage()` flow.

**Affected**: `src/agents/orchestrator.py:249-329`.

### 7.5 Round detection via mediator_synthesis presence

`DelphiPersonaAgent.execute()` determines `round_number` by checking `context.mediator_synthesis is not None`. If mediator fails → synthesis is None → R2 personas think they're in R1.

**Affected**: `src/agents/forecasters/personas.py`.

### 7.6 ForesightCollector never calls LLM

Pure data-collection agent. Accepts `llm_client` (BaseAgent contract) but never uses it. Cost is always $0. Foresight APIs may be unreliable (GDELT parse errors on Cyrillic queries). Metaculus uses `/api/posts/` with optional Token auth. Graceful degradation — never raises.

**Affected**: `src/agents/collectors/foresight_collector.py`, `src/data_sources/foresight.py`.

### 7.7 StyleReplicator selects task by outlet language

Russian outlets → `style_generation_ru` (YandexGPT), English → `style_generation_en` (Claude). Language comes from `OutletProfile.language`. If `outlet_profile` is None or has wrong language, wrong LLM task is used.

**Affected**: `src/agents/generators/style_replicator.py`.

### 7.8 YandexGPT is a stub

`src/llm/providers.py` — waiting for `yandex-cloud-ml-sdk`. OpenRouter fallback works for all tasks.

### 7.9 Budget default is $50

`LLMConfig.max_budget_usd = 50`. A single Opus prediction costs $5-15. `BudgetTracker` raises `BudgetExceededError` if exceeded.

**Affected**: `src/llm/config.py`, `src/llm/budget.py`.

### 7.10 Delphi persona weights

Initial weights (for future weighted aggregation): REALIST=0.22, GEOSTRATEG=0.20, ECONOMIST=0.20, MEDIA_EXPERT=0.18, DEVILS_ADVOCATE=0.20. Currently not used by Judge — equal weight aggregation.

**Affected**: `src/agents/forecasters/personas.py::PERSONAS`.

### 7.11 ScenarioType is a unified enum

Single `ScenarioType` defined in `src/schemas/events.py`, re-exported from `src/schemas/agent.py`. Values: BASELINE, OPTIMISTIC, PESSIMISTIC, BLACK_SWAN, WILDCARD. Judge checks `BLACK_SWAN` for wild card selection.

### 7.12 QualityGate REVISE → drop

V1 behavior: headlines with `REVISE` gate decision are dropped, not re-generated. No iterative revision cycle exists yet.

**Affected**: `src/agents/generators/quality_gate.py`.
