# Stage 3: Trajectory Analysis & Assessments

## Three Parallel Analyst Agents

At Stage 3 (Trajectory Analysis), event threads identified by `EventTrendAnalyzer` flow into three specialized analytical agents working in **parallel**:

1. **GeopoliticalAnalyst** — Strategic actors, power dynamics, escalation probability, military and sanction implications
2. **EconomicAnalyst** — Affected economic indicators, market impacts, supply chains, fiscal implications
3. **MediaAnalyst** — Event media value assessment through six-dimensional Galtung & Ruge (1965) framework

Each analyst produces an assessment (`GeopoliticalAssessment`, `EconomicAssessment`, `MediaAssessment`) for every event thread. Minimum successful analysts: 2 out of 3; the architecture tolerates failure of one analyst.

### GeopoliticalAnalyst

**File**: `src/agents/analysts/geopolitical.py`

**LLM Model**: `anthropic/claude-opus-4.6` (primary, fallback: claude-sonnet-4.5)

For each event thread, the agent constructs a profile of strategic actors and power relationships:

- **Strategic actors** (2–5 per thread): States, alliances (NATO, SCO), international organizations (UN, EU, WTO)
  - Each actor has: name, role (initiator/target/mediator/ally/observer/spoiler), interests, likely actions, leverage points
- **Power dynamics**: Description of relative strength and positioning
- **Alliance shifts**: Possible realignment or coalition changes
- **Escalation probability** (0–1): Numeric forecast for military/diplomatic escalation
- **Second-order effects** (3–5): Causal chains showing cascading reactions between actors
- **Sanctions risk**: Assessment level (none/low/medium/high/imminent)
- **Military implications**: If applicable to the event
- **Headline angles**: Geopolitical framing opportunities for news outlets

**Output**: `GeopoliticalAssessment` schema (see below).

### EconomicAnalyst

**File**: `src/agents/analysts/economic.py`

**LLM Model**: `anthropic/claude-opus-4.6` (primary, fallback: claude-sonnet-4.5)

For each event thread, the agent forecasts economic impacts:

- **Affected indicators** (list): Currency pairs, commodity prices (oil, metals), stock indices, bond spreads
  - Each indicator: name, direction (up/down/neutral/volatile), magnitude (low/medium/high), confidence (0–1), timeframe (immediate/days/weeks/months)
- **Market impact**: Overall market direction (strongly_negative → strongly_positive)
- **Affected sectors**: Which industries face direct exposure
- **Supply chain impact**: Geographic breaks, production/logistics disruptions
- **Fiscal calendar events**: Related government budget/policy events
- **Central bank signals**: Policy adjustments or forward guidance triggered
- **Trade flow impact**: Changes to import/export volumes and routes
- **Commodity prices**: Specific commodity markets affected
- **Employment impact**: Labor market effects
- **Headline angles**: Economic framing opportunities

**Output**: `EconomicAssessment` schema (see below).

### MediaAnalyst

**File**: `src/agents/analysts/media.py`

**LLM Model**: `anthropic/claude-opus-4.6` (primary, fallback: claude-sonnet-4.5)

Unique to this agent: it receives the target outlet's `OutletProfile` (from Stage 1) to assess coverage likelihood for that **specific outlet**, not just generic newsworthiness.

For each event thread, relative to the outlet, the agent assesses:

- **Newsworthiness** (six dimensions, Galtung & Ruge 1965):
  - **Timeliness** (0–1): Event occurs now, not archived
  - **Impact** (0–1): Scale of affected persons/assets/systems
  - **Prominence** (0–1): Known figures, celebrities, industry leaders involved
  - **Proximity** (0–1): Geographic, cultural, or thematic closeness to outlet's audience
  - **Conflict** (0–1): Presence of explicit opposition, tension, or emotional charge
  - **Novelty** (0–1): Event is unexpected, radically different from precedent
- **Editorial fit** (0–1): Alignment with outlet's editorial line (from profile)
- **Editorial fit explanation**: Why the story fits or doesn't fit
- **News cycle position**: breaking/developing/emerging/declining
- **Saturation** (0–1): How long topic has been in news (>14 days straight → newsroom seeks fresh angle)
- **Coverage probability** (0–1): Forecast of publication likelihood for this outlet
- **Predicted prominence**: Where story would appear if covered (top_headline/major/secondary/brief/ignore)
- **Likely framing**: Expected angle/tone for this outlet
- **Competing stories**: Other stories competing for space on target date
- **Headline angles**: Framing opportunities tailored to outlet voice

**Output**: `MediaAssessment` schema (see below).

---

## Trajectory Modeling

After parallel analysis, each event thread receives an `EventTrajectory` describing its development path.

### EventTrajectory Schema

| Field | Type | Purpose |
|---|---|---|
| `thread_id` | str | Reference to `EventThread.id` |
| `current_state` | str | Current situation description (2–3 sentences) |
| `momentum` | str | Development vector: escalating, stable, de_escalating, emerging, culminating, fading |
| `momentum_explanation` | str | Why the event has this momentum |
| `scenarios` | list[Scenario] | 2–4 scenario variants; min 2, max 4 |
| `key_drivers` | list[str] | 3–5 forces determining development |
| `uncertainties` | list[str] | 2–3 major uncertainty points |

**Momentum** describes short-term development:

- **escalating**: Situation intensifies; crisis likelihood rises
- **stable**: Status quo maintained; no major changes expected
- **de_escalating**: Tension declining; crisis has passed peak
- **emerging**: New event just appearing in media space
- **culminating**: Event approaching critical point, resolution, climax
- **fading**: Event losing topicality; media attention falling

### Scenario Schema

Each `Scenario` in the `scenarios` list contains:

| Field | Type | Purpose |
|---|---|---|
| `scenario_type` | ScenarioType | baseline, optimistic, pessimistic, black_swan, wildcard |
| `description` | str | Scenario summary (2–3 sentences) |
| `probability` | float | Assigned probability (0.0–1.0); sum across all scenarios = 1.0 |
| `key_indicators` | list[str] | 2–3 signs pointing to scenario realization |
| `headline_potential` | str | Possible headline this scenario could generate |

**Scenario Types** (5 total):

1. **BASELINE** — Most likely development given current trajectory
2. **OPTIMISTIC** — Situation improves on key parameters
3. **PESSIMISTIC** — Situation deteriorates
4. **BLACK_SWAN** — Extreme, previously unthinkable turn
5. **WILDCARD** — Surprising but plausible development requiring activation of identified risks

!!! note
    Probabilities across all scenarios must sum to 1.0. The framework supports 2–4 scenarios per thread (typically 3).

---

## Cross-Impact Matrix

Events in information space are not independent. One event's development affects others' probability, creating feedback loops.

The cross-impact matrix is built as a **sparse representation** — only meaningful connections included:

$$\text{CrossImpactEntry:} \quad (\text{source\_thread\_id}, \text{target\_thread\_id}, \text{impact\_score}) \in \mathbb{R}$$

where:

- **source_thread_id** — causal event ID
- **target_thread_id** — consequence event ID
- **impact_score** $\in [-1.0, 1.0]$ — influence strength and direction:
  - $> 0$ — reinforcing influence (source accelerates, makes target more likely)
  - $< 0$ — dampening influence (source slows, makes target less likely)
  - $= 0$ — no influence (typically omitted from matrix)

For a typical 20-event portfolio, the full matrix has $20 \times 19 = 380$ potential pairs. In practice, 30–50 meaningful connections exist. This sparsity is critical for Delphi scalability.

### CrossImpactMatrix Schema

| Field | Type | Purpose |
|---|---|---|
| `entries` | list[CrossImpactEntry] | Sparse impact relationships (empty list if <2 threads) |
| `generated_at` | datetime | Timestamp of matrix generation (UTC) |

where `CrossImpactEntry` contains:

| Field | Type | Purpose |
|---|---|---|
| `source_thread_id` | str | ID of causal event thread |
| `target_thread_id` | str | ID of consequence event thread |
| `impact_score` | float | Influence magnitude $\in [-1.0, 1.0]$ |
| `explanation` | str | Brief explanation of causal mechanism |

---

## Assessment Schemas

### NewsworthinessScore

Six-dimensional assessment used by `MediaAnalyst`:

| Dimension | Field | Range | Meaning |
|---|---|---|---|
| 1 | `timeliness` | [0, 1] | Event occurs now vs. archived |
| 2 | `impact` | [0, 1] | Scale of affected persons/assets |
| 3 | `prominence` | [0, 1] | Known figures involved |
| 4 | `proximity` | [0, 1] | Geographic/cultural closeness to audience |
| 5 | `conflict` | [0, 1] | Presence of opposition/tension |
| 6 | `novelty` | [0, 1] | Unexpectedness; departure from precedent |

**Composite score** (weighted average):

$$\text{composite} = 0.25 \times \text{impact} + 0.20 \times \text{timeliness} + 0.20 \times \text{prominence} + 0.15 \times \text{conflict} + 0.10 \times \text{proximity} + 0.10 \times \text{novelty}$$

### GeopoliticalAssessment

Output schema of `GeopoliticalAnalyst`:

| Field | Type | Purpose |
|---|---|---|
| `thread_id` | str | Reference to `EventThread.id` |
| `strategic_actors` | list[StrategicActor] | 2–5 key geopolitical players |
| `power_dynamics` | str | Description of relative strength |
| `alliance_shifts` | list[str] | Possible coalition realignments |
| `escalation_probability` | float | [0, 1] probability of escalation |
| `second_order_effects` | list[str] | 3–5 cascading effects |
| `sanctions_risk` | str | none/low/medium/high/imminent |
| `military_implications` | str | Military consequences (if applicable) |
| `headline_angles` | list[str] | Geopolitical framing opportunities |

where `StrategicActor` contains:

| Field | Type | Purpose |
|---|---|---|
| `name` | str | Actor name (country, leader, organization) |
| `role` | str | initiator/target/mediator/ally/observer/spoiler |
| `interests` | list[str] | Key interests at stake |
| `likely_actions` | list[str] | Probable near-term moves |
| `leverage` | str | Economic/military/diplomatic/information tools |

### EconomicAssessment

Output schema of `EconomicAnalyst`:

| Field | Type | Purpose |
|---|---|---|
| `thread_id` | str | Reference to `EventThread.id` |
| `affected_indicators` | list[EconomicIndicator] | Markets/indices impacted |
| `market_impact` | str | Overall market direction assessment |
| `affected_sectors` | list[str] | Industries with exposure |
| `supply_chain_impact` | str | Logistics/production disruptions |
| `fiscal_calendar_events` | list[str] | Related government events |
| `central_bank_signals` | list[str] | Policy/guidance adjustments |
| `trade_flow_impact` | str | Changes to import/export flows |
| `commodity_prices` | list[str] | Specific commodities affected |
| `employment_impact` | str | Labor market effects |
| `headline_angles` | list[str] | Economic framing opportunities |

where `EconomicIndicator` contains:

| Field | Type | Purpose |
|---|---|---|
| `name` | str | Indicator name (e.g., "EUR/USD") |
| `direction` | str | up/down/neutral/volatile |
| `magnitude` | str | low/medium/high |
| `confidence` | float | [0, 1] confidence in direction forecast |
| `timeframe` | str | immediate/days/weeks/months |

### MediaAssessment

Output schema of `MediaAnalyst`:

| Field | Type | Purpose |
|---|---|---|
| `thread_id` | str | Reference to `EventThread.id` |
| `newsworthiness` | NewsworthinessScore | 6-dimensional assessment |
| `editorial_fit` | float | [0, 1] alignment with outlet editorial |
| `editorial_fit_explanation` | str | Why story fits or doesn't fit |
| `news_cycle_position` | str | breaking/developing/emerging/declining |
| `saturation` | float | [0, 1] how long in news cycle |
| `coverage_probability` | float | [0, 1] likelihood of publication |
| `predicted_prominence` | str | top_headline/major/secondary/brief/ignore |
| `likely_framing` | str | Expected angle/tone for outlet |
| `competing_stories` | list[str] | Other stories competing for space |
| `headline_angles` | list[str] | Framing opportunities for outlet voice |

---

## Source Code References

- **GeopoliticalAnalyst**: `src/agents/analysts/geopolitical.py`
- **EconomicAnalyst**: `src/agents/analysts/economic.py`
- **MediaAnalyst**: `src/agents/analysts/media.py`
- **EventTrendAnalyzer** (trajectories + cross-impact): `src/agents/analysts/event_trend.py`
- **All schemas**: `src/schemas/events.py`
- **LLM model routing**: `src/llm/router.py` (lines 77–97)

For specifications and prompts, see `docs/04-analysts.md` (§3–5: Analyst specifications, §2: Trajectory Analysis).
