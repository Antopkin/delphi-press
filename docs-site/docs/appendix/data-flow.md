# Data Flow: 9 Pipeline Stages

Polная архитектура pipeline: 9 стадий, 28 LLM-задач, agents, timeouts, parallel execution.

## Pipeline Stages Table

| # | Стадия | Агенты | Parallel? | Min | Timeout | Output |
|---|---|---|---|---|---|---|
| 1 | Collection | NewsScout, EventCalendar, OutletHistorian, Foresight | Да | 2/4 | 600s | signals, events, profile |
| 2 | Event ID | EventTrendAnalyzer | Нет | — | 600s | 20 EventThread |
| 3 | Trajectory | Geo, Econ, Media | Да | 2/3 | 600s | assessments |
| 4 | Delphi R1 | 5 персон | Да | 3/5 | 600s | R1 assessments |
| 5 | Delphi R2 | Mediator → 5 персон | Mix | 3/5 | 900s | synthesis + R2 |
| 6 | Consensus | Judge | Нет | — | 300s | timeline + top-7 |
| 7 | Framing | FramingAnalyzer | Нет | — | 300s | 7 briefs |
| 8 | Generation | StyleReplicator | Нет | — | 300s | 14–21 headlines |
| 9 | Quality Gate | QualityGate | Нет | — | 300s | 5–7 final |

---

## Stage Descriptions

### Stage 1: Collection (Параллельная, 2–4 агентов)
- **NewsScout:** fetch RSS от 16 источников, extract headlines, compute relevance
- **EventCalendar:** parse calendar, recognize date patterns (anniversaries, holidays)
- **OutletHistorian:** historical topic frequency в целевом издании (архивные данные за 6 мес)
- **Foresight:** GDELT + Metaculus (если доступны) для trending topics

**Output:** `signals` (список тематических сигналов), `events` (parsed calendar events), `profile` (outlet profile)

**Timeout:** 600s (каждый агент может потребовать HTTP requests)

---

### Stage 2: Event ID (Последовательная, 1 агент)
- **EventTrendAnalyzer:** group headlines по event threads, extract entity recognition, classify по категориям
- **Output:** `EventThreads` — ~20 nested event topics с confidence scores

**Timeout:** 600s (LLM-heavy stage, требует analysis всех заголовков)

---

### Stage 3: Trajectory (Параллельная, 2–3 агентов)
- **GeoAnalyst:** geopolitical context, border/UN involvement, sanctions
- **EconomicAnalyst:** economic indicators, trade, currency, investor impact
- **MediaExpert:** framing precedents, headline keywords, media playbooks

**Output:** `assessments` — 3 analytical perspectives на event threads

**Timeout:** 600s

---

### Stage 4: Delphi Round 1 (Параллельная, 3–5 персон)
- **Realist:** base rate, historical precedents, institutional inertia
- **Geostrateg:** neorealism, cui bono, decision trees
- **Economist:** follow the money, rational actor, economic calendar
- **MediaExpert:** gatekeeping, framing, news value criteria
- **Devil's Advocate:** pre-mortem, steelmanning, black swans

**Min agents:** 3/5 (если 1–2 fail, continue)

**Output:** R1 assessments (probability ranges, confidence)

**Timeout:** 600s (LLM calls для 5 персон параллельно)

---

### Stage 5: Delphi Round 2 (Гибридная: медиатор → персоны)
- **Mediator:** R1 результаты, classify (consensus/disputes/gaps), anonymize positions
- **5 Personas (again):** respond to mediator's questions

**Min agents:** 3/5

**Output:** synthesis (consensus points), R2 assessments (revised confidences)

**Timeout:** 900s (самая длинная стадия, требует медиации + повторных LLM calls)

---

### Stage 6: Consensus (Последовательная, 1 агент)
- **Judge:** weighted median confidence, Platt scaling (если available), headline selection, wild cards
- **Horizon-adaptive:** weights для 1d/3d/7d горизонтов

**Output:** timeline (top-7 events with confidence), final_prediction

**Timeout:** 300s (детерминистический алгоритм, no LLM since v0.7.0)

---

### Stage 7: Framing (Последовательная, 1 агент)
- **FramingAnalyzer:** LLM-as-judge, generates 7 brief frames (narrative angles for each top-7 event)

**Output:** 7 framing briefs (100–150 слов каждый)

**Timeout:** 300s

---

### Stage 8: Generation (Последовательная, 1 агент)
- **StyleReplicator:** генерирует 14–21 headlines в стиле целевого издания
- **Model selection по языку издания**

**Output:** 14–21 generated headlines

**Timeout:** 300s

---

### Stage 9: Quality Gate (Последовательная, 1 агент)
- **QualityGate:** фильтрует/ранжирует, returns 5–7 финальных

**Output:** 5–7 final headlines

**Timeout:** 300s

---

## Key Numbers

- **Total LLM calls:** ~28 (distributed across 9 stages)
- **Typical duration:** 40–60 minutes (dependent on parallel execution and LLM latency)
- **Cost per run:** $5–15 (Opus model, openRouter pricing)
- **Parallel factor:** stages 1, 3, 4, 5 can run agents concurrently, overall pipeline remains sequential

## Notes

- Timeout values set to 2x observed p95 latency
- R1/R2 minimum agent counts: 3/5 (pipeline continues if 1–2 agents fail)
- Event ID timeout same as collection (both LLM-heavy)
- Delphi R2 longer timeout due to multi-round mediation complexity
