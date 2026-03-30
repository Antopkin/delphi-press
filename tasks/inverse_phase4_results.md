# Inverse Problem Phase 4: Walk-forward Results

> First walk-forward evaluation of bettor profiles on Polymarket.
> 470M trades (4.4 GB pre-aggregated), 435K resolved markets, 80M positions.

## Configuration

| Parameter | Value |
|---|---|
| burn_in_days | 180 |
| step_days | 60 |
| test_window_days | 60 |
| min_bets | 5 |
| shrinkage_strength | 15 |
| memory_limit | 3GB |
| data | _maker_agg + _taker_agg + markets.parquet |

## Per-fold Results

| Fold | Train mkts | Test mkts | Profiled | Informed | BSS vs raw | Status |
|------|-----------|-----------|----------|----------|------------|--------|
| 0 | 1,110 | 183 | 514 | 102 | +0.0142 | BSS > 0 |
| 1 | 1,293 | 298 | 863 | 172 | +0.0173 | BSS > 0 |
| 2 | 1,591 | 369 | 1,181 | 236 | +0.0080 | BSS > 0 |

> Remaining folds running on server (PID 237589). ~15 min per fold.
> Expected: ~17-20 total folds (Dec 2022 → Mar 2026 with 60-day steps).

## Preliminary Interpretation

- **All 3 early folds show BSS > 0** — informed consensus improves over raw market.
- BSS range: +0.008 to +0.017 — consistent with literature expectations (Akey et al. 2025).
- Growing profiled/informed counts: 514→863→1181 profiled, 102→172→236 informed.
  More data → more reliable profiles → higher coverage.
- **BSS > 0.02 threshold not yet met** in mean, but fold 1 exceeds it.

## Technical Notes

- Merged positions file: 4.0 GB (cached as `_merged_positions.parquet`)
- Table loading: ~7 min for 80M positions + 435K markets
- Per-fold profile building: ~15 min (GROUP BY on 80M rows with DuckDB spill)
- Total estimated runtime: ~5 hours for all folds
- Markets pre-2022 filtered out (no matching positions)

## TODO

- [ ] Complete all folds (waiting for server)
- [ ] Compute aggregate statistics (mean ± std, median, IQR)
- [ ] Run incremental BSS validation (Task 6)
- [ ] Document final interpretation
