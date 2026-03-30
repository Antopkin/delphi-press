# Inverse Problem Phase 5: Live Integration + BSS Variants + Publication Prep

> Промпт для следующей сессии Claude Code.
> Контекст: Phase 4 (v0.9.2) завершена — 1242 теста, PR #1 merged в main.

---

## Контекст: что уже сделано

### Phase 2 (v0.9.0)
- Parquet store (506→62 МБ), Bayesian shrinkage, parametric λ (Exp/Weibull), HDBSCAN clustering
- Enriched signal + extremizing, clone validation, 156 inverse тестов

### Phase 3 (v0.9.1)
- Adaptive extremizing: d из inter-bettor position_std (Satopää et al. 2014)
- Soft volume gate: $10K–$100K gradient (Clinton & Huang 2024)
- `as_of` temporal cutoff, `timing_score`, Murphy decomposition + ECE + calibration slope
- 6 crash fixes. E2E server verified: 348K INFORMED profiles in 7.5s

### Phase 4 (v0.9.2) — ТЕКУЩАЯ СЕССИЯ ЗАВЕРШИЛА ЭТО
- **Walk-forward evaluation**: 22 фолда, robust mean BSS = **+0.127** (12.7% BS reduction), 100% positive
- **Temporal leak найден и исправлён**: pre-aggregated позиции включали trades после cutoff T. Fix: bucketed partial aggregates — один скан 33 ГБ → 2.4 ГБ `_merged_bucketed.parquet` (30-day time buckets). Суммы composable, averages нет.
- **Bucketed approach**: per-fold 4 сек (было 15 мин), total 82 мин (было 5+ часов + OOM)
- **Docker**: pyarrow через `--extra inverse`, bind mount `/data/inverse`, worker healthcheck fix
- **Deploy**: PR #1 merged, 4/4 containers healthy, `delphi.antopkin.ru` live

### Что есть на сервере (`deploy@213.165.220.144`)
```
/home/deploy/data/inverse/
  bettor_profiles.parquet          62 МБ  (1.7M profiles, 348K informed)
  bettor_profiles_summary.json     216 B
  hf_cache/
    trades.parquet                 33 ГБ  (470M raw trades, re-downloaded)
    _maker_agg.parquet             1.5 ГБ (pre-aggregated maker)
    _taker_agg.parquet             2.9 ГБ (pre-aggregated taker)
    _merged_bucketed.parquet       2.4 ГБ (82.6M rows, 30-day time buckets)
    _merged_positions.parquet      3.8 ГБ (old, with temporal leak)
    markets.parquet                150 МБ (572K markets)
  walk_forward_clean.csv           3.4 КБ (22-fold results)
```

**Docker**: 4 контейнера (app + worker + redis + nginx). Production на `main` branch.
**Диск**: 138 ГБ total, ~35 ГБ свободно.
**RAM**: 8 ГБ. DuckDB memory_limit=2GB работает без OOM.

---

## Задачи (3 основные + 2 опциональные)

### Задача 1: Live trades integration — enrichment для текущих рынков

**Проблема**: enrichment (informed consensus) работает в walk-forward eval, но НЕ работает в production pipeline. `dry_run.py --profiles` загружает профили, но enrichment не срабатывает — нет trades для текущих рынков.

**Цепочка**: `ForesightCollector` → находит matching Polymarket markets → нужны trades на этих markets → `compute_enriched_signal()` → Judge использует informed signal.

**Два подхода** (выбрать один или оба, исследовать trade-offs):

**Подход A: CLOB API (real-time)**
- Polymarket CLOB API даёт текущие orders/trades по market_id
- `src/data_sources/foresight.py` уже имеет `PolymarketCLOBClient`
- Нужно: для каждого matching market → fetch recent trades → convert to TradeRecord → compute signal
- Плюс: real-time, свежие данные
- Минус: rate limits, API stability, нужен per-request fetch

**Подход B: Periodic bulk download (batch)**
- Cron job: раз в неделю скачать свежий `trades.parquet` с HuggingFace, rebuild bucketed + profiles
- Enrichment использует pre-built profiles (уже работает)
- Плюс: простой, надёжный, переиспользует существующий pipeline
- Минус: задержка до 7 дней, профили не включают последние trades

**Исследовать**: запустить research-агентов для оценки:
- Polymarket CLOB API: rate limits, endpoints для trades по condition_id
- HuggingFace dataset `SII-WANGZJ/Polymarket_data`: как часто обновляется?
- Есть ли другие bulk data sources для Polymarket trades?

**Файлы для чтения**:
- `src/data_sources/foresight.py` — PolymarketCLOBClient
- `src/agents/collectors/foresight_collector.py` — как collector передаёт данные в pipeline
- `scripts/dry_run.py` — как `--profiles` и `--trades` интегрируются
- `src/inverse/signal.py` — `compute_enriched_signal()`, `compute_informed_signal()`
- `src/inverse/store.py` — `load_profiles()`

### Задача 2: Incremental BSS variants (Task 6 из Phase 4)

**Что сделать**: Запустить walk-forward с разными feature flags на bucketed данных.

```bash
# На сервере, каждый вариант ~2-5 мин:
# 1. Baseline (current, уже есть: BSS +0.127)
# 2. +adaptive extremize (d from position_std)
# 3. +volume gate (skip markets < $10K)
# 4. +both
# 5. +timing_score weighting
```

**Нужно**: реализовать `--adaptive-extremize` и `--volume-gate` flags в `scripts/eval_walk_forward.py`. Были удалены в Phase 4 (dead CLI args). Вернуть и реализовать логику.

**Логика adaptive extremize** (из `src/inverse/signal.py:_compute_adaptive_d()`):
```python
d = 1.0 + 2.0 * statistics.stdev(informed_positions)  # clamped [1.0, 2.0]
informed_prob = extremize(informed_prob, d)
```

**Логика volume gate** (из `src/inverse/signal.py`):
```python
gate = max(0.0, min(1.0, (market_volume - 10000) / (100000 - 10000)))
final = gate * informed_prob + (1 - gate) * raw_prob
```

**Файлы**:
- `scripts/eval_walk_forward.py` — добавить flags + логику в `compute_fold_signals()`
- `src/inverse/signal.py` — `_compute_adaptive_d()`, `extremize()`, volume gate constants
- `tasks/inverse_phase4_results.md` — документировать результаты вариантов

### Задача 3: Fix version в health endpoint

**Проблема**: `curl .../api/v1/health` возвращает `"version":"0.8.0"` вместо `"0.9.2"`.

**Найти**: где hardcoded version string. Скорее всего в `src/main.py` или `src/api/`.

### Задача 4 (опциональная): Bootstrap CI для BSS

**Для публикации** нужны confidence intervals. Для каждого fold: resample test markets 1000 раз, compute BSS → 2.5th/97.5th percentile.

С 22/22 positive folds, sign test даёт p < 0.001. Но per-fold CI покажет uncertainty.

### Задача 5 (опциональная): Cron для обновления профилей

Weekly cron на сервере:
1. `wget` свежий trades.parquet с HuggingFace (если обновился)
2. `python3 scripts/duckdb_build_bucketed.py` → rebuild bucketed
3. `python3 scripts/duckdb_build_profiles.py` → rebuild profiles
4. Docker restart worker (чтобы подхватил новые профили)

---

## Принципы работы

### Субагенты — использовать активно
- **Research agents**: исследовать Polymarket CLOB API, HuggingFace dataset frequency, другие data sources
- **Data Engineer**: оценить memory/disk trade-offs для live vs batch подхода
- **AI Engineer**: методологическая оценка BSS variants — какие стоит запускать?
- **Code reviewer**: ревью перед merge
- **Explore**: исследование кодовой базы перед изменениями

### TDD (Red → Green → Refactor)
- Каждая фича начинается с failing test
- `uv run pytest tests/ -v` после каждого шага

### Коммиты после каждого шага
```
git add ... && git commit -m "feat/fix/docs: ..."
```

### Web search — если нужно
- Polymarket CLOB API docs: актуальные endpoints, rate limits
- HuggingFace dataset update frequency
- Best practices для live prediction market data feeds

---

## Файлы и спеки

- **Walk-forward результаты**: `tasks/inverse_phase4_results.md` (22 фолда, BSS таблица)
- **Walk-forward скрипт**: `scripts/eval_walk_forward.py` (bucketed mode, DuckDB)
- **Bucketed build**: `scripts/duckdb_build_bucketed.py` (33 ГБ → 2.4 ГБ)
- **DuckDB profiler**: `scripts/duckdb_build_profiles.py` (legacy, без temporal fix)
- **Signal**: `src/inverse/signal.py` (adaptive_extremize, volume_gate, compute_enriched_signal)
- **Profiler**: `src/inverse/profiler.py` (as_of, timing_score, Bayesian shrinkage)
- **Store**: `src/inverse/store.py` (Parquet + JSON, load_profiles)
- **Schemas**: `src/inverse/schemas.py` (BettorProfile, InformedSignal)
- **CLOB client**: `src/data_sources/foresight.py` (PolymarketCLOBClient)
- **Collector**: `src/agents/collectors/foresight_collector.py`
- **Dry run**: `scripts/dry_run.py` (--profiles, --trades)
- **Metrics**: `src/eval/metrics.py` (brier_decomposition, calibration_slope, ECE)
- **Methodology**: `docs/methodology-inverse-problem.md`
- **Сервер**: `deploy@213.165.220.144`, данные в `/home/deploy/data/inverse/`

---

## Критерии успеха

| Метрика | Порог | Что означает |
|---|---|---|
| Live enrichment fires | > 0 markets enriched | Pipeline integration works |
| BSS variants documented | 3-5 variants compared | Feature ablation complete |
| Adaptive extremize BSS | > baseline +0.127 | Feature improves signal |
| Volume gate BSS | > baseline or justified removal | Feature evaluated |
| Health version | "0.9.2" | Cosmetic fix |
| Bootstrap CI | 95% CI excludes 0 | Statistically significant |

---

## Приоритет

1. **Задача 2** (BSS variants) — быстрая, ~30 мин, ценный результат
2. **Задача 3** (version fix) — 5 мин
3. **Задача 1** (live integration) — основная работа сессии
4. Задача 4-5 — если останется время
