"""Distribution metrics for prediction market price histories.

Stage 1 data enrichment — pure math, zero I/O.
Spec: tasks/research/distribution_metrics_methods.md

Contract:
    Input: price history (list[float] in [0,1]), volume, bid/ask.
    Output: frozen MarketMetrics model with volatility, trend, spread,
            liquidity-weighted probability, confidence intervals.
"""

from __future__ import annotations

import math
import statistics
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPS = 1e-6  # clamp for logit to avoid log(0)
_SPREAD_KNEE = 0.05  # normalized spread inflection point
_SPREAD_K = 40  # sigmoid steepness


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class MarketMetrics(BaseModel):
    """Frozen distribution metrics computed from market price history."""

    model_config = ConfigDict(frozen=True)

    volatility_7d: float = Field(description="Std of logit-returns over window")
    trend_7d: float = Field(description="EMA(short) - EMA(long) in logit space")
    spread: float = Field(description="Normalized bid-ask spread")
    uncertainty: float = Field(description="Sigmoid uncertainty score [0,1]")
    lw_probability: float = Field(ge=0.0, le=1.0, description="Liquidity-weighted probability")
    ci_low: float | None = Field(description="Empirical p10 (None if < min_obs)")
    ci_high: float | None = Field(description="Empirical p90 (None if < min_obs)")
    distribution_reliable: bool = Field(description="True if enough observations for CI")


# ---------------------------------------------------------------------------
# Helper: logit transform
# ---------------------------------------------------------------------------


def _logit(p: float, eps: float = _EPS) -> float:
    """Logit transform with epsilon clamp: log(p / (1-p))."""
    p = max(eps, min(1.0 - eps, p))
    return math.log(p / (1.0 - p))


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------


def compute_volatility(prices: list[float], window: int = 7) -> float:
    """Standard deviation of logit-returns over the last *window* prices.

    Returns 0.0 if fewer than 2 prices.
    """
    if len(prices) < 2:
        return 0.0

    tail = prices[-window:] if len(prices) > window else prices
    logit_returns = [_logit(tail[i]) - _logit(tail[i - 1]) for i in range(1, len(tail))]
    if len(logit_returns) < 2:
        return abs(logit_returns[0]) if logit_returns else 0.0
    return statistics.stdev(logit_returns)


def _ema(values: list[float], span: int) -> list[float]:
    """Exponential moving average (manual loop, no pandas)."""
    alpha = 2.0 / (span + 1)
    result: list[float] = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1.0 - alpha) * result[-1])
    return result


def compute_trend(prices: list[float], span_short: int = 3, span_long: int = 7) -> float:
    """EMA(short) - EMA(long) in logit space. Positive = toward YES."""
    if len(prices) < 2:
        return 0.0

    logit_prices = [_logit(p) for p in prices]
    ema_short = _ema(logit_prices, span_short)
    ema_long = _ema(logit_prices, span_long)
    return ema_short[-1] - ema_long[-1]


def compute_spread_metrics(bid: float, ask: float) -> tuple[float, float]:
    """Normalized spread and sigmoid uncertainty score.

    Returns (normalized_spread, uncertainty). Both 0.0 if bid >= ask.
    """
    if bid >= ask or ask <= 0:
        return 0.0, 0.0

    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 0.0, 0.0

    s_norm = (ask - bid) / mid
    uncertainty = 1.0 / (1.0 + math.exp(-_SPREAD_K * (s_norm - _SPREAD_KNEE)))
    return round(s_norm, 6), round(uncertainty, 6)


def compute_lw_probability(prob: float, volume: float, ref_volume: float = 1_000_000) -> float:
    """Liquidity-weighted probability — shrink toward 0.5 for low volume."""
    if volume <= 0:
        return 0.5
    weight = math.log10(1.0 + volume) / math.log10(1.0 + ref_volume)
    weight = min(weight, 1.0)  # cap at 1.0
    return weight * prob + (1.0 - weight) * 0.5


def compute_confidence_interval(
    prices: list[float], min_obs: int = 14
) -> tuple[float | None, float | None]:
    """Empirical p10/p90 from price history.

    Returns (None, None) if fewer than *min_obs* observations.
    """
    if len(prices) < min_obs:
        return None, None

    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    idx_10 = max(0, int(n * 0.10))
    idx_90 = min(n - 1, int(n * 0.90))
    return sorted_prices[idx_10], sorted_prices[idx_90]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def compute_market_metrics(
    prices: list[float],
    volume: float,
    bid: float,
    ask: float,
    probability: float,
) -> MarketMetrics:
    """Compute all distribution metrics from market data.

    Args:
        prices: chronological price history (floats in [0, 1]).
        volume: total trading volume in USD.
        bid: best bid price.
        ask: best ask price.
        probability: current YES probability.
    """
    volatility = compute_volatility(prices)
    trend = compute_trend(prices)
    spread, uncertainty = compute_spread_metrics(bid, ask)
    lw_prob = compute_lw_probability(probability, volume)
    ci_low, ci_high = compute_confidence_interval(prices)
    reliable = ci_low is not None

    return MarketMetrics(
        volatility_7d=round(volatility, 6),
        trend_7d=round(trend, 6),
        spread=spread,
        uncertainty=uncertainty,
        lw_probability=round(lw_prob, 6),
        ci_low=round(ci_low, 6) if ci_low is not None else None,
        ci_high=round(ci_high, 6) if ci_high is not None else None,
        distribution_reliable=reliable,
    )
