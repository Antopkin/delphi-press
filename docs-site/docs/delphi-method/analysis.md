# Stage 3: Trajectory Analysis & Three Scenarios

## Three Parallel Analyst Agents

At Stage 3, events identified by EventTrendAnalyzer flow into three specialized analytical agents working in **parallel**:

1. **Geopolitical Analyst** — Analysis of strategic actors, balance of power, alliances, escalation probability
2. **Economic Analyst** — Analysis of capital flows, market indicators, supply chains, scenario impacts on indices
3. **Media Analyst** — Assessment of event media value through the six-dimensional Galtung & Ruge (1965) framework

Minimum successful analysts: $\text{min\_successful} = 2$ out of 3. The architecture tolerates failure of one analyst without canceling the Delphi forecast.

### Geopolitical Analysis

For each event, a profile of key strategic actors is constructed:

- **Strategic actors**: States, alliances (NATO, SCO), international organizations (UN, EU)
- **Balance of power**: Relative strength, directional shifts in positioning (who strengthens, who weakens)
- **Escalation probability**: For conflicts, diplomatic crises — numeric assessment (0–1)
- **Second-order effects**: Causal chains showing how one actor's move triggers another's response

The analytical framework combines neorealism (system structure determines actor behavior) with constructivism (threat perception depends on identity and narrative).

### Economic Analysis

For each event:

- **Affected indicators**: Currency pairs, commodity prices, stock indices, bond spreads
- **Fiscal consequences**: Relationships to government budget policies
- **Supply chains**: Geographic breaks, sectors vulnerable to escalation or stabilization
- **Market signal**: What markets already price in vs. what remains a surprise

Core principle: *Follow the money* — economic incentives reveal actors' true intentions and constraints.

### Media Analysis: Six-Dimensional Newsworthiness Framework

Event newsworthiness is evaluated by six criteria (Galtung & Ruge, 1965):

1. **Timeliness** (timeliness) — Event occurs now, not archived
2. **Magnitude** (scale) — Is the event large in affected persons or assets
3. **Prominence** (notability) — Are top figures, familiar to audience, involved
4. **Proximity** (closeness) — Geographic, cultural, thematic closeness to outlet audience
5. **Conflict** (conflict) — Presence of explicit opposition, emotional charge
6. **Novelty** (novelty) — Event is unexpected, radically differs from precedent

Additionally, the media analyst assesses:

- **Editorial fit** (0–1): Event alignment with outlet editorial line
- **Media saturation** (0–1): How long topic has been in news. If > 14 days straight — newsroom seeks fresh angle or withdraws
- **Cycle position**: Is topic at peak attention, declining, or in rising trend

Output: `MediaAssessment` with overall newsworthiness score and coverage probability forecast for the outlet.

---

## Trajectory Modeling

After parallel analysis, each event receives a trajectory model describing its development path. The trajectory captures:

1. **Current state** — Where the event stands now (2–3 sentences)
2. **Momentum** — Development vector
3. **Three scenarios** — BASELINE, OPTIMISTIC/PESSIMISTIC, WILDCARD
4. **Key drivers** — 3–5 forces determining development
5. **Uncertainties** — 2–3 major uncertainty points

### Event Momentum

Momentum describes the event thread's short-term development vector:

- **Escalating** — Situation intensifies; crisis likelihood rises
- **Stable** — Status quo maintained; no major changes expected
- **De-escalating** — Tension declining; crisis has passed peak
- **Emerging** — New event just appearing in media space
- **Culminating** — Event approaching critical point, resolution, climax
- **Fading** — Event losing topicality; media attention falling

### Three Scenario Development

For each event, three scenarios are defined with:

- Brief description (2–3 sentences)
- Assigned probability (0.0–1.0); sum across three scenarios = 1.0
- 2–3 key indicators pointing to scenario realization
- Potential headline the scenario could generate

**Scenario types**:

1. **BASELINE** — Most likely development based on current momentum
2. **OPTIMISTIC** or **PESSIMISTIC** — Situation improvement or deterioration on key parameters
3. **WILDCARD** — Surprising turn requiring activation of identified risks

### Cross-Impact Matrix

Events in information space are not independent. One event's development affects others' probability.

The cross-impact matrix is built as sparse representation:

$$\text{CrossImpactEntry:} \quad (source\_id, target\_id, impact\_score) \in [-1, 1] \times \mathbb{R}$$

where:

- $source\_id$ — causal event
- $target\_id$ — consequence event
- $impact\_score \in [-1, 1]$ — influence strength and direction:
  - $> 0$ — reinforcing influence (source accelerates, makes target more likely)
  - $< 0$ — dampening influence (source slows, makes target less likely)
  - $= 0$ — no influence (not included in matrix)

For a typical 20-event portfolio, the full matrix would contain $20 \times 19 = 380$ pairs. In practice, 30–50 meaningful connections exist; others are ignored. This sparsity is critical for Delphi scalability with many events.

---

## EventTrajectory Schema

The complete trajectory model combines all elements:

| Field | Type | Purpose |
|---|---|---|
| `event_thread_id` | str | Reference to EventThread |
| `current_state` | str | Current situation (2–3 sentences) |
| `momentum` | Momentum | escalating, stable, de-escalating, emerging, culminating, fading |
| `key_drivers` | list[str] | 3–5 development forces |
| `uncertainties` | list[str] | 2–3 major uncertainty points |
| `baseline_scenario` | Scenario | Most likely outcome |
| `optimistic_scenario` | Scenario | Best-case outcome |
| `pessimistic_scenario` | Scenario | Worst-case outcome |
| `wildcard_scenario` | Scenario | Surprising development |
| `geopolitical_analysis` | str | Geopolitical analyst assessment |
| `economic_analysis` | str | Economic analyst assessment |
| `media_analysis` | MediaAssessment | Media analyst assessment |

where `Scenario` contains:

| Field | Type | Purpose |
|---|---|---|
| `description` | str | Scenario summary (2–3 sentences) |
| `probability` | float | Assigned probability (0.0–1.0) |
| `key_indicators` | list[str] | 2–3 realization indicators |
| `potential_headline` | str | Possible headline from this scenario |

---

## CrossImpactMatrix Schema

The cross-impact matrix captures event dependencies:

| Field | Type | Purpose |
|---|---|---|
| `entries` | list[CrossImpactEntry] | Sparse impact relationships |
| `computed_at` | datetime | Timestamp of computation |

where `CrossImpactEntry` contains:

| Field | Type | Purpose |
|---|---|---|
| `source_id` | str | Causal event ID |
| `target_id` | str | Consequence event ID |
| `impact_score` | float | Influence magnitude [-1, 1] |
| `impact_type` | str | reinforcing, dampening, or neutral |
| `rationale` | str | Explanation of causal link |

---

## Source Code References

- **Analyst agents**: `src/agents/analysts/geopolitical_analyst.py`, `src/agents/analysts/economic_analyst.py`, `src/agents/analysts/media_analyst.py`
- **Trajectory models**: `src/schemas/trajectory.py`
- **Event trend coordinator**: `src/agents/analysts/event_trend_analyzer.py`

For complete specifications, see `docs/04-analysts.md` (§2: Trajectory Analysis, §3: Cross-Impact).
