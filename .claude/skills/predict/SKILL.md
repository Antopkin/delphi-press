---
name: predict
description: "Run Delphi Press prediction pipeline — forecast media headlines for a given outlet and date. Use when user asks for a prediction, forecast, headline generation, or mentions generating headlines for a media outlet. Also triggers on natural language like 'сделай прогноз', 'спрогнозируй заголовки', 'что напишет СМИ'."
allowed-tools: Read, Bash, Glob
---

# Delphi Press Prediction

Run the full 9-stage Delphi forecasting pipeline to predict headlines for a media outlet.

## Parameters

- **outlet** (required): Media outlet name. Examples: "ТАСС", "РБК", "BBC Russian", "Reuters"
- **target_date** (optional): YYYY-MM-DD format. Default: tomorrow.

## How to extract parameters from natural language

The user may say things like:
- "Сделай прогноз для ТАСС" → outlet="ТАСС"
- "Forecast BBC Russian headlines for April 15" → outlet="BBC Russian", target_date="2026-04-15"
- "А теперь для Reuters" → outlet="Reuters" (use context from previous run for date)
- "Что напишет РБК завтра?" → outlet="РБК"

If outlet is unclear, ask the user.

## Execution

Run the Python pipeline via `scripts/dry_run.py` with Claude Code provider:

```bash
uv run python scripts/dry_run.py \
  --provider claude_code \
  --outlet "{outlet}" \
  --target-date "{target_date}" \
  --db data/delphi_press.db \
  --event-threads 20
```

This will:
1. Run the full 9-stage Delphi pipeline (Collection → Event ID → Trajectory → Delphi R1 → Mediation → Delphi R2 → Judge → Framing → Generation → QA)
2. All LLM calls go through Claude Code Max subscription ($0 cost)
3. Sonnet 4.6 for news collection, Opus 4.6 for analysis/personas
4. Save prediction to local SQLite DB (`data/delphi_press.db`)

## After completion

1. Show the top headlines from stdout output
2. Show the prediction ID and web UI URL: `http://localhost:8000/results/{prediction_id}`
3. Ask if the user wants to start the web server for full results:
   - If yes: `uv run uvicorn src.main:app --port 8000` (run in background)
4. Ask if the user wants another prediction for a different outlet

## Error handling

- If the pipeline fails, show the error and failed stage
- Common issues: Claude Code not authenticated (run `claude setup-token`), no internet for RSS/web search
