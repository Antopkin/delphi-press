"""Evaluation module for retrospective prediction testing.

Pipeline stage: Evaluation (post-prediction).
Spec: docs-site/docs/evaluation/metrics.md
Contract: PredictionResponse -> EvalResult (via ground truth comparison).
"""

from src.eval.correlation import (
    collect_news_in_window,
    compute_granger_causality,
    compute_spearman_correlation,
    detect_sharp_movements,
)
from src.eval.ground_truth import fetch_headlines_from_wayback
from src.eval.metrics import brier_score, composite_score, log_score, market_brier_comparison
from src.eval.schemas import (
    BrierComparison,
    CorrelationResult,
    PriceMovement,
    ResolvedMarket,
)

__all__ = [
    "BrierComparison",
    "CorrelationResult",
    "PriceMovement",
    "ResolvedMarket",
    "brier_score",
    "collect_news_in_window",
    "composite_score",
    "compute_granger_causality",
    "compute_spearman_correlation",
    "detect_sharp_movements",
    "fetch_headlines_from_wayback",
    "log_score",
    "market_brier_comparison",
]
