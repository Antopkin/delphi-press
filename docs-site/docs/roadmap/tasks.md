# Дорожная карта

!!! info "Формат"
    Kanban: Done → In Progress → Next → Backlog.
    Текущая версия: **v0.9.8** (2026-04-12). Тесты: 1 413.

---

## Done (v0.9.2 — v0.9.6)

| Задача | Версия | Результат |
|--------|--------|-----------|
| Walk-forward валидация | v0.9.2 | 22 фолда, BSS +0.196, p = 2.38 × 10⁻⁷ |
| BSS variants & bootstrap CI | v0.9.3 | Volume gate, extremizing, timing — baseline оптимален |
| EIP-55 wallet key fix | v0.9.3 | `.lower()` на ключах, профили заработали |
| Market Dashboard `/markets` | v0.9.4 | Informed consensus vs raw price, sparklines |
| Production на Opus 4.6 | v0.9.4 | 28 задач, `max_tokens=None`, JSON-truncation fix |
| Incremental pipeline save | v0.9.5 | Draft headlines Stage 8, final Stage 9, no data loss |
| Auto-download profiles | v0.9.5 | 62 MB parquet при первом запуске, SHA-256 |
| Progress / results redesign | v0.9.6 | Hero h1, shimmer, фазовая группировка, bordered cards |
| Docs-site (29 страниц) | v0.9.6 | mkdocs-material, KaTeX, 11 gotchas, bibliography |
| Литобзор архетипов | v0.9.6 | 26 статей, валидация 6 тезисов, [RFC](discussion.md) |
| Wayback HTML ground-truth | v0.9.7 | Fetcher для ТАСС/РИА/РБК, forward-forecast runner |
| Claude Code mode ($0/run) | v0.9.8 | `ClaudeCodeProvider`, claude-agent-sdk, predict skill, 1413 тестов |

---

## In Progress

### Архетипы трейдеров — RFC

[Полный документ](discussion.md) отправлен команде. Ждём feedback по 14 вопросам.

- **Контекст**: текущий модуль `src/inverse/` классифицирует трейдеров только по точности (Brier Score → INFORMED/MODERATE/NOISE). Не знаем *почему* одни точнее — какую стратегию используют, на каких рынках компетентны. Архетипная классификация даст *archetype-weighted consensus*: взвешивание не только по точности, но и по соответствию стратегии типу рынка.
- **Литературная база**: 26 статей (Kyle, Tetlock, Kahneman-Tversky, Barber & Odean, Mitts & Ofir и др.). Литература сходится на 6–8 канонических архетипов.
- **Решение команды**: нужен выбор по таксономии (8 vs 11 архетипов), масштабу (PoC vs full), и методу (semi-supervised vs pure ML).

---

## Next

Задачи, готовые к старту. Отсортированы по важности.

---

### 1. Retrospective Evaluation Pilot

!!! info "В процессе (2026-04-11)"
    Forward-forecast pilot запущен: 3 outlets (ТАСС / РИА / РБК) × `target_date=today` × Haiku 4.5. Predicted headlines в `data/eval/forecast_runs/`. Ground truth собирается через `src/eval/ground_truth.py::fetch_headlines_from_wayback_html()` через 6–24 часа после запуска. Полный retrospective (50×3×Opus) — следующая фаза, требует ~$200.

**Контекст и контроль leakage**: в процессе реализации обнаружено, что все 4 коллектора (`src/agents/collectors/`) используют wall-clock временные фильтры — `NewsScout.fetch_feeds(days_back=7)` тянет последние 7 дней от момента запуска, не от `target_date`. Прямой retrospective прогон на прошлую дату **протекает пост-target данные** в сигналы → модель видит ответ → метрика становится мусором. Два возможных пути:

1. **Forward forecast (реализовано)**: запускать pipeline на `target_date = today`, собирать ground truth через Wayback Machine когда индексация догонит (обычно 6–24 часа). Нет leakage, потому что RSS на момент запуска не содержит материал после today.

2. **Strict retrospective (отложено)**: форк всех 4 коллекторов с явным `cutoff_date` параметром, заменой `web_search` на Wayback-based fetcher, фильтрацией RSS items по `published_at <= cutoff`. Даёт полноценный walk-forward на головной задаче. Оценка объёма: half-day рефакторинга + новые тесты temporal cutoff per-collector.

**Инфраструктура ground truth**: `fetch_headlines_from_wayback()` (старый RSS-based путь) **не работает** для русскоязычных СМИ — Wayback почти не архивирует их RSS-фиды (0 snapshots на всех проверенных датах). Новая функция `fetch_headlines_from_wayback_html()` скачивает HTML главной страницы через Wayback CDX + извлекает заголовки через trafilatura + regex по `item__title` (для РБК). Проверено: ТАСС 20 clean, РИА 9, РБК 12 с первой позиции. 16 новых unit-тестов в `tests/test_eval/test_ground_truth.py`.

**Infrastructure ready**:
- `scripts/eval_forecast_vs_reality.py` — runner с `--run` / `--collect` режимами
- `src/eval/ground_truth.py::fetch_headlines_from_wayback_html()` — ground truth fetcher
- `src/eval/metrics.py::composite_score()` — weighted metric (was dead code, теперь подключено)
- `docs/meeting/forecast_vs_reality.md` — артефакт-отчёт (генерируется `--collect` фазой)

**Остаётся**:
- Дождаться Wayback индексации (6–24ч) → запустить `--collect` → обновить артефакт цифрами
- Опционально: полный 50×3×Opus pilot (~$200, требует бюджета)
- Опционально: strict retrospective через форк коллекторов (half-day refactor)

---

### 2. Pipeline Checkpoint & Resume

**Контекст**: если Stage 9 (QualityGate) падает по timeout, весь pipeline нужно перезапускать. Стоимость перезапуска: $10–15 (full preset). Incremental save (v0.9.5) сохраняет *результаты*, но не *состояние* — нельзя продолжить с точки сбоя.

**Что делать**: сериализовать `PipelineContext` (16 слотов) после каждой стадии в `PipelineStep.output_data` (поле существует, но не заполняется). Новый endpoint: `POST /predictions/{id}/resume` — пропускает completed стадии, стартует с первой незавершённой.

**Сложность**: средняя. ~200–300 LOC. `PipelineContext` — Pydantic-модель, сериализуется в JSON. Основная работа: десериализация + валидация + пропуск стадий в `Orchestrator`. Миграция БД не нужна.

**Важность**: высокая. Прямая экономия при каждом timeout. Также необходим для будущего масштабирования (длинные pipeline с archetype routing).

---

### 3. QualityGate Revision Pipeline

**Контекст**: Stage 9 может вернуть статус `REVISE` — заголовок не прошёл fact-check или style-check. Сейчас `REVISE = drop`: заголовок просто удаляется без переделки. Это один из двух HIGH IMPACT gotchas в документации.

**Что делать**: при `REVISE` — переотправить заголовок в StyleReplicator (Stage 8) с feedback от QualityGate. Максимум 1 retry. Если после retry всё ещё `REVISE` → drop.

**Сложность**: средняя. Цикл retry внутри `_run_generation_quality()` в orchestrator. Нужна передача QualityGate feedback как дополнительного контекста в StyleReplicator prompt.

**Важность**: высокая. Без этого система иногда отдаёт 5 заголовков вместо 7, и теряются потенциально хорошие варианты.

---

### 4. Event-Level Prediction Storage

**Контекст**: Stage 6 (Judge) генерирует `PredictedTimeline` — ранжированный список событий с вероятностями. Этот объект **не сохраняется** в БД. Без него невозможно сравнить *наш прогноз* с *рыночной ценой Polymarket* per-event (Delphi BS vs Market BS).

**Что делать**: JSON dump `PredictedTimeline` в `PipelineStep.output_data` для Stage 6. Добавить endpoint `GET /predictions/{id}/events` для просмотра.

**Сложность**: низкая. Pydantic → JSON → существующее поле. ~50 LOC.

**Важность**: высокая. Блокирует per-prediction market evaluation — ключевую метрику для сравнения с Polymarket.

---

### 5. LLM Provider Fallback

**Контекст**: весь pipeline зависит от одного провайдера — OpenRouter. Если OpenRouter недоступен, ни один LLM-вызов не пройдёт. Это документировано как MEDIUM IMPACT gotcha.

**Что делать**: добавить fallback provider в `ModelRouter`. При ошибке OpenRouter → попробовать прямой API Anthropic (для Claude) или Google (для Gemini). `LLMProvider` уже абстрагирован — нужен второй instance.

**Сложность**: средняя. `ModelRouter` уже имеет retry + fallback по *моделям* (Opus → Sonnet). Нужен fallback по *провайдерам*. Требует отдельных API-ключей.

**Важность**: средняя. Критична для production-готовности, но OpenRouter имеет хороший SLA.

---

### 6. Gemini Flash JSON Repair

**Контекст**: Light-пресет ($1–2 за прогноз) использует Gemini Flash для дешёвых задач. На ~10% задач генерирует невалидный JSON → парсинг падает → стадия failsafe → деградированное качество.

**Варианты**: (a) JSON repair middleware (strip trailing commas, fix quotes), (b) prompt engineering с explicit examples, (c) замена на Claude Haiku 4.5 ($0.25/M input). Вариант (a) наиболее общий.

**Сложность**: низкая. JSON repair = ~50 LOC regex + `json.loads` retry. Или замена модели в `DEFAULT_ASSIGNMENTS`.

**Важность**: средняя. Только для Light-пресета. Full-пресет (Opus) не затронут.

---

### 7. Explicit Round Flag

**Контекст**: система определяет R1 vs R2 по наличию `mediator_synthesis` в контексте. Если Mediator (Stage 5) падает, R2 персоны думают, что они в R1 — получают неправильный промпт и не видят feedback других персон. HIGH IMPACT gotcha.

**Что делать**: добавить `round: Literal[1, 2]` в `PipelineContext`. Передавать явно в каждую персону. Не полагаться на наличие mediator output.

**Сложность**: низкая. Одно поле в `PipelineContext`, условная передача в `_run_delphi_r1()` и `_run_delphi_r2()`.

**Важность**: средняя. Проявляется только при падении Mediator (~5% прогонов).

---

## Backlog

Задачи без фиксированного приоритета. Разделены по направлениям.

---

### Направление: Архетипы трейдеров (Phase 7–9)

Ожидает feedback команды по [RFC](discussion.md).

**Phase 7 — Feature Engineering**: расширение BettorProfile с 6 до 12 признаков (category_entropy, pl_ratio, early_entry_score, mean_market_conviction, position_flip_rate, maker_fraction). UMAP preprocessing для datasets > 100K.

- *Сложность*: средняя. Вычисление features из существующих 470M trades. Требует market category tags (возможно join через Polymarket API).
- *Важность*: высокая — необходимое условие для Phase 8–9.

**Phase 8 — Semi-supervised Labeling**: LLM лейблит ~20 HDBSCAN центроидов ($0.10) + ~340K ambiguous кошельков ($13/run). ML классифицирует остальные 1.3M.

- *Сложность*: средняя. Новый модуль `src/inverse/archetype.py`. LLM structured output + label propagation.
- *Важность*: высокая — даёт именованные архетипы вместо безымянных кластеров.

**Phase 9 — Archetype-Weighted Consensus**: модификация `compute_informed_signal()` — weight × archetype_fit(market_category). Walk-forward BSS валидация.

- *Сложность*: низкая (формула). Высокая (валидация: 22 фолда × N архетипов).
- *Важность*: **критическая** — это финальная проверка: улучшает ли BSS > +0.196.

---

### Направление: Калибровка и оценка

**Per-Persona Weight Update (B.6)**: динамическая подстройка весов 5 Дельфи-персон по историческому BS.

- *Условие старта*: per-persona BS variance > 0.10 (не измерено).
- *Сложность*: низкая. Добавить tracking per-persona BS → обновлять `initial_weight` в `personas.py`.
- *Важность*: средняя. Потенциально улучшает агрегацию в Judge.

**Platt Scaling в Judge (B.5)**: логистическая регрессия для калибровки выходных вероятностей.

- *Условие старта*: reliability > 0.05 (требует данные из Retrospective Eval).
- *Сложность*: низкая. Scipy logistic fit, ~30 LOC в `judge.py`.
- *Важность*: средняя. Satopää extremizing уже частично покрывает.

**Калибровка BERTScore (B.4)**: настройка порогов для оценки стилистического соответствия заголовков.

- *Условие старта*: после Retrospective Eval Pilot.
- *Сложность*: низкая. Подбор threshold на validation set.
- *Важность*: низкая. Влияет только на метрику оценки, не на генерацию.

---

### Направление: Инфраструктура и надёжность

**Observability: метрики и алертинг**: сейчас есть health endpoint и per-agent логирование, но нет Prometheus/Grafana и нет алертинга при падении pipeline.

- *Сложность*: средняя. `prometheus_fastapi_instrumentator` для FastAPI + custom metrics (pipeline_duration, llm_cost_total, stage_errors). Grafana dashboard.
- *Важность*: средняя для текущего масштаба. Высокая при росте пользователей.

**CI/CD pipeline**: ~~сейчас деплой ручной~~ **Готово (v0.9.7).** GitHub Actions: `ruff check` + `pytest` + CSS build на push/PR. Auto-deploy на VPS через SSH после прохождения CI. Security audit (`uv audit`) по расписанию.

**Database Audit & PostgreSQL Assessment**: аудит SQLite-схемы (неиспользуемые поля, индексы). Оценка миграции на PostgreSQL.

- *Сложность*: средняя (аудит), высокая (миграция).
- *Важность*: низкая сейчас. SQLite справляется при текущей нагрузке (~100K predictions).

**Deployment Runbook**: документация для воспроизведения серверной среды с нуля — от создания VPS до `docker compose up`.

- *Сложность*: низкая. Документирование существующего процесса.
- *Важность*: средняя. Критична при смене сервера или добавлении team members.

---

### Направление: Данные и интеграции

**Kalshi / OECD Integration (B.2)**: дополнительные источники данных для enrichment.

- *Сложность*: средняя. Kalshi API аналогичен Polymarket. OECD — REST API.
- *Важность*: низкая. Polymarket покрывает основные потребности.

**HuggingFace Dataset (B.11)**: публикация данных (N=500+ resolved predictions) для воспроизводимости.

- *Условие старта*: после Retrospective Eval Pilot (нужны ground truth данные).
- *Сложность*: низкая. Parquet export + dataset card.
- *Важность*: средняя. Для академической публикации и community trust.

**Правовая проверка (B.9)**: licensing (MIT? Apache?), compliance, terms of use.

- *Условие старта*: до публичного деплоя.
- *Сложность*: нетехническая.
- *Важность*: высокая для публичного запуска.

---

## Определение v1.0

Версия v1.0 = **production-ready prediction system** с доказанной точностью.

**Минимальные критерии:**

- [ ] Retrospective Eval Pilot пройден (CompositeScore > baseline)
- [ ] Checkpoint & Resume реализован (cost recovery при timeout)
- [ ] QualityGate revision pipeline (не теряем заголовки)
- [ ] Event-level storage (per-prediction market comparison)
- [ ] LLM provider fallback (не зависим от одного OpenRouter)
- [ ] Round flag (explicit R1/R2, без implicit detection)
- [ ] Правовая проверка пройдена

**Желательные:**

- [ ] Per-persona weight update (B.6)
- [ ] Platt scaling calibration (B.5)
- [x] CI/CD pipeline с автотестами
- [ ] Observability (Prometheus + Grafana)

---

## Направление: Literature-Driven Improvements (Claude Code Sprint Plan)

!!! info "Контекст"
    Раздел добавлен на основе литературного обзора 24 статей (апрель 2026). Полная документация: `docs/conference-imemo/` (конспекты, литобзор, аналитическая записка). Реализация через Claude Code субагентов.

Каждое улучшение подкреплено конкретным исследованием. Задачи приоритизированы по матрице impact × effort.

---

### Sprint 1 — Quick Wins (P1, ~2–3 дня)

Низкое усилие, высокий или диагностический impact. Каждая задача — 15–50 строк кода, 0 дополнительных LLM-вызовов в production.

#### 1.1 Position-Concentration Filter (whale filter)

**Файл:** `src/inverse/signal.py` → `compute_enriched_signal()`

**Проблема.** Формула веса трейдера: `w = (1 - BS) × size × recency`. Если один кошелёк держит 20% инвентаря рынка, его `size` доминирует. Clinton & Huang (2025, SocArXiv) документируют: трейдер Théo — $42M, 20% Trump-YES — систематически смещал цену Polymarket. Наш `enriched_signal` в whale-dominated рынке будет отражать позицию одного человека, а не informed consensus.

**Литература:**

- Clinton, J.; Huang, T. (2025). "Prediction Markets? The Accuracy and Efficiency of $2.4 Billion in the 2024 Presidential Election." → 62/65 дней P(H)+P(T) ≠ $1.00; whale distortion как механизм.
- Mitts, J.; Ofir, M. (2026). "From Iran to Taylor Swift: Anomalous Profits in Polymarket." → 93K рынков, $143M аномального profit, 69.9% win rate у выявленных крупных трейдеров.

**Решение.** Перед weighted mean в `compute_enriched_signal()`: cap max wallet share at 15% of total position size.

```python
total_size = sum(s for _, s in positions)
for i, (pos, size) in enumerate(positions):
    capped = min(size, 0.15 * total_size)
    positions[i] = (pos, capped)
```

**Порог 15%** — начальный; оптимизировать через ablation на 22 фолдах walk-forward.

**Тест:** BSS до/после на 22 фолдах. Ожидаемый прирост: +0.005–0.020 на фолдах с whale-dominated рынками.

**Усилие:** ~20 строк.

---

#### 1.2 Calibration Consistency Check

**Файл:** `src/agents/forecasters/judge.py` → после `_build_predicted_timeline()`, перед `_rank_predictions()`

**Проблема.** Judge агрегирует вероятности по event threads, но не проверяет логическую согласованность. Если три взаимоисключающих заголовка получают P = 0.45, 0.40, 0.35 → сумма 1.20 = логически невозможно. Clinton & Huang (2025) показали: Polymarket нарушал P(A)+P(B)=1 в 95% предвыборного периода.

**Литература:**

- Mantic AI (2026, Metaculus Fall Cup, 4-е из 539). Toby Shevlane: «probability distributions across mutually exclusive and exhaustive questions must sum to ~100%, and logically related questions must respect ordering constraints». Structural calibration check — ключ к top-1% результату.

**Решение.** Детерминированный validation pass (0 LLM-вызовов):

1. Сгруппировать `TimelineEntry` по `event_thread_id`.
2. Для каждой группы с `scenario_type = BASELINE`: проверить `sum(calibrated_prob)`.
3. Если sum > 1.05 → нормализовать через softmax, логировать warning.
4. Если два заголовка на одно событие с `|p₁ - p₂| > 0.30` → логировать divergence flag.

**Тест:** 10–20 dry runs, посчитать % event_threads с sum > 1.0.

**Усилие:** ~50 строк.

---

#### 1.3 BSS Stratification by Market Depth

**Файл:** `src/eval/metrics.py` или `scripts/eval_walk_forward.py`

**Проблема.** Mean BSS +0.196 агрегирует все рынки. Sethi et al. (2025) показали: модели бьют рынки на thin races (House: FiveThirtyEight BS 0.158 vs Polymarket 0.204), рынки бьют модели на presidential (все модели: double-digit negative returns). Возможно, наш BSS gain сконцентрирован в thin markets, а на deep markets мы на уровне baseline или хуже.

**Литература:**

- Sethi, R. et al. (2025). "Political Prediction and the Wisdom of Crowds." ACM CI '25, pp. 214–225. → 41 контракт, модели > рынки на Senate/House, рынки > модели на presidency.
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading." Econometrica, 53(6). → 1/λ = market depth. Чем глубже рынок, тем полнее информация в цене, тем сложнее её превзойти.

**Решение.** Разбить resolved markets по квартилям `total_volume`:

- Q1: thin (< 25th percentile volume)
- Q2–Q3: medium
- Q4: deep (> 75th percentile)

Вычислить BSS отдельно для каждого. Добавить в output `eval_walk_forward.py`.

**Тест:** `uv run python scripts/eval_walk_forward.py` → новая таблица BSS по квартилям.

**Усилие:** ~30 строк.

---

#### 1.4 Permutation Test (Skill vs Luck)

**Файл:** `src/eval/metrics.py`

**Проблема.** Текущий sign test (p = 2.38×10⁻⁷) — сильное свидетельство, но тестирует только знак BSS. Permutation test — независимое подтверждение, что именно INFORMED-tier трейдеры несут сигнал, а не случайная подвыборка.

**Литература:**

- Mellers, B. et al. (2015). "Identifying and Cultivating Superforecasters." Perspectives on Psychological Science, 10(3), 267–281. → GJP: year-to-year correlation r=0.65, 70% retention — доказывает skill, не luck.
- DeLong, J.B. et al. (1990). "Noise Trader Risk in Financial Markets." JPE, 98(4), 703–738. → Noise traders могут зарабатывать через structural risk premium (не из-за skill). Permutation test различает.

**Решение.** 1000 permutations: shuffle tier assignments (INFORMED ↔ NOISE), пересчитать BSS для каждой. Сравнить реальный BSS с permuted distribution. Если real > 95th percentile → skill confirmed.

```python
def permutation_test(profiles, trades, ..., n_permutations=1000):
    real_bss = compute_bss(profiles, trades)
    permuted = []
    for _ in range(n_permutations):
        shuffled = shuffle_tiers(profiles)
        permuted.append(compute_bss(shuffled, trades))
    p_value = sum(1 for p in permuted if p >= real_bss) / n_permutations
    return real_bss, permuted, p_value
```

**Тест:** p-value < 0.01 → INFORMED tier несёт genuine signal.

**Усилие:** ~30 строк, ~1 минута вычислений (1000 shuffles × 22 folds).

---

#### 1.5 Mediator Fallback Key Question

**Файл:** `src/agents/forecasters/mediator.py` → fallback branch (строки 112-119)

**Проблема.** Если LLM parse fails, `key_question = ""`. Персона в R2 получает dispute без вопроса = функционально median-only feedback = нулевой gain.

**Литература:**

- Williams, A.R. et al. (2025). "DeLLMphi: A Multi-Turn Method for Multi-Agent Forecasting." NeurIPS MTI-LLM. → Прямой ablation: mediator=median → BS 0.165 (0 gain); mediator=arguments → BS 0.157 (full gain). Разница 0.008 BS = 28% gap closure между public forecasters и superforecasters.
- Rowe, G.; Wright, G. (1999). "The Delphi Technique as a Forecasting Tool." IJF, 15(4), 353–375. → «The greatest degree of improvement in accuracy over rounds occurred in the reasons condition.»

**Решение.** Алгоритмический fallback при пустом `key_question`:

```python
if not dispute.key_question:
    max_pos = max(dispute.positions, key=lambda p: p.probability)
    min_pos = min(dispute.positions, key=lambda p: p.probability)
    dispute.key_question = (
        f"{max_pos.agent_label} оценивает P={max_pos.probability:.2f}, "
        f"{min_pos.agent_label} оценивает P={min_pos.probability:.2f}. "
        f"Какой конкретный фактор объясняет расхождение "
        f"в {abs(max_pos.probability - min_pos.probability)*100:.0f} пп?"
    )
```

**Тест:** Проверить последние 20 dry runs: % disputes с пустым key_question до/после.

**Усилие:** ~15 строк.

---

#### 1.6 Adversarial Persona Audit (read-only, диагностика)

**Файл:** Анализ существующих dry run outputs, не изменение кода.

**Проблема.** Bertolotti & Mari (2025, arXiv:2502.21092) зафиксировали homogeneity bias при LLM-Дельфи: «predominance of positive perspectives, challenges mentioned only tangentially». Lorenz & Fritz (2026, arXiv:2602.08889) уточняют: «a single LLM queried with identical prompts risks mode collapse: a narrow distribution of estimates».

У нас Devil's Advocate имеет явный adversarial mandate (pre-mortem, steelmanning, goal ≠ Brier minimization). Но работает ли это на практике?

**Литература:**

- Bertolotti, F.; Mari, L. (2025). "An LLM-based Delphi Study to Predict GenAI Evolution." arXiv:2502.21092. → 15 агентов, 5 раундов, gpt-4o-mini: «problems framed in terms of GenAI's lack of diffusion, implicitly assuming broader adoption is inherently beneficial».
- DeLLMphi (Williams et al., 2025). → Identical experts: 0.159 ±0.016; diverse experts: 0.157 ±0.003. Diversity снижает дисперсию в 5.3×.

**Метрика аудита.** Из последних 20 dry runs извлечь R1-output Devil's Advocate. Вычислить:

- `adversarial_divergence` = % случаев где `|DA_prob - median(others)| > 0.15`
- Порог: если < 30% — промпт недостаточно adversarial, нужна правка.

**Усилие:** Скрипт анализа ~50 строк.

---

### Sprint 2 — Evaluation & Calibration (P2, ~1–2 недели)

Среднее усилие, диагностический и calibration impact.

#### 2.1 Profitability Test Metric

**Файл:** `src/eval/metrics.py`

**Литература:**

- Sethi, R. et al. (2025). ACM CI '25. → Profitability test vs Brier score: Silver Bulletin бьёт FiveThirtyEight по BS (convention bounce credit), но проигрывает по profitability (buy-high-sell-low pattern). «Conventional measures reward modeling flaws that result in predictable reversals.»

**Решение.** `compute_profitability_test()`: для каждого resolved market, если `p_consensus > p_market` → virtual buy YES; payoff = `(outcome - p_market)`. Cumulative sum = profitability. Положительный = genuine informational edge.

**Усилие:** ~80 строк.

---

#### 2.2 Evidence Sensitivity Ablation

**Файл:** `scripts/dry_run.py` → новый флаг `--ablation=context_stripped`

**Литература:**

- Lorenz, T.; Fritz, M. (2026). "Scalable Delphi." arXiv:2602.08889. → Ablation None → Benchmark → Model → Full: correlation r растёт с ~0 до 0.87–0.95. «If models were recalling memorized results, we would expect the opposite pattern.»

**Решение.** Запустить pipeline с пустыми `event_threads` и `trajectories` (только outlet + date). Если BSS на full context >> BSS на stripped context → pipeline genuinely использует контекст. Если нет → pipeline опирается на LLM prior, не на наши данные.

**Усилие:** ~100 строк (ablation mode в orchestrator).

---

#### 2.3 Platt Scaling Audit (a=1.5 → investigate)

**Файл:** `src/agents/forecasters/judge.py` → `_platt_scale()`, a=1.5

**Литература:**

- Turtel, B.; Franklin, D.; Schoenegger, P. (2025). "LLMs Can Teach Themselves to Better Predict the Future." TMLR. arXiv:2502.05253. → Acquiescence bias: LLM среднее ~57% при 45% positive outcomes. LLM переоценивают, не недооценивают. Extremization (a>1) усиливает этот bias.
- Наш собственный ablation Phase 5: extremizing ухудшил BSS на −64%.
- Atanasov, P. et al. (2024). "Crowd Prediction Systems." IJF. → a=1.32 калиброван для **человеческих** прогнозистов, не для LLM.

**Решение.** Запустить Murphy decomposition (REL component уже реализован в `src/eval/metrics.py`) на 22 фолдах. Если calibration slope > 1.0 → overconfidence confirmed → снизить a до 1.0 или 0.8.

**Усилие:** Анализ существующих метрик + потенциально 1 строка (изменение `self.a`).

---

#### 2.4 Kyle λ Early-Entry Weighting

**Файл:** `src/inverse/signal.py`, `src/inverse/profiler.py`

**Литература:**

- Kyle, A.S. (1985). Econometrica, 53(6), 1315–1335. → λ = √(Σ₀/σ²_u); в continuous equilibrium λ = const; 1/λ = market depth.
- arXiv:2603.03136 (2026). "Anatomy of Polymarket." → Kyle λ на президентских контрактах: 0.518 → 0.01–0.04 (50× change) за жизнь рынка. Ранние сделки при high λ (thin market) = высокий информационный сигнал.

**Решение.** Добавить `early_entry_score` в `BettorProfile`: для каждого трейдера — в каком проценте жизни рынка он вошёл. Использовать как множитель в весе: `weight *= 1.0 + 0.5 × (1.0 - entry_percentile)`. Ранние входы → ×1.5, поздние → ×1.0.

**Усилие:** ~80 строк в profiler + signal.

---

### Sprint 3 — Archetype Architecture (P3, ~6–8 недель)

Высокое усилие, потенциально наибольший BSS gain.

Детальное описание — в [Discussion RFC](discussion.md). Литературная валидация по 6 тезисам проведена в `docs/conference-imemo/notes/D_archetypes/` (6 конспектов, 27K слов).

#### 3.1 Phase 7: Feature Engineering

Расширение `BettorProfile` с текущих полей до 12 признаков. Литературная база:

- Barber, B.M.; Odean, T. (2013). "The Behavior of Individual Investors." Handbook of Finance. → 4 архетипа (overconfident, sensation-seeker, familiarity, sophisticated minority), параметризованных через turnover, concentration, local bias.
- Wang, H. (2025). "Heterogeneous Trader Responses." arXiv:2505.01962. → Параметрическое пространство (γ, IL) для retail/pension/institutional/hedge.
- Mahfouz, M. et al. (2021). "Learning to Classify Trading Agents." ICAIF. → LOB features + neural net F1=0.61–0.75.

#### 3.2 Phase 8: Semi-supervised Labeling

- arXiv:2505.21662 (2025). → Supervised SVM/DNN = 91–99% accuracy; unsupervised HDBSCAN alone = «may give misleading results» (Fundamentalists F1=0.00).

#### 3.3 Phase 9: Archetype-Weighted Consensus

- Discussion.md Тезис 5. Market-Archetype Performance Matrix → bias correction per (market_category, archetype) pair.

---

### Sprint 4 — Advanced (P4, 12+ недель)

#### 4.1 Point-in-Time Backtesting Dataset

**Литература:** Mantic AI (2026). → «Restricting information access to a specific past date and asking questions whose answers are now known» — enables evaluation «from months to milliseconds». Prerequisite для DSPy optimization и RL fine-tuning.

#### 4.2 DSPy MIPROv2 Prompt Optimization

**Литература:** Discussion.md Тезис 4. DSPy (ICLR 2024): LLM pipeline = computational graph; MIPROv2 оптимизирует prompt parameters на фиксированной топологии. GPT-3.5 на GSM8K: 25.2% → 81.6%, cost $2, 10 minutes. Требует backtesting corpus из 4.1.

#### 4.3 DSSW Noise Trader Risk Premium Correction

**Литература:** DeLong, J.B. et al. (1990). JPE, 98(4). → NTR = (2γμ²σ²ρ) / [r(1+r)²]. Коррекция рыночной цены на noise premium перед использованием как baseline. Высокое усилие (оценка μ и σ²ρ per market per fold).

---

### Что НЕ стоит делать (подтверждено литературой + нашими ablation)

| Антипаттерн | Наш ablation | Литературное объяснение |
|---|---|---|
| **Extremizing (a > 1.0)** | Phase 5: BSS −64% | Turtel & Schoenegger (2025): LLM acquiescence bias (~57% mean при 45% positive outcomes). Extremization усиливает, а не корректирует bias. |
| **Volume gate (отсечение thin markets)** | Phase 5: BSS −64% | Sethi et al. (2025): модели бьют рынки именно на thin markets. Clinton & Huang (2025): «markets with more trading activity are no more accurate, controlling for event type». |
| **3+ раунда Дельфи** | Не тестировали | Dalkey & Helmer (1963): основная конвергенция к Q3. DeLLMphi (2025): «most substantial opinion updates occur in round 0→1». Каждый раунд = +$8–10 cost. |
| **Single agent + self-feedback** | Не тестировали | DeLLMphi (2025): BS 0.172 (хуже baseline 0.174). Self-feedback без genuine multi-agent diversity = антипаттерн. |
| **Увеличение числа персон > 5** | Не тестировали | Bertolotti & Mari (2025): 15 vs 5 агентов — нет улучшения topic diversity. Lorenz & Fritz (2026): персонная конфигурация влияет на дисперсию, не на среднее. |

---

### Библиография литобзора

Полные конспекты: `docs/conference-imemo/notes/` (24 файла, 84K слов).
Синтетический литобзор: `docs/conference-imemo/lit-review.md`.
Аналитическая записка: `docs/conference-imemo/improvements.md`.

Ключевые источники для Sprint 1–2:

1. Arrow, K.J. et al. (2008). Science, 320(5878), 877–878.
2. Atanasov, P. et al. (2024). IJF. DOI: 10.1016/j.ijforecast.2023.12.009.
3. Bertolotti, F.; Mari, L. (2025). arXiv:2502.21092.
4. Clinton, J.; Huang, T. (2025). SocArXiv. DOI: 10.31219/osf.io/d5yx2.
5. Dalkey, N.; Helmer, O. (1963). Management Science, 9(3), 458–467.
6. DeLong, J.B. et al. (1990). JPE, 98(4), 703–738.
7. Kyle, A.S. (1985). Econometrica, 53(6), 1315–1335.
8. Lorenz, T.; Fritz, M. (2026). arXiv:2602.08889.
9. Mellers, B. et al. (2015). Perspectives on Psychological Science, 10(3), 267–281.
10. Rowe, G.; Wright, G. (1999). IJF, 15(4), 353–375.
11. Sethi, R. et al. (2025). ACM CI '25, pp. 214–225.
12. Turtel, B. et al. (2025). TMLR. arXiv:2502.05253.
13. Wang, H. (2025). arXiv:2505.01962.
14. Williams, A.R. et al. (2025). NeurIPS MTI-LLM Workshop.
15. Wolfers, J.; Zitzewitz, E. (2004). JEP, 18(2), 107–126.
