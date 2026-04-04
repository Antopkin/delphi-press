# Pipeline: 9 стадий

**Delphi Press** реализует девятистадийный sequential-parallel hybrid конвейер: каждая стадия выполняется последовательно, но агенты внутри стадии могут работать параллельно (в зависимости от конфигурации). Контекст (состояние) передаётся через 16 типизированных слотов (`PipelineContext`), заполняемых последовательно.

## Обзор стадий

| # | Стадия | Агенты | Параллель | min_successful | Timeout |
|---|---|---|---|---|---|
| 1 | COLLECTION | 4 агента | Да | 2/4 | 600s |
| 2 | EVENT_IDENTIFICATION | EventTrendAnalyzer | Нет | — | 600s |
| 3 | TRAJECTORY | 3 аналитика | Да | 2/3 | 600s |
| 4 | DELPHI_R1 | 5 персон | Да | 3/5 | 600s |
| 5 | DELPHI_R2 | Медиатор+5 персон | Смешано | 3/5 | 900s |
| 6 | CONSENSUS | Judge | Нет | — | 300s |
| 7 | FRAMING | FramingAnalyzer | Нет | — | 300s |
| 8 | GENERATION | StyleReplicator | Нет | — | 300s |
| 9 | QUALITY_GATE | QualityGate | Нет | — | 300s |

!!! note "Что такое min_successful?"
    Минимальное число агентов, которые должны завершиться успешно для продолжения pipeline. Обеспечивает graceful degradation: если одни агенты отказали, другие достаточно.

## 18 агентов, 27 LLM-задач

| Агент | Стадия | LLM-задачи | Слоты контекста | Файл |
|---|---|---|---|---|
| NewsScout | 1 | news_scout_search | signals | collectors/news_scout.py |
| EventCalendar | 1 | event_calendar, event_assessment | scheduled_events | collectors/event_calendar.py |
| OutletHistorian | 1 | outlet_historian | outlet_profile | collectors/outlet_historian.py |
| ForesightCollector | 1 | (нет LLM) | foresight_events, foresight_signals | collectors/foresight_collector.py |
| EventTrendAnalyzer | 2 | event_clustering, trajectory_analysis, cross_impact_analysis | event_threads, trajectories, cross_impact_matrix | analysts/event_trend.py |
| GeopoliticalAnalyst | 3 | geopolitical_analysis | event_threads[] | analysts/geopolitical.py |
| EconomicAnalyst | 3 | economic_analysis | event_threads[] | analysts/economic.py |
| MediaAnalyst | 3 | media_analysis | event_threads[] | analysts/media.py |
| DelphiRealist | 4/5 | delphi_r1_realist, delphi_r2_realist | round1/2_assessments | forecasters/personas.py |
| DelphiGeostrateg | 4/5 | delphi_r1_geostrateg, delphi_r2_geostrateg | round1/2_assessments | forecasters/personas.py |
| DelphiEconomist | 4/5 | delphi_r1_economist, delphi_r2_economist | round1/2_assessments | forecasters/personas.py |
| DelphiMediaExpert | 4/5 | delphi_r1_media, delphi_r2_media | round1/2_assessments | forecasters/personas.py |
| DelphiDevilsAdvocate | 4/5 | delphi_r1_devils, delphi_r2_devils | round1/2_assessments | forecasters/personas.py |
| Mediator | 5 | mediator | mediator_synthesis | forecasters/mediator.py |
| Judge | 6 | (детерминированный) | predicted_timeline, ranked_predictions | forecasters/judge.py |
| FramingAnalyzer | 7 | framing | framing_briefs | generators/framing.py |
| StyleReplicator | 8 | style_generation, style_generation_ru, style_generation_en | generated_headlines | generators/style_replicator.py |
| QualityGate | 9 | quality_factcheck, quality_style | final_predictions | generators/quality_gate.py |

## Поток данных: примеры слотов

Основные слоты `PipelineContext`:

- **signals**: `List[SignalRecord]` — сырые новости из RSS и поиска (100–200)
- **scheduled_events**: `List[ScheduledEvent]` — политические/экономические события на target_date
- **outlet_profile**: `OutletProfile` — стилевой профиль издания с примерами заголовков
- **event_threads**: `List[EventThread]` — top-20 кластеризованных событийных цепочек
- **trajectories**: `List[EventTrajectory]` — сценарные траектории (baseline, optimistic, pessimistic, black_swan)
- **cross_impact_matrix**: `CrossImpactMatrix` — матрица перекрёстных влияний между событиями
- **round1_assessments**: `List[PersonaAssessment]` — независимые оценки от 5 персон (раунд 1)
- **mediator_synthesis**: `MediatorSynthesis` — консенсус, расхождения, ключевые вопросы
- **round2_assessments**: `List[PersonaAssessment]` — пересмотренные оценки после медиации
- **ranked_predictions**: `List[RankedPrediction]` — top-7 финальных событий, ранжированных по headline_score
- **framing_briefs**: `List[FramingBrief]` — анализ подачи каждого события
- **generated_headlines**: `List[GeneratedHeadline]` — сгенерированные заголовки и абзацы (2–3 на событие)
- **final_predictions**: `List[FinalPrediction]` — финальные прогнозы после факт-чека и дедупликации

## Поток данных: пример

$$\text{PredictionRequest} \xrightarrow{\text{Stage 1}} \text{signals, events, outlet\_profile}$$

$$\xrightarrow{\text{Stage 2}} \text{event\_threads, trajectories, cross\_impact\_matrix}$$

$$\xrightarrow{\text{Stages 3–5}} \text{round1/2\_assessments, mediator\_synthesis}$$

$$\xrightarrow{\text{Stages 6–9}} \text{ranked\_predictions} \to \text{framing\_briefs} \to \text{generated\_headlines} \to \text{final\_predictions}$$

$$\xrightarrow{\text{Response}} \text{PredictionResponse} \text{ с 7 заголовков, уверенностью, обоснованиями}$$

## Производительность и стоимость

| Стадия | LLM-вызовов | Основная модель | Стоимость |
|---|---|---|---|
| 1: Collection | ~5 | Gemini + Opus | \$1,50 |
| 2: Event Identification | ~25 | Gemini-flash | \$0,50 |
| 3: Trajectory | ~21 | Opus | \$3,00 |
| 4: Delphi R1 | 5 | Opus (единая модель для 5 персон) | \$8,00 |
| 5a: Mediator | 1 | Opus | \$2,00 |
| 5b: Delphi R2 | 5 | Opus (единая модель для 5 персон) | \$8,00 |
| 6: Judge | — | (детерминированный) | \$0 |
| 7: Framing | ~7 | Opus | \$2,00 |
| 8: Generation | ~21 | Opus | \$1,50 |
| 9: Quality Gate | ~14 | Opus | \$2,00 |
| **Итого** | **~105 вызовов** | | **~\$30,50** |

Время выполнения: 15–20 минут на одном VPS.
