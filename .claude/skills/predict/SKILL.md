---
name: predict
description: Run Delphi Press prediction pipeline — forecast media headlines for a given outlet and date using 5 expert personas as parallel subagents
allowed-tools: Read, Write, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

# /predict outlet="<outlet>" target_date="<YYYY-MM-DD>"

Run the full Delphi forecasting pipeline to predict tomorrow's headlines for a media outlet.

## Parameters

- **outlet** (required): Media outlet name. Examples: "ТАСС", "РБК", "BBC Russian", "Reuters", "Коммерсантъ"
- **target_date** (optional): Target date in YYYY-MM-DD format. Default: tomorrow. Must not be in the past.

## Before you start

1. Validate parameters. If outlet is missing, ask the user.
2. Read `GLOSSARY.md` — domain terminology reference.
3. Create output directory: `mkdir -p data/predictions`

## Important: Claude Code mode specifics

In Claude Code mode, ALL 5 expert personas run on the same model (Opus 4.6). Diversity comes from **distinct prompts** (25-35KB each), not from different models. This is by design — covered by Max subscription at $0 cost.

The main session acts as **orchestrator + mediator + judge**. The 5 personas run as **parallel subagents** via the Agent tool.

---

## Stage 1-2: COLLECTION + EVENT IDENTIFICATION

Goal: gather real-time information about the outlet and current events relevant to the target date.

### 1a. Build outlet profile

Use WebSearch to research the outlet. Determine:
- **outlet_type**: news agency / newspaper / online media / TV
- **editorial_stance**: political leaning, editorial line
- **primary_topics**: top 5-7 topic categories the outlet covers
- **audience_description**: who reads this outlet
- **language**: primary language of headlines
- **publication_frequency**: daily / hourly / etc.

### 1b. Collect current signals

Run 3-5 web searches to gather:
- Breaking news and developing stories relevant to the outlet's beat
- Scheduled events on/around the target date (summits, hearings, economic releases, elections, deadlines)
- Ongoing story arcs (conflicts, negotiations, trials, legislation)

Use WebSearch and/or `mcp__exa__web_search_exa` for broad coverage. Use WebFetch for specific URLs if needed.

### 1c. Identify event threads

From collected signals, identify **10-20 event threads** — distinct storylines that could generate headlines. For each:
- **thread_id**: short snake_case identifier (e.g., `us_cn_tariffs_apr2026`)
- **title**: one-line description
- **current_state**: what's happening now
- **key_facts**: 3-5 verified facts with sources
- **relevance_to_outlet**: why this outlet would cover it (high/medium/low)

Focus on events with **high outlet relevance**. Drop threads with low relevance.

---

## Stage 3: TRAJECTORY ANALYSIS

For each event thread, analyze:

1. **Momentum**: accelerating / stable / decelerating
2. **Momentum direction**: escalation / status_quo / de-escalation
3. **Days until target**: calendar distance
4. **Three scenarios**:
   - **Base** (most likely): description + probability
   - **Upside** (positive escalation): description + probability
   - **Downside** (negative/de-escalation): description + probability
5. **Key trigger**: what single event would shift the trajectory most
6. **Sources**: specific articles/reports backing the analysis

Then build a **cross-impact matrix**: for each pair of event threads, estimate how one event's realization affects the other's probability. Use values from -1.0 (strongly decreases) to +1.0 (strongly increases). Only note non-trivial interactions (|value| >= 0.1).

Save the complete context (outlet profile, event threads with trajectories, cross-impact matrix) — you'll pass it to all 5 subagents.

---

## Stage 4: DELPHI ROUND 1

Launch **5 parallel subagents** using the Agent tool. Each subagent is one expert persona.

### Personas and their prompt files

| Persona | prompt file | persona_id | cold-start weight |
|---------|-------------|------------|-------------------|
| Realist | `docs/prompts/realist.md` | `realist` | 0.22 |
| Geostrateg | `docs/prompts/geostrateg.md` | `geostrateg` | 0.20 |
| Economist | `docs/prompts/economist.md` | `economist` | 0.20 |
| Media Expert | `docs/prompts/media-expert.md` | `media_expert` | 0.18 |
| Devil's Advocate | `docs/prompts/devils-advocate.md` | `devils_advocate` | 0.20 |

### How to launch each subagent

Before launching, Read each persona's prompt file. Each file contains three sections delimited by ``` blocks:
1. **System prompt** — the persona's identity and analytical framework
2. **User prompt** — Jinja2 template with slots for context data
3. **Output JSON schema** — the PersonaAssessment format

For each persona, launch an Agent with this prompt structure:

```
You are an expert forecaster in a Delphi simulation. Your role is defined below.

## YOUR IDENTITY (System Prompt)

{paste the system prompt section from docs/prompts/{persona}.md}

## YOUR TASK

You are participating in Round 1 of a Delphi forecasting exercise.
Target outlet: {outlet}
Target date: {target_date}

## OUTLET PROFILE

{paste outlet profile from Stage 1a}

## EVENT TRAJECTORIES

{paste all event threads with trajectories from Stage 3}

## CROSS-IMPACT MATRIX

{paste cross-impact matrix from Stage 3}

## CALIBRATION CHECK

Before finalizing each probability:
- If > 0.70: name one specific scenario where the forecast is wrong.
- If < 0.30: name one specific scenario where the forecast is right.
- If deviation from historical base rate > 20pp: cite the specific fact causing this.

## OUTPUT FORMAT

Return your assessment as a single valid JSON block. No text outside the JSON.

{
  "persona_id": "{persona_id}",
  "round_number": 1,
  "predictions": [
    {
      "event_thread_id": "<thread_id from list above>",
      "prediction": "<Specific claim: what exactly will happen>",
      "probability": <0.03-0.97>,
      "newsworthiness": <0.0-1.0>,
      "scenario_type": "<base|upside|downside|black_swan>",
      "reasoning": "<Chain of reasoning: base rate -> case specifics -> conclusion. Min 100 chars>",
      "key_assumptions": ["<assumption 1>", "<assumption 2>"],
      "evidence": ["<fact from provided data>"],
      "conditional_on": [],
      "update_trigger": "<One specific fact that would shift probability >= 15pp>"
    }
  ],
  "cross_impacts_noted": ["<if event A then event B more/less likely>"],
  "blind_spots": ["<what the group might miss>"],
  "confidence_self_assessment": <0.0-1.0>,
  "revisions_made": [],
  "revision_rationale": ""
}

Requirements:
- 5 to 15 predictions
- probability: never 0.0 or 1.0; minimum 0.03, maximum 0.97
- Do NOT round probabilities to multiples of 5 or 10 (use 0.63, not 0.60)
- reasoning: must mention historical base rate
- evidence: only facts from provided data, do not fabricate
```

Launch all 5 subagents in a **single message with 5 Agent tool calls**. This is critical for parallelism.

### Parse R1 results

Extract the JSON block from each subagent's response. If a subagent failed to return valid JSON, note it and continue if at least 3 of 5 succeeded. If fewer than 3 succeeded, retry the failed ones sequentially.

---

## Stage 5a: MEDIATION

You (the main session) now act as the **mediator**. Read the mediator prompt: `docs/prompts/mediator.md`.

### Step 1: Anonymize

Randomly assign labels Expert A through Expert E to the 5 persona assessments. The mapping must be random — do NOT use alphabetical order of persona names. The mediator must not know which persona gave which assessment.

### Step 2: Compute statistics

For each event_thread_id mentioned across all assessments:
1. Count how many personas mentioned it
2. Compute median probability and spread (max - min)
3. Classify:
   - **Consensus**: spread < 0.15 AND mentioned by >= 3 experts
   - **Dispute**: spread >= 0.15
   - **Gap**: mentioned by < 3 experts

### Step 3: Formulate key questions

For each **dispute** (spread >= 0.15), formulate one **concrete, factually verifiable question** that could resolve the disagreement. The question must be:
- Specific (not "is escalation likely?" but "did the UN Security Council schedule a session before April 2?")
- Factually checkable
- Central to the disagreement
- Neutral (no leading language)

### Step 4: Supervisor search (optional)

If any dispute has spread > 0.25, run a targeted WebSearch for fresh facts that could resolve it. Add findings to `supplementary_facts`.

### Step 5: Compile MediatorSynthesis

Structure the synthesis as JSON with:
- `consensus_areas`: [{event_thread_id, median_probability, spread, num_agents}]
- `disputes`: [{event_thread_id, median_probability, spread, positions: [{agent_label, probability, reasoning_summary, key_assumptions}], key_question}]
- `gaps`: [{event_thread_id, mentioned_by, note}]
- `cross_impact_flags`: [{prediction_event_id, depends_on_event_id, note}]
- `overall_summary`: 2-3 neutral sentences
- `supplementary_facts`: [] or [fact strings from supervisor search]

---

## Stage 5b: DELPHI ROUND 2

Launch **5 parallel subagents** again. Each persona receives:
1. Their own R1 assessment (so they remember what they said)
2. The full MediatorSynthesis (anonymized — they see Expert A-E, not persona names)
3. Independence Guard instructions

Use the same Agent template as R1, but add these sections:

```
## YOUR ROUND 1 ASSESSMENT

{paste this persona's R1 JSON}

## INDEPENDENCE GUARD (Malmqvist 2024: anti-sycophancy)

Before reading the mediator synthesis: rate your confidence in your R1 assessment [1-5].
After reading: if you change an estimate, name the SPECIFIC FACT from the synthesis.
If you keep your estimate, explain in one sentence why.
Shifting because "others disagree" violates the Delphi protocol and reduces group accuracy.

## MEDIATOR SYNTHESIS (Round 1 Feedback)

{paste the full MediatorSynthesis JSON}

## ROUND 2 INSTRUCTIONS

Revise your R1 predictions considering the mediator's feedback. For each change:
- Explain why with reference to a specific fact or argument
- If you do NOT change: explain why the opposing arguments don't convince you
- Do NOT shift numbers just because "everyone else thinks so" — this violates Delphi method

Return the same JSON format as Round 1, but with round_number: 2.
Fill in revisions_made and revision_rationale fields.
```

Parse R2 results the same way as R1. Minimum 3 of 5 must succeed.

---

## Stage 6: JUDGE — Aggregation and Ranking

You (the main session) now act as the **judge**. Read the judge prompt: `docs/prompts/judge.md`.

### Step 1: Collect all R2 assessments

For each event_thread_id, gather all probability estimates from R2 (or R1 if persona didn't participate in R2).

### Step 2: Weighted aggregation

Apply cold-start weights (no calibration history in Claude Code mode):
- realist: 0.22
- geostrateg: 0.20
- economist: 0.20
- media_expert: 0.18
- devils_advocate: 0.20

For R2 assessments, apply temporal decay multiplier 1.5x (R2 is more informed than R1).

Compute weighted median probability for each event thread.

### Step 3: Platt scaling (extremization)

Apply to each weighted median:
```
calibrated_p = sigmoid(1.73 * logit(raw_p))
```
where logit(p) = ln(p / (1-p)) and sigmoid(x) = 1 / (1 + e^(-x))

This shifts probabilities away from 0.5 toward the extremes, correcting the systematic underconfidence of LLM ensembles.

### Step 4: Compute headline_score

For each event thread:
```
headline_score = calibrated_prob * newsworthiness * (1 - saturation) * outlet_relevance
```
where:
- `newsworthiness`: weighted average from all personas
- `saturation`: estimate how saturated this topic already is in media (0-1)
- `outlet_relevance`: how likely THIS outlet covers it (from outlet profile, 0-1)

### Step 5: Rank and select

- **Top 7**: highest headline_score events
- **Wild cards** (up to 2): events with probability < 0.30 but headline_score in top 15 — low probability but high impact if they happen
- For each selected event: record dissenting views (minority positions from personas who disagreed with consensus)

---

## Stages 7-9: FRAMING + GENERATION + QUALITY GATE

For each of the top-7 predictions (+ wild cards):

### Stage 7: Framing
Determine the angle this specific outlet would use:
- What frame fits the outlet's editorial stance?
- What hook makes this newsworthy for their audience?
- What angle differentiates from competitors?

### Stage 8: Generation
Write **2-3 headline variants** in the **outlet's language and style**:
- Match the outlet's typical headline length, tone, and formatting
- If the outlet uses Russian headlines, write in Russian
- If the outlet uses English, write in English
- Include a first paragraph (lead) for each variant

### Stage 9: Quality Gate
For each headline variant, check:
- **Factual plausibility**: does the claim follow from the evidence?
- **Style authenticity**: would a reader recognize this as a headline from this outlet?
- **Confidence calibration**: does the confidence level match the reasoning?

Select the **best variant** for each prediction.

---

## OUTPUT: Save Report

Save the final report to: `data/predictions/{target_date}_{outlet_slug}_{HHMM}.md`

Where `outlet_slug` is the outlet name lowercased with spaces replaced by hyphens (e.g., "bbc-russian").

### Report template

```markdown
# Delphi Press: Forecast for {outlet}

**Target date**: {target_date}
**Generated**: {current_datetime}
**Mode**: Claude Code (Opus 4.6 x5 personas, prompt diversity)

---

## Top Headlines

### 1. {headline}

> {first_paragraph}

- **Confidence**: {calibrated_probability} ({confidence_label})
- **Category**: {category}
- **Reasoning**: {reasoning}
- **Evidence**: {evidence_chain}
- **Agreement**: {agent_agreement_summary}
- **Dissenting views**: {dissenting_views}

### 2. ...
(repeat for all top-7)

---

## Wild Cards

### W1. {headline} (probability: {prob})
> {description and why it matters if it happens}

---

## Methodology

- **Pipeline**: 9-stage Delphi method with 5 expert personas
- **Personas**: Realist (base rates), Geostrateg (power dynamics), Economist (follow the money), Media Expert (editorial logic), Devil's Advocate (black swans)
- **Rounds**: 2 (R1: independent assessment, Mediation, R2: revised with feedback)
- **Aggregation**: Weighted median + Platt scaling (a=1.73)
- **Model**: All personas on Opus 4.6 (prompt diversity, not model diversity)

---

<details>
<summary>Raw Data: Event Threads</summary>

{event_threads_json}

</details>

<details>
<summary>Raw Data: Round 1 Assessments</summary>

{r1_assessments_json}

</details>

<details>
<summary>Raw Data: Mediator Synthesis</summary>

{mediator_synthesis_json}

</details>

<details>
<summary>Raw Data: Round 2 Assessments</summary>

{r2_assessments_json}

</details>
```

After saving, print the file path and a brief summary of the top-3 headlines.

---

## Error Handling

- **Subagent returns invalid JSON**: Extract any JSON-like block from the response. If still invalid, retry that persona once. If it fails again, skip it (proceed if >= 3 of 5 succeeded).
- **Web search returns no results**: Fall back on your own knowledge. Note in the report that some data collection was limited.
- **Fewer than 3 personas succeeded in a round**: Stop the pipeline. Save a partial report with what you have and note the failure.
- **Any stage fails completely**: Save partial results up to the last successful stage. Mark the report as incomplete.

---

## Confidence Labels

| Probability range | Label |
|---|---|
| 0.85 - 0.97 | Very high confidence |
| 0.70 - 0.84 | High confidence |
| 0.55 - 0.69 | Moderate confidence |
| 0.40 - 0.54 | Low confidence |
| 0.20 - 0.39 | Very low confidence |
| 0.03 - 0.19 | Negligible |
