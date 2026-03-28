"""News-market correlation analysis.

Pipeline stage: Evaluation (post-prediction).
Spec: tasks/research/polymarket_inverse_problem.md §5 step 4.
Contract: resolved markets + news signals -> CorrelationResult.
"""

from __future__ import annotations

import logging

from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


def detect_sharp_movements(
    prices: list[dict],
    *,
    threshold: float = 0.10,
    min_interval_hours: int = 4,
) -> list[dict]:
    """Detect sharp price movements (|delta_p| >= threshold) in a price series.

    Args:
        prices: List of {"t": unix_timestamp, "p": price_float} dicts.
        threshold: Minimum absolute price change to qualify.
        min_interval_hours: Minimum hours between detected movements (dedup).

    Returns:
        List of dicts: {timestamp, delta_p, price_before, price_after}.
    """
    if len(prices) < 2:
        return []

    min_interval_sec = min_interval_hours * 3600
    movements: list[dict] = []
    last_detected_ts = -float("inf")

    for i in range(1, len(prices)):
        try:
            p_before = float(prices[i - 1]["p"])
            p_after = float(prices[i]["p"])
            ts = int(prices[i]["t"])
        except (KeyError, ValueError, TypeError):
            continue

        delta = p_after - p_before
        if abs(delta) >= threshold and (ts - last_detected_ts) >= min_interval_sec:
            movements.append(
                {
                    "timestamp": ts,
                    "delta_p": delta,
                    "price_before": p_before,
                    "price_after": p_after,
                }
            )
            last_detected_ts = ts

    return movements


def collect_news_in_window(
    signals: list[dict],
    movement_timestamp: int,
    *,
    window_hours: int = 24,
    market_categories: list[str] | None = None,
) -> dict:
    """Collect news signals in [-window_hours, 0] before a price movement.

    Args:
        signals: List of signal dicts with published_at, relevance_score, categories.
        movement_timestamp: Unix timestamp of the price movement.
        window_hours: Lookback window in hours.
        market_categories: Market categories for overlap scoring.

    Returns:
        Dict: {count, mean_relevance, category_overlap_score}.
    """
    window_sec = window_hours * 3600
    window_start = movement_timestamp - window_sec

    matching: list[dict] = []
    for sig in signals:
        pub_ts = sig.get("published_at", 0)
        if isinstance(pub_ts, (int, float)) and window_start <= pub_ts <= movement_timestamp:
            matching.append(sig)

    if not matching:
        return {"count": 0, "mean_relevance": 0.0, "category_overlap_score": 0.0}

    mean_rel = sum(s.get("relevance_score", 0.0) for s in matching) / len(matching)

    # Category overlap: Jaccard of union of signal categories vs market categories
    overlap = 0.0
    if market_categories:
        market_cats = {c.lower() for c in market_categories}
        all_signal_cats: set[str] = set()
        for s in matching:
            all_signal_cats.update(c.lower() for c in s.get("categories", []))
        if all_signal_cats and market_cats:
            overlap = len(all_signal_cats & market_cats) / len(all_signal_cats | market_cats)

    return {
        "count": len(matching),
        "mean_relevance": mean_rel,
        "category_overlap_score": overlap,
    }


def compute_spearman_correlation(
    movements: list[tuple[float, int]],
) -> tuple[float | None, float | None]:
    """Spearman rho between |delta_p| and news_count.

    Args:
        movements: List of (|delta_p|, news_count) tuples.

    Returns:
        (rho, p_value) or (None, None) if insufficient data (< 5 points).
    """
    if len(movements) < 5:
        return None, None

    deltas = [m[0] for m in movements]
    counts = [m[1] for m in movements]

    import math

    result = spearmanr(deltas, counts)
    rho = float(result.statistic)
    pval = float(result.pvalue)
    if math.isnan(rho):
        return None, None
    return rho, pval


def compute_granger_causality(
    daily_news_counts: list[int],
    daily_price_changes: list[float],
    *,
    max_lag: int = 7,
) -> tuple[float | None, float | None, int | None]:
    """Granger causality test: does news volume Granger-cause price changes?

    Uses statsmodels.tsa.stattools.grangercausalitytests.
    Returns (None, None, None) if statsmodels is not installed or data insufficient.

    Args:
        daily_news_counts: Daily news signal counts.
        daily_price_changes: Daily price changes (first differences).
        max_lag: Maximum lag in days to test.

    Returns:
        (f_stat, p_value, best_lag) for the most significant lag,
        or (None, None, None).
    """
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        logger.warning("statsmodels not installed; skipping Granger causality test")
        return None, None, None

    import numpy as np

    n = min(len(daily_news_counts), len(daily_price_changes))
    if n < max_lag + 3:
        return None, None, None

    data = np.column_stack(
        [
            daily_price_changes[:n],
            daily_news_counts[:n],
        ]
    ).astype(float)

    try:
        results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    except Exception:
        logger.warning("Granger causality test failed", exc_info=True)
        return None, None, None

    # Find lag with lowest p-value (ssr_ftest)
    best_lag = None
    best_p = 1.0
    best_f = 0.0

    for lag in range(1, max_lag + 1):
        if lag not in results:
            continue
        test_result = results[lag]
        f_stat = test_result[0]["ssr_ftest"][0]
        p_val = test_result[0]["ssr_ftest"][1]
        if p_val < best_p:
            best_p = p_val
            best_f = f_stat
            best_lag = lag

    if best_lag is None:
        return None, None, None

    return float(best_f), float(best_p), best_lag
