# News↔Market Correlation Report

Generated: 2026-03-28T23:10:37.936560+00:00

## Parameters

- Markets analyzed: 17
- Movement threshold: |Δp| >= 0.05
- News window: 24h before movement
- Min market volume: $50,000

## Summary

- Total sharp movements detected: 33
- Movements with news signals: 0 (0.0%)

## Spearman Rank Correlation

- Insufficient data (< 5 movements)



## Granger Causality

- Not computed (insufficient data or statsmodels not installed)

## Movement Details

| Market | Δp | News Count | Mean Relevance |
|--------|-----|------------|----------------|
| Counter-Strike: Acend vs Bebop (BO3) - CCT Europe Serie | -0.055 | 0 | 0.00 |
| Counter-Strike: Acend vs Bebop (BO3) - CCT Europe Serie | +0.190 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.160 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.050 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.075 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | +0.055 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | +0.060 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.060 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.055 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | +0.050 | 0 | 0.00 |
| Will the price of Bitcoin be above $72,000 on February  | -0.085 | 0 | 0.00 |
| Will Universitatea Craiova CS win on 2025-10-23? | +0.170 | 0 | 0.00 |
| Will Universitatea Craiova CS win on 2025-10-23? | -0.235 | 0 | 0.00 |
| Will Biden say "Old" during drop out speech? | +0.205 | 0 | 0.00 |
| Will Biden say "Old" during drop out speech? | -0.195 | 0 | 0.00 |
| Will Trump say “Sleazebag” by February 28? | +0.479 | 0 | 0.00 |
| Trail Blazers vs. Kings: O/U 239.5 | -0.095 | 0 | 0.00 |
| Will the price of Ethereum be above $4,475 on September | -0.250 | 0 | 0.00 |
| Will the price of Ethereum be above $4,475 on September | +0.467 | 0 | 0.00 |
| Will Elon Musk post 90-114 tweets from February 14 to F | +0.080 | 0 | 0.00 |
| Will Elon Musk post 90-114 tweets from February 14 to F | +0.050 | 0 | 0.00 |
| Will Elon Musk post 90-114 tweets from February 14 to F | -0.105 | 0 | 0.00 |
| Will Elon Musk post 90-114 tweets from February 14 to F | -0.055 | 0 | 0.00 |
| Will Elon Musk post 90-114 tweets from February 14 to F | -0.066 | 0 | 0.00 |
| Will the highest temperature in London be 18°C on Febru | +0.200 | 0 | 0.00 |
| Will the highest temperature in London be 18°C on Febru | -0.090 | 0 | 0.00 |
| Will the highest temperature in London be 18°C on Febru | +0.160 | 0 | 0.00 |
| Will the highest temperature in London be 18°C on Febru | -0.474 | 0 | 0.00 |
| Will Trump say "Two Weeks" first during Saudi PM events | -0.235 | 0 | 0.00 |
| Will Trump say "Two Weeks" first during Saudi PM events | +0.060 | 0 | 0.00 |
| Will Trump say "Two Weeks" first during Saudi PM events | +0.830 | 0 | 0.00 |
| Will the highest temperature in London be between 66-67 | -0.085 | 0 | 0.00 |
| Will the highest temperature in London be between 66-67 | +0.055 | 0 | 0.00 |

## Methodology

1. Fetch resolved markets from Polymarket Gamma API (active=false, closed=true)
2. Retrieve 30-day price history via CLOB API (chunked startTs/endTs)
3. Detect sharp movements: consecutive price points with |Δp| >= threshold
4. For each movement, search GDELT for news in [-window, 0] before the movement
5. Compute Spearman rank correlation between |Δp| and news count
6. Compute Granger causality test (daily aggregates, 1-3 day lags)

## References

- Snowberg, Wolfers, Zitzewitz (2013) — How Prediction Markets Can Save Event Studies
- Polymarket accuracy: polymarket.com/accuracy (aggregate BS ≈ 0.084)
- Event study windows: [-24h, +24h] standard, [-2h, +2h] for breaking news
