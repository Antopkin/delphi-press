# Inverse Problem Phase 4: Walk-forward eval + E2E pipeline + deploy

> Промпт для следующей сессии Claude Code.
> Контекст: Phase 3 (v0.9.1) завершена — 1226 тестов, 6 коммитов на `feat/inverse-phase2`.

---

## Контекст: что уже сделано

### Phase 2 (v0.9.0)
- Parquet store (506→62 МБ), Bayesian shrinkage, parametric λ (Exp/Weibull), HDBSCAN clustering
- Enriched signal + extremizing, clone validation, 156 inverse тестов

### Phase 3 (v0.9.1)
- **Adaptive extremizing**: d из inter-bettor position_std (не |informed-raw|). Satopää et al. 2014.
- **Soft volume gate**: $10K–$100K gradient (Clinton & Huang 2024).
- **`as_of` temporal cutoff**: фильтрует trades И resolutions по дате. No look-ahead bias.
- **`timing_score`**: volume-weighted fraction of market lifetime at bet time. [INFERRED] от Bürgi et al.
- **3 новые метрики**: Murphy decomposition (REL/RES/UNC), calibration slope (OLS), ECE.
- **6 crash fixes**: extremize bounds, timezone parsing, JSON validation, schema constraints.
- **E2E server verified**: Parquet load 348K INFORMED profiles in 7.5s.
- **Citation corrections**: Akey et al. 2025 (primary for tier profiling), Mitts & Ofir 2026 (general principle).

### Что есть на сервере (`deploy@213.165.220.144`)
```
/home/deploy/data/inverse/
  bettor_profiles.json          506 МБ  (legacy, 1.7M profiles)
  bettor_profiles.parquet        62 МБ  (ZSTD, same data)
  bettor_profiles_summary.json   216 B  (sidecar)
  hf_cache/
    _maker_agg.parquet          1.5 ГБ  (maker trades)
    _taker_agg.parquet          2.9 ГБ  (taker trades)
    markets.parquet             150 МБ  (market metadata с endDate, createdAt)
```

**Docker**: 4 контейнера (app + worker + redis + nginx). Production на `main` branch.
**Ветка**: `feat/inverse-phase2` — НЕ замержена в main. 6 коммитов Phase 3.

---

## Задачи (все 7, в порядке выполнения)

### Задача 1: `scripts/eval_walk_forward.py` — DuckDB backend

**Что сделать**: Написать walk-forward eval скрипт, работающий с Parquet через DuckDB.

**ВАЖНО**: НЕ использовать Python profiler (`build_bettor_profiles()`) на полном датасете — 470M trades = 140+ ГБ RAM = OOM. Только DuckDB с predicate pushdown.

**Данные на сервере**: `hf_cache/_maker_agg.parquet`, `_taker_agg.parquet`, `markets.parquet`.

**Алгоритм**:
1. Загрузить trades + markets через DuckDB
2. T_start = earliest_date + burn_in_days (default 180)
3. Для каждого fold:
   a. Train: trades с timestamp < T, resolutions с resolution_date < T
   b. Test: markets resolved в [T, T + test_window)
   c. BUILD PROFILES через DuckDB SQL (GROUP BY user_id, аналог Python profiler)
   d. Для каждого test market: compute informed signal
   e. Per-fold метрики: BSS, Murphy decomposition, calibration slope, ECE
4. Advance T by step_days
5. Aggregate: mean ± std, median, IQR, min fold BSS, fraction BSS>0, trend

**Параметры CLI**:
```
--data-dir    PATH   /home/deploy/data/inverse/hf_cache/
--profiles    PATH   bettor_profiles.parquet (optional, для сравнения)
--burn-in     INT    180  (дней)
--step        INT    60   (дней, non-overlapping default — честные CI)
--test-window INT    60   (дней)
--min-bets    INT    5    (walk-forward → низкий порог + shrinkage)
--output-csv  PATH   results/walk_forward_folds.csv
--verbose
```

**Выходные колонки per-fold CSV**: fold_id, train_start, train_end, test_start, test_end, n_train_markets, n_test_markets, n_profiled, n_informed, bss_vs_raw, bs_raw, bs_informed, reliability, resolution, uncertainty, calibration_slope, ece, coverage, tier_stability.

**Метрики уже реализованы** в `src/eval/metrics.py`: `brier_decomposition()`, `calibration_slope()`, `expected_calibration_error()`.

**TDD**: RED → GREEN → REFACTOR. Тесты на synthetic data перед реальным запуском.

**Ссылки**: `scripts/duckdb_build_profiles.py` (существующий DuckDB pipeline — переиспользовать SQL паттерны), `scripts/eval_informed_consensus.py` (существующий eval — переиспользовать сигнатуры).

### Задача 2: Запуск walk-forward на сервере + baseline BSS

**Что сделать**: SSH на сервер, запустить `eval_walk_forward.py` с данными из hf_cache/.

**Проверить**:
- BSS > 0 → informed consensus помогает
- BSS ≤ 0 → рынок эффективен (валидный научный результат, документировать)
- Calibration slope ≈ 1.0 → модель калибрована
- Tier stability > 60% → INFORMED бетторы стабильны между фолдами

**Зафиксировать результат** в `tasks/inverse_phase4_results.md`.

Это **первое в мире walk-forward evaluation bettor profiles на Polymarket** — publishable novelty.

### Задача 3: Dry run pipeline с профилями

**Что сделать**: Запустить `scripts/dry_run.py` с реальными профилями на сервере.

```bash
# Внутри Docker (после rebuild с pyarrow):
python scripts/dry_run.py \
  --outlet "ТАСС" \
  --model google/gemini-2.5-flash \
  --profiles /app/data/inverse/bettor_profiles.parquet \
  --event-threads 5
```

**Проверить**: в evidence chain должно появиться:
```
Market: 0.55, Informed traders (12): 0.72, dispersion: 0.17
```

Если informed traders = 0 для всех рынков → нужны `--trades` с историей ставок по market_id. Без trades → `market_id not in inverse_trades` → нет enrichment. В этом случае нужно адаптировать dry_run для работы с Parquet trades из hf_cache.

### Задача 4: Dockerfile — добавить pyarrow

**Что сделать**: Одна строка в Dockerfile.

```dockerfile
RUN pip install pyarrow
```

Или в `pyproject.toml` добавить `pyarrow` в dependencies / optional extras `[inverse]`.

**Почему**: сейчас pyarrow ставится руками (`pip install --target ...`) после каждого docker compose build. Это ломается при rebuild.

### Задача 5: Merge feat/inverse-phase2 → main

**Что сделать**:
1. `git checkout main && git merge feat/inverse-phase2`
2. Или через PR: `gh pr create` → merge

**Ветка содержит**: Phase 2 (v0.9.0) + Phase 3 (v0.9.1) = ~12 коммитов, +3000 строк, 1226 тестов.

**ВАЖНО**: merge только ПОСЛЕ задач 1-4 (walk-forward validated, dry run passed, pyarrow в Dockerfile).

### Задача 6: Incremental BSS validation

**Что сделать**: После baseline BSS (задача 2) — запустить walk-forward варианты:

1. Baseline (fixed d=1.5, no gate, min_bets=20) → BSS_baseline
2. +adaptive extremizing only → BSS_adaptive. Если BSS_adaptive < BSS_baseline → REVERT
3. +volume gate only → BSS_gate. Если BSS_gate < BSS_baseline → REVERT
4. +both → BSS_combined
5. +timing_score weighting (если реализовано) → BSS_timing

**Каждое изменение должно улучшать BSS индивидуально.** Иначе — revert.

Документировать в `tasks/inverse_phase4_results.md`.

### Задача 7: Серверный deploy с Phase 3 кодом

**Что сделать** (ПОСЛЕ merge в main):
```bash
ssh deploy@213.165.220.144
cd /home/deploy/apps/delphi-press
git pull origin main
docker compose build app
docker compose up -d
```

**Проверить**:
- `docker ps` — все 4 контейнера healthy
- `curl https://delphi.antopkin.ru/api/v1/health` — 200 OK
- Parquet load работает внутри Docker

---

## Принципы работы

### TDD (Red → Green → Refactor)
- Каждая фича начинается с failing test
- Минимальный код для green
- `uv run pytest tests/ -v` после каждого шага
- Ни один существующий тест не ломается

### Субагенты
- **Explore**: для исследования кодовой базы перед изменениями
- **Code reviewer**: для ревью перед merge
- **Research**: если нужен контекст по DuckDB SQL паттернам или walk-forward methodology

### Коммиты после каждого шага
```
git add ... && git commit -m "feat/fix/docs: ..."
```
Коммит после каждой завершённой задачи. Не батчить.

---

## Спеки и файлы

- **Полный план Phase 3 с исследованиями**: `tasks/inverse_phase3_plan.md` (§1-8)
- **Существующий DuckDB pipeline**: `scripts/duckdb_build_profiles.py`
- **Существующий eval**: `scripts/eval_informed_consensus.py`
- **Метрики**: `src/eval/metrics.py` (brier_decomposition, calibration_slope, ECE)
- **Profiler**: `src/inverse/profiler.py` (as_of, timing_score, resolutions_with_dates)
- **Signal**: `src/inverse/signal.py` (adaptive_extremize, market_volume, _compute_adaptive_d)
- **Loader**: `src/inverse/loader.py` (load_resolutions_with_dates, load_market_timestamps)
- **Schemas**: `src/inverse/schemas.py` (BettorProfile.timing_score)
- **Store**: `src/inverse/store.py` (Parquet + JSON)
- **Сервер**: `deploy@213.165.220.144`, данные в `/home/deploy/data/inverse/`
- **Docker**: `docker-compose.yml` в `/home/deploy/apps/delphi-press/`

---

## Критерии успеха

| Метрика | Порог | Что означает |
|---|---|---|
| BSS vs raw market | > 0.00 | Informed consensus не вредит |
| BSS vs raw market | > 0.02 | Informed consensus реально помогает |
| Calibration slope | 0.8 – 1.2 | Модель примерно калибрована |
| ECE | < 0.10 | Приемлемая калибровка |
| Tier stability | > 60% | INFORMED бетторы стабильны между фолдами |
| Dry run enrichment | > 0 informed traders | Pipeline интегрирован |
| Docker healthy | 4/4 containers | Production deploy successful |

**Если BSS ≤ 0**: это валидный научный результат. Документировать и переключиться на другие стратегии.
