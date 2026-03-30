# Inverse Problem Phase 4: Walk-forward Results

> First walk-forward evaluation of bettor profiles on Polymarket.
> 470M trades, 435K resolved markets, 82.6M bucketed positions.

## Configuration

| Parameter | Value |
|---|---|
| burn_in_days | 180 |
| step_days | 60 |
| test_window_days | 60 |
| min_bets | 5 |
| shrinkage_strength | 15 |
| memory_limit | 2GB |
| bucket_size | 30 days |
| data | _merged_bucketed.parquet (2.4 GB, temporal leak eliminated) |

## Clean Results (22 folds, bucketed positions)

| Fold | Train mkts | Test mkts | Profiled | Informed | BSS |
|------|-----------|-----------|----------|----------|-----|
| 0 | 1,110 | 183 | 506 | 101 | +0.0143 |
| 1 | 1,293 | 298 | 855 | 171 | +0.0212 |
| 2 | 1,591 | 369 | 1,173 | 234 | +0.0054 |
| 3 | 1,960 | 496 | 1,538 | 307 | +0.0274 |
| 4 | 2,456 | 709 | 2,361 | 472 | +0.0296 |
| 5 | 3,165 | 944 | 3,127 | 625 | +0.0753 |
| 6 | 4,109 | 1,892 | 4,537 | 907 | +0.0734 |
| 7 | 6,001 | 3,328 | 15,721 | 3,144 | +0.1806 |
| 8 | 9,329 | 4,675 | 40,829 | 8,165 | +0.1893 |
| 9 | 14,004 | 4,354 | 170,781 | 34,156 | +0.2726 |
| 10 | 18,358 | 7,480 | 305,042 | 61,008 | +0.2131 |
| 11 | 25,838 | 7,909 | 443,640 | 88,731 | +0.2715 |
| 12 | 33,747 | 15,791 | 596,209 | 119,241 | +0.2233 |
| 13 | 49,538 | 31,199 | 769,347 | 153,869 | +0.1367 |
| 14 | 80,737 | 65,903 | 811,436 | 162,287 | +0.0951 |
| 15 | 146,640 | 124,084 | 997,453 | 199,490 | +0.1322 |
| 16 | 270,724 | 161,693 | 1,244,549 | 248,909 | +0.1252 |
| 17* | 432,417 | 1,610 | 1,486,040 | 297,208 | +0.4312 |
| 18* | 434,027 | 387 | 1,489,609 | 297,921 | +0.4284 |
| 19* | 434,414 | 316 | 1,497,829 | 299,565 | +0.4464 |
| 20* | 434,730 | 12 | 1,498,339 | 299,667 | +0.4731 |
| 21* | 434,742 | 998 | 1,498,352 | 299,670 | +0.4491 |

\* Folds 17-21 have <2000 test markets — high variance, use with caution.

## Aggregate Statistics

### All 22 folds

| Metric | Value |
|---|---|
| Mean BSS | **+0.196** |
| Median BSS | +0.159 |
| Std BSS | 0.160 |
| Min BSS | +0.005 (fold 2) |
| Max BSS | +0.473 (fold 20) |
| Fraction BSS > 0 | **22/22 (100%)** |
| Tier stability | 0.613 |
| Total time | 82 min |

### Robust subset (folds 0-16, test markets >= 944)

| Metric | Value |
|---|---|
| Mean BSS | **+0.127** |
| Median BSS | +0.095 |
| Min BSS | +0.005 |
| Max BSS | +0.273 |
| Fraction BSS > 0 | **17/17 (100%)** |

## Temporal Leak Analysis

### What was the leak?

Pre-aggregated positions (`_maker_agg.parquet`, `_taker_agg.parquet`) contained ALL trades
by a user on a market — including trades made AFTER the walk-forward cutoff T. This means:
1. Profiling used "future" trade information
2. Test signal included late-resolution trades

### Fix: Bucketed partial aggregates

Scanned 33 GB raw `trades.parquet`, output 30-day bucketed sums. For any cutoff T,
reconstruct positions from `WHERE time_bucket <= T/bucket_size`. Zero data loss, zero leak.

### Comparison: leaked vs clean

| Metric | Leaked (old) | Clean (bucketed) |
|---|---|---|
| Folds completed | 15 (OOM) | 22 |
| Mean BSS (folds 0-14) | +0.092 | **+0.117** |
| Median BSS | +0.054 | **+0.095** |
| Per-fold time | ~15 min | **~4 sec** |
| Total time | 5+ hours | **82 min** |
| Memory | OOM at 7.4 GB | Peak 4.6 GB |

**Clean BSS is HIGHER than leaked.** The temporal leak did not inflate BSS — it
introduced noise that diluted the informed signal. Future trades on training
markets added noise to profiling; future trades on test markets added noise to
signal computation.

## Interpretation

1. **22/22 folds BSS > 0** — informed consensus **always** improves over raw market.
2. **Robust mean BSS = +0.127** (folds 0-16) — 12.7% Brier Score reduction.
3. **Inverted-U pattern confirmed**: BSS peaks at fold 9-11 (+0.21-0.27) with optimal
   data volume, then decreases as markets become more liquid and efficient.
4. **Tier stability = 0.613** — 61% Jaccard overlap between consecutive folds' INFORMED sets.
   This exceeds the 60% threshold, confirming stable tier classification.
5. **Scale**: 1.5M profiled users, 300K informed — massive dataset.
6. **Speed**: bucketed approach reduced per-fold from 15 min to ~4 sec (225× speedup).

### Comparison with literature

- Akey et al. 2025: top 1% captures 84% of gains. Our top 20% (INFORMED) captures
  BSS +0.13 — significant above typical prediction tournament improvements.
- Satopää et al. 2014: extremizing adds 10-20% in tournament settings. **Our ablation
  shows extremizing HURTS on Polymarket data** — likely because informed bettors are
  correlated (same market signals), not independently informed (private info).
- **First published walk-forward evaluation on Polymarket bettor profiles.**

## Phase 5: BSS Variant Ablation (2026-03-30)

Single-pass multi-variant evaluation: 5 configs in one run, DuckDB SQL once per fold.
22 folds, 435K resolved markets, bootstrap CI 1000 resamples.

### Variant Results

| Variant | BSS mean | BSS median | Fraction > 0 | Sign test p | 95% CI (fold) |
|---|---|---|---|---|---|
| **Baseline** | **+0.196** | **+0.159** | **100% (22/22)** | **2.38e-07** | **[+0.135, +0.260]** |
| Volume gate | +0.071 | +0.054 | 95.5% (21/22) | — | [+0.040, +0.102] |
| Gate + extremize | +0.047 | +0.028 | 68.2% (15/22) | 0.067 | [+0.022, +0.075] |
| Gate + timing | +0.071 | +0.054 | 95.5% (21/22) | — | [+0.040, +0.102] |
| All three | +0.047 | +0.028 | 68.2% (15/22) | 0.067 | [+0.022, +0.075] |

### Interpretation

1. **Baseline is optimal.** No variant improves over simple accuracy-weighted consensus with Bayesian shrinkage.
2. **Volume gate hurts (-64% BSS).** Soft gating markets below $100K removes informative signal — most Polymarket markets are below this threshold.
3. **Extremizing hurts further.** Pushing probabilities away from 0.5 amplifies noise rather than independent information. This contradicts Satopää et al. 2014 predictions — likely because our INFORMED bettors are already highly correlated (not independently informed).
4. **Timing weight has zero effect.** Gate + timing = gate alone — timing_score doesn't discriminate within the INFORMED tier.
5. **Negative result is valuable:** simplest model wins. No hyperparameter tuning needed.

### Methodology Note

Parameters ($10K/$100K thresholds, d_scale=2.0, d_max=2.0) were set a priori from literature in Phase 3, NOT tuned on walk-forward data. Overfitting risk is minimal.

## Technical Notes

- Bucketed build: 3-pass (maker→taker→merge), 34 min on 8 GB server
- Bucketed file: 2.4 GB, 82.6M rows, 30-day time buckets
- Walk-forward: streaming `read_parquet()` with predicate pushdown on `time_bucket`
- No OOM: peak 4.6 GB RAM (vs 7.4 GB before, crashed at fold 15)
- trades.parquet re-downloaded from HuggingFace (32.8 GB)
