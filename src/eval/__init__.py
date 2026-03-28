"""Evaluation module for retrospective prediction testing.

Pipeline stage: Evaluation (post-prediction).
Spec: tasks/research/retrospective_testing.md
Contract: PredictionResponse -> EvalResult (via ground truth comparison).
"""

from src.eval.ground_truth import fetch_headlines_from_wayback
from src.eval.metrics import brier_score, composite_score, log_score

__all__ = [
    "brier_score",
    "composite_score",
    "fetch_headlines_from_wayback",
    "log_score",
]
