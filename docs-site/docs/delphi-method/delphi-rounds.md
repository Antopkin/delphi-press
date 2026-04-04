# Stages 4–5: Delphi Rounds & Expert Consensus

## Five Expert Personas

The Delphi system is built on five independent **expert personas** — LLM agents with clearly defined analytical frameworks, cognitive biases, and initial weights. Each operates on the same model (`anthropic/claude-opus-4.6`) but differs through **system prompt**, determining identity, methodology, and deliberate cognitive biases.

| ID | Name | Role | Weight | Primary Methodology |
|---|---|---|---|---|
| 1 | REALIST | Risk analyst | 0.22 | Base rates, Tetlock *Superforecasting* |
| 2 | GEOSTRATEG | IR specialist | 0.20 | Neorealism, cui bono, balance of power |
| 3 | ECONOMIST | Macroeconomist | 0.20 | Follow the money, market indicators |
| 4 | MEDIA_EXPERT | Editor/analyst | 0.18 | Gatekeeping (White 1950), framing (Entman 1993) |
| 5 | DEVILS_ADVOCATE | Contrarian/red teamer | 0.20 | Pre-mortem, black swan detection (Taleb) |

Total weight: $0.22 + 0.20 + 0.20 + 0.18 + 0.20 = 1.00$

### Persona 1: The Realist

**Identity**: Experienced political risk analyst (Eurasia Group, Oxford Analytica profile) with 20 years consulting experience. Thinks in base rates, historical precedent, institutional inertia.

**Analytical Framework**:

1. *Base rates* — First question: "How often has this happened in 10–20 years? What were outcomes?"
2. *Institutional inertia* — Systems change slower than appearance suggests
3. *Outside view before inside view* — Start with external viewpoint (Tetlock, Superforecasting)
4. *Calibration over confidence* — Prefer uncertain accuracy over confident error
5. *Question separation* — "Will it happen?" and "Will it make headlines?" are different tasks

**Managed Cognitive Bias**:

- **Overestimates**: Status quo inertia, bureaucratic process predictability
- **Underestimates**: Black swans, escalation speed, role of leader decisions
- **Anchors on**: Historical precedent

**Initial Weight**: 0.22 (elevated — base rates historically well-calibrated)

### Persona 2: The Geopolitical Strategist

**Identity**: IR specialist (IISS, Chatham House, IMEMO RAN) focused on power balances, alliances, state strategic interests.

**Analytical Framework**:

1. *Cui bono* — Who wins, who loses?
2. *Decision trees* — Second- and third-order effects
3. *Neorealism + constructivism* — System structure determines behavior; identities and narratives shape threat perception
4. *Red lines & thresholds* — Distinguish real red lines from bluffing

**Managed Cognitive Bias**:

- **Overestimates**: Rationality of state actors, geopolitical factor weight
- **Underestimates**: Domestic political accidents, technology role, non-state actor economic motivation
- **Anchors on**: Great power competition model

**Initial Weight**: 0.20

### Persona 3: The Economist

**Identity**: Macroeconomist and market analyst (Goldman Sachs Research, The Economist Intelligence Unit) focused on capital flows, fiscal policy, commodity prices, corporate interests.

**Analytical Framework**:

1. *Follow the money* — Base principle
2. *Rational actor with budget constraints* — Economic incentives reveal true intentions
3. *Economic calendar* — Predictable news drivers (data releases, central bank meetings)
4. *Market signals contain information* — Yield curve, CDS spreads, gold price

**Managed Cognitive Bias**:

- **Overestimates**: Economic rationality, predictive power of market indicators
- **Underestimates**: Ideological factors, culture wars, emotion-driven events
- **Anchors on**: Economic calendar and market consensus

**Initial Weight**: 0.20

### Persona 4: Media Expert

**Identity**: Former editor at major news agency (Reuters, TASS) + journalism professor. Understands newsroom operations: deadlines, sources, editorial policy, competition for attention.

**Analytical Framework**:

1. *Gatekeeping* (White, 1950) — Not everything important gets published. Editorial filters limit throughput
2. *Framing* (Entman, 1993) — One event, ten angles. Frame choice determines headline and angle
3. *Media saturation* — Topic in top news 14+ days straight → newsroom seeks fresh angle or withdraws
4. *Competition for attention* — Parallel events compete for audience

**Managed Cognitive Bias**:

- **Overestimates**: Media cycle importance, editorial decision predictability
- **Underestimates**: Technical and procedural events, slow-developing crises
- **Anchors on**: Current news cycle and topic balance

**Initial Weight**: 0.18 (below average — media expertise important for headline formulation, less for probability)

### Persona 5: Devil's Advocate

**Identity**: Systematic contrarian, risk analyst (red team, intelligence community, Nassim Taleb school). Mission: find what others missed.

**Analytical Framework**:

1. *Pre-mortem* — "Imagine the forecast failed. What exactly went wrong?" (Klein, 1989)
2. *Steelmanning* — Build strongest version of opposite position, then attack
3. *Cascading dependencies* — If A is contested and B depends on A, the chain becomes fragile
4. *Black swans* (Taleb) — Low probability, high impact scenarios

**Managed Cognitive Bias**:

- **Overestimates**: Black swan probability, system fragility, non-obvious causal links
- **Underestimates**: Status quo resilience, boring outcome probability, institutional stability
- **Anchors on**: Unlikely, high-impact scenarios

**Initial Weight**: 0.20 (paradoxically high — contrarian forecasts add ensemble value even if rarely right)

---

## Round 1: Independent Assessment

All five personas run in **parallel**. Each receives:

- **Outlet profile** (`OutletProfile`): geography, target audience, editorial policy, topic balance
- **Event trajectories** (`EventTrajectory[]`): up to 20 events with current state, momentum, scenarios, drivers
- **Cross-impact matrix** (`CrossImpactMatrix`): sparse event dependencies
- **Persona system prompt** — identity, methodology, bias specification

**LLM Parameters for R1**:

- **Model**: `anthropic/claude-opus-4.6`
- **Temperature**: $T = 0.7$ (some stochasticity, managed)
- **max_tokens**: 4096
- **json_mode**: true (structured output)

Minimum successful agents: $\text{min\_successful} = 3$ out of 5. One agent failure doesn't cancel the round.

### Output Schema: PersonaAssessment

Each persona returns structured assessment `PersonaAssessment`:

```json
{
  "persona_id": str,                    // "realist", "geostrateg", etc.
  "round_number": int,                  // 1 or 2
  "predictions": PredictionItem[],      // 5–15 predictions
  "cross_impacts_noted": str[],         // Observed cross-impacts
  "blind_spots": str[],                 // What group might miss
  "confidence_self_assessment": float,  // (0–1) self-confidence
  
  // Round 2 only:
  "revisions_made": str[],              // What changed
  "revision_rationale": str             // Why
}
```

### Output Schema: PredictionItem

Each element in `predictions[]` contains one event forecast:

```json
{
  "event_thread_id": str,               // Stage 3 event ID
  "prediction": str,                    // Concrete statement
  "probability": float,                 // (0.0–1.0, not rounded to 5%)
  "newsworthiness": float,              // (0–1) coverage likelihood
  "scenario_type": str,                 // BASELINE | OPTIMISTIC | PESSIMISTIC | WILDCARD
  "reasoning": str,                     // Reasoning chain (3–7 sentences)
  "key_assumptions": str[],             // 2–4 key premises
  "evidence": str[],                    // References to input data
  "conditional_on": str[]               // IDs of dependent predictions
}
```

**Critical Requirements**:

1. **Probability Precision**: Each probability must be unique, not rounded to 5% or 10% (0.63, not 0.60). This requirement (Tetlock) improves calibration.

2. **Range**: $0.03 \leq \text{probability} \leq 0.97$. Probabilities of 0.00 or 1.00 forbidden (indicate overconfidence).

3. **Justification**: Each forecast must have explicit reasoning chain and key premises on which assessment rests.

---

## Mediator: Disagreement Synthesis (Stage 5a)

After Round 1, five independent assessments feed into the **Mediator** — a specialized agent whose task is not to forecast but to **structure disagreements** for substantive Round 2.

### Classical Delphi vs. LLM-Delphi

In classical Delphi (Dalkey & Helmer, 1963), Round 2 feedback consists of aggregated statistics: median, quartiles, histogram.

But research on **DeLLMphi** (Zhao et al., 2024) showed a critical problem: if LLM agents receive only median group estimates, they shift slightly toward it without substantive argument revision. This phenomenon is called *Degeneration-of-Thought* (Liang et al., 2024, EMNLP).

**Our Solution**: Instead of bare statistics, the Mediator formulates **substantive specific questions** that reveal actual disagreements and force agents to revise arguments, not just numbers.

### Three Mediation Stages

**Stage 1: Algorithmic Event Classification**

For each event, collect all five personas' assessments and compute:

1. **Spread**: $\text{spread} = \max(\text{probabilities}) - \min(\text{probabilities})$
2. **Median**: $\text{median}(\text{probabilities})$
3. **Count**: Number of agents mentioning event: $n \in [0, 5]$

Events classified as:

1. **Consensus Area**: $\text{spread} < 0.15$ **AND** $n \geq 3$
   - *Interpretation*: Experts agree; no revision needed. High confidence for final forecast.

2. **Dispute Area**: $\text{spread} \geq 0.15$
   - *Interpretation*: Experts disagree. Mediator formulates specific factual question whose answer might reconcile positions.

3. **Gap Area**: $n < 3$
   - *Interpretation*: Events mentioned by <3 experts. Potentially important gaps the group missed.

**Stage 2: Cascade Dependency Check**

*CrossImpactFlag*: If prediction A depends on event B (via `conditional_on`), and B is disputed, this creates chain uncertainty worth highlighting.

**Stage 3: LLM-Enriched Synthesis**

Mediator receives:

- Anonymized assessments (Expert A–E labels, see below)
- Event trajectories (context)
- Stages 1–2 results (algorithmic classification)

Mediator enriches via LLM call:

- For each dispute: formulate one-liner key question whose answer reconciles positions
- For each gap: explain why missing coverage might matter
- Generate overall summary (2–3 sentences): consensus count, dispute count, gap count

**LLM Parameters for Mediator**:

- **Model**: `anthropic/claude-opus-4.6`
- **Temperature**: 0.7 (neutral)
- **json_mode**: true

### Anonymity as Groupthink Defense

**Critical mechanism** (Zhang et al., 2024, ACL): **Expert labels are randomly reassigned each run**.

Algorithm:

1. Generate deterministic random tree from persona ID hashes
2. Shuffle labels {Expert A, B, C, D, E}
3. Same persona gets different label each run

**Effect**: Agent cannot recognize itself by label and conform. Preserves minority position independence.

### Output: MediatorSynthesis

```json
{
  "consensus_areas": ConsensusArea[],       // spread < 0.15, n >= 3
  "disputes": DisputeArea[],                // spread >= 0.15 + key question
  "gaps": GapArea[],                        // n < 3
  "cross_impact_flags": CrossImpactFlag[],  // Dependency chains
  "overall_summary": str,                   // 2–3 sentence overview
  "supplementary_facts": str[]              // For supervisor search if needed
}
```

**ConsensusArea**:
```json
{
  "event_thread_id": str,
  "median_probability": float,   // (0–1)
  "spread": float,               // < 0.15
  "num_agents": int              // >= 3
}
```

**DisputeArea**:
```json
{
  "event_thread_id": str,
  "median_probability": float,
  "spread": float,               // >= 0.15
  "positions": AnonymizedPosition[],  // Each expert's view
  "key_question": str            // Factual question for R2
}

AnonymizedPosition: {
  "agent_label": str,            // "Expert A", "Expert B", etc.
  "probability": float,
  "reasoning_summary": str,      // First 200 chars of reasoning
  "key_assumptions": str[]
}
```

**GapArea**:
```json
{
  "event_thread_id": str,
  "mentioned_by": str[],         // Expert labels mentioning event
  "note": str                    // Why this gap might matter
}
```

**CrossImpactFlag**:
```json
{
  "prediction_event_id": str,    // Event A
  "depends_on_event_id": str,    // Event B (disputed)
  "note": str                    // A→B dependency description
}
```

---

## Round 2: Revision with Feedback

All five personas run **again in parallel**. Each receives:

- **Their own R1 assessments**
- **MediatorSynthesis** — anonymized other experts' positions and key questions
- **Independence Guard** — explicit instruction: *"Don't shift numbers just because others disagree. Answer the mediator's key question substantively"*

**LLM Parameters for R2**:

- **Model**: `anthropic/claude-opus-4.6`
- **Temperature**: $T = 0.6$ (reduced from 0.7 to lower noise)
- **max_tokens**: 4096
- **json_mode**: true

Minimum successful agents: $\text{min\_successful} = 3$ out of 5.

### Output: RevisedAssessment

Structure identical to `PersonaAssessment`, plus revision fields:

```json
{
  // All R1 fields...
  "predictions": PredictionItem[],
  "confidence_self_assessment": float,
  
  // R2-specific:
  "revisions_made": str[],         // List of changes
  "revision_rationale": str        // Why these revisions
}
```

Example revisions:

- "Raised probability from 0.42 to 0.58 — mediator's question about Hungarian veto crucial; rethought reasoning"
- "Kept 0.25 — minority position, but factual question didn't dispel uncertainty"
- "Added new prediction on minority-mentioned event — now see importance of this gap"

---

## Theoretical Justification for LLM Delphi

### Classical Delphi & Its Advantages

*Delphi Method* (Dalkey & Helmer, RAND Corporation, 1963) — structured group forecasting technique based on four principles:

1. **Anonymity**: Experts don't know who gave which estimate
2. **Iteration**: Multiple rounds with feedback
3. **Controlled feedback**: Participants receive aggregated group statistics (median, quartiles, histogram)
4. **Statistical aggregation**: Final result is averaged group estimate

**Proven advantages** (Rowe & Wright, 2001, 2005):

- Suppresses anchoring effect — experts shift based on data, not authority
- Reduces authority pressure — anonymity protects minority views
- More calibrated probabilities — group often beats individual experts

### Adaptation for LLM Agents

Our implementation replaces human experts with LLM agents with defined cognitive profiles. Key differences:

1. **Determinism** — Each agent receives identical inputs (trajectories, cross-impacts) and system prompt defining framework
2. **No classical authority pressure** — Agents don't know others' views until mediation. Group pressure introduced controlledvia mediator, not majority expression
3. **Reproducibility** — Results reproducible with fixed random seeds

### Key Research

**AIA Forecaster** (Schoenegger et al., 2024): If all ensemble agents use one model, their errors **correlate**. Correlated errors don't offset in aggregation.

*Finding*: Five copies of one model barely outperform single call.

*Our Solution*: All five personas use `claude-opus-4.6`, but **diversity comes from system prompts, cognitive profiles, analytical frameworks** — not model variety. This enables:

- Cost control (single provider)
- Quality assurance (Opus 4.6 is strongest in category)
- Intentional error diversity through cognitive design

**DeLLMphi** (Zhao et al., 2024): Classical LLM Delphi shows critical failure:

1. R1: agents give independent estimates
2. R2: shown median group estimates
3. Result: slight shift toward median **without substantive argument revision**

*Finding*: *Degeneration-of-Thought* — LLM settled in position, unable to *genuine revision* from statistics alone

*Our Solution*: Mediator formulates **substantive factual questions**:

$$\text{Key Question:} \quad Q = \text{"What exactly must be checked to resolve this disagreement?"}$$

Lorenz & Fritz (2025, arXiv:2602.08889) showed: **substantive questions** correlate forecasts with ground truth at $r = 0.87$–$0.95$. Bare statistics: $r \approx 0.60$–$0.70$.

**Minority Position Defense** (Zhang et al., 2024, ACL): LLM agents reproduce human conformity with *bandwagon score* 0.524 in GPT-3.5. Majority shifts agent even if initially disagreed.

*Our Solution*: Label rotation prevents self-recognition; agent can't conform to its own past.

**Two Rounds Suffice** (Rowe & Wright, 2005):

- R1 → R2: substantial improvement (80% convergence)
- R2 → R3: marginal (additional 5–10%)
- R3+: diminishing returns

With LLM cost linear in rounds, **two rounds** balance quality and expense.

---

## Complete Two-Round Delphi Architecture

Full cycle:

$$\begin{aligned}
\text{R1:} \quad &\text{5 personas} \xrightarrow{\parallel} \text{PersonaAssessment}[] \\
\text{Mediation:} \quad &\text{PersonaAssessment}[] \xrightarrow{\text{Mediator}} \text{MediatorSynthesis} \\
\text{R2:} \quad &\{\text{Self R1} + \text{MediatorSynthesis}\} \xrightarrow{\parallel} \text{RevisedAssessment}[] \\
\text{Judge:} \quad &\text{RevisedAssessment}[] \xrightarrow{\text{aggregation}} \text{RankedPrediction}[]
\end{aligned}$$

Each stage:

- Data-independent (agents don't see each other until mediation)
- Parses to typed Pydantic objects (validation)
- Logs full LLM cost (tokens, USD)
- Preserves reasoning chains, not just probabilities

For complete Delphi specification, see `docs/05-delphi-pipeline.md`.

---

## Source Code References

- **Persona definitions**: `src/agents/forecasters/personas.py`
- **Mediator logic**: `src/agents/forecasters/mediator.py`
- **Data schemas**: `src/schemas/forecaster.py`
- **Prompts**: `docs/prompts/personas.md`, `docs/prompts/mediator.md`

For complete Delphi orchestration, see `docs/05-delphi-pipeline.md` and `src/agents/orchestrator.py`.
