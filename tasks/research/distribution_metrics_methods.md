# Distribution Metrics from Prediction Market Prices

*Research date: 2026-03-28*

## Summary

5 метрик для enrichment Polymarket/Metaculus сигналов:

### 1. Volatility
- **Logit-transform обязателен**: `σ = std(Δlogit(p))` — raw std некорректен для [0,1]
- Window: 7 дней (default), 14 (для медленных событий)
- Logit: `x = log(p / (1-p))`, returns: `Δx = logit(p_t) - logit(p_{t-1})`

### 2. Trend
- **EMA-delta** (fast): `EMA(3) - EMA(7)` в logit space. Positive = к YES.
- **LinRegress** (precise): slope + R². `scipy.stats.linregress` на logit(p).
- Не использовать Mann-Kendall — overkill для pipeline.

### 3. Spread → Uncertainty
- `spread = ask - bid`, normalized: `s_norm = spread / mid`
- Sigmoid mapping: `U = 1 / (1 + exp(-40 * (s_norm - 0.05)))`
  - s_norm=0.02 → U≈0.12 (liquid), s_norm=0.05 → U=0.50, s_norm=0.15 → U≈0.98

### 4. Liquidity-weighted probability
- `weight = log10(1 + volume) / log10(1 + ref_volume)` (ref=1M USD)
- `lw_prob = weight * p + (1 - weight) * 0.5`
- Low volume → shrink к 0.5

### 5. Confidence interval
- Polymarket: empirical p10/p90 из price history (min 14 obs)
- Metaculus: q1/q3 напрямую (уже в API)
- Bootstrap НЕ используем при N < 30

## Реализация
Готовый модуль: `src/data_sources/distribution_metrics.py`
- `compute_market_metrics(prices, volume_usd, bid, ask)` → `MarketMetrics`
- Зависимости: numpy, pandas, scipy (все в проекте)
- ~250 строк кода с полной документацией

## Ключевые параметры
| Parameter | Default | Rationale |
|---|---|---|
| window | 7 | 1 week, min power for trend detection |
| reference_volume | 1,000,000 | ~75th percentile Polymarket markets |
| span_short/long | 3/7 | EMA fast/slow |
| ci_min_obs | 14 | 2 weeks daily data |
| spread_knee | 0.05 | 5% normalized spread = 0.50 uncertainty |
