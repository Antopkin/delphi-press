"""Parametric bettor modeling — recover Exp(λ) / Weibull(λ,k) from positions.

Pipeline stage: Offline analysis (extends bettor profiling).
Spec: docs-site/docs/methodology/inverse-phases.md §2.

Contract:
    Input: per-user positions + market horizons.
    Output: dict[user_id → ParametricResult].

Mathematical model:
    Bettor believes event time T ~ Exp(λ): P(T ≤ H) = 1 - exp(-λH).
    Observed: volume-weighted position ≈ P(T ≤ H).
    Inverse: λ = -log(1 - position) / H.

    Weibull extension: P(T ≤ H) = 1 - exp(-(λH)^k).
    Requires scipy.optimize for MLE of (λ, k).

No published work applies Weibull/Exp recovery to prediction market bets
(Manski 2006, Satopää 2014 confirm theoretical gap). This is novel.
"""

from __future__ import annotations

import logging
import math
from typing import Literal

import numpy as np
from scipy import optimize

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    ExponentialFit,
    ParametricResult,
    TradeRecord,
    WeibullFit,
)

logger = logging.getLogger(__name__)

__all__ = [
    "build_parametric_profiles",
    "fit_exponential",
    "fit_weibull",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum observations for exponential fit.
MIN_OBS_EXPONENTIAL = 5

#: Minimum observations for Weibull fit.
MIN_OBS_WEIBULL = 20

#: Clamp positions to avoid log(0) or log(inf).
_POS_CLAMP_LOW = 1e-7
_POS_CLAMP_HIGH = 1 - 1e-7

#: L-BFGS-B bounds for lambda and k.
_LAMBDA_BOUNDS = (1e-6, 100.0)
_K_BOUNDS = (0.1, 10.0)

#: AIC difference threshold (Burnham & Anderson 2002): delta > 2 = substantial.
DELTA_AIC_THRESHOLD = 2.0


# ---------------------------------------------------------------------------
# Exponential fit (closed-form MLE)
# ---------------------------------------------------------------------------


def fit_exponential(
    positions: list[float],
    horizons: list[float],
    *,
    user_id: str = "unknown",
    prior_lambda: float | None = None,
    prior_strength: int = 0,
) -> ExponentialFit | None:
    """Fit Exp(λ) via closed-form MLE: λ = mean(-log(1-p) / H).

    For n < 30, optional Bayesian shrinkage with Gamma prior:
        posterior_λ = (n_obs + prior_strength) / (Σ H_i + prior_strength/prior_lambda)

    Args:
        positions: Observed positions (volume-weighted YES probability), one per market.
        horizons: Market horizon in days, same length as positions.
        user_id: Trader ID for the result object.
        prior_lambda: Prior mean λ for Bayesian shrinkage. None = MLE only.
        prior_strength: Strength of the prior (pseudo-observations).

    Returns:
        ExponentialFit or None if insufficient valid observations.
    """
    if len(positions) != len(horizons):
        return None

    # Filter valid observations
    lambdas: list[float] = []
    for p, h in zip(positions, horizons):
        if h <= 0:
            continue
        p_clamped = max(_POS_CLAMP_LOW, min(_POS_CLAMP_HIGH, p))
        lam = -math.log(1 - p_clamped) / h
        if math.isfinite(lam) and lam > 0:
            lambdas.append(lam)

    n = len(lambdas)
    if n < MIN_OBS_EXPONENTIAL:
        return None

    # MLE: λ̂ = mean of per-market lambdas
    lambda_mle = sum(lambdas) / n

    # Optional Bayesian shrinkage for small n
    if prior_lambda is not None and prior_strength > 0 and n < 30:
        lambda_hat = (n * lambda_mle + prior_strength * prior_lambda) / (n + prior_strength)
    else:
        lambda_hat = lambda_mle

    # Log-likelihood: LL = Σ log(P(observed | λ, H))
    # For Exp: P(pos | λ, H) ~ pos^(λH-1) * (1-pos)  (beta-like, approximation)
    # Simplified: use squared error as proxy for LL
    log_lik = _exp_log_likelihood(positions, horizons, lambda_hat)

    # 95% CI via Fisher information: SE(λ) ≈ λ / sqrt(n)
    se = lambda_hat / math.sqrt(n) if n > 0 else lambda_hat
    ci_lower = max(1e-7, lambda_hat - 1.96 * se)
    ci_upper = lambda_hat + 1.96 * se

    return ExponentialFit(
        user_id=user_id,
        lambda_val=round(lambda_hat, 8),
        n_observations=n,
        log_likelihood=round(log_lik, 4),
        ci_lower=round(ci_lower, 8),
        ci_upper=round(ci_upper, 8),
    )


# ---------------------------------------------------------------------------
# Weibull fit (scipy L-BFGS-B)
# ---------------------------------------------------------------------------


def fit_weibull(
    positions: list[float],
    horizons: list[float],
    *,
    user_id: str = "unknown",
    initial_lambda: float | None = None,
) -> WeibullFit | None:
    """Fit Weibull(λ, k) via MLE using scipy L-BFGS-B.

    Model: P(T ≤ H) = 1 - exp(-(λH)^k).
    Initialize at (λ_exp_mle, k=1.0) for convergence stability.

    Args:
        positions: Observed positions, one per market.
        horizons: Market horizon in days.
        user_id: Trader ID.
        initial_lambda: Starting λ value. If None, uses Exp MLE.

    Returns:
        WeibullFit or None if optimizer fails or insufficient data.
    """
    if len(positions) != len(horizons):
        return None

    # Filter valid observations
    valid = []
    for p, h in zip(positions, horizons):
        if h > 0:
            p_clamped = max(_POS_CLAMP_LOW, min(_POS_CLAMP_HIGH, p))
            valid.append((p_clamped, h))

    n = len(valid)
    if n < MIN_OBS_WEIBULL:
        return None

    pos_arr = np.array([v[0] for v in valid])
    hor_arr = np.array([v[1] for v in valid])

    # Initial guess
    if initial_lambda is None:
        # Use Exp MLE
        lam_init = float(np.mean(-np.log(1 - pos_arr) / hor_arr))
        lam_init = max(_LAMBDA_BOUNDS[0], min(_LAMBDA_BOUNDS[1], lam_init))
    else:
        lam_init = initial_lambda

    x0 = np.array([lam_init, 1.0])

    def neg_log_lik(params: np.ndarray) -> float:
        lam, k = params
        lh = lam * hor_arr
        predicted = 1.0 - np.exp(-(lh**k))
        # Gaussian likelihood approximation: -LL ∝ Σ(p - predicted)^2
        residuals = pos_arr - predicted
        return float(0.5 * np.sum(residuals**2))

    result = optimize.minimize(
        neg_log_lik,
        x0,
        method="L-BFGS-B",
        bounds=[_LAMBDA_BOUNDS, _K_BOUNDS],
        options={"ftol": 1e-12, "gtol": 1e-8, "maxiter": 500},
    )

    # Accept result if converged OR if residual is negligible (perfect/near-perfect fit)
    if not result.success and result.fun > 1e-8:
        logger.debug("Weibull fit failed for %s: %s", user_id, result.message)
        return None

    lam_opt, k_opt = result.x
    log_lik = -result.fun  # negate because we minimized -LL

    # AIC and BIC
    k_params = 2  # lambda and k
    aic = 2 * k_params - 2 * log_lik
    bic = k_params * math.log(n) - 2 * log_lik

    return WeibullFit(
        user_id=user_id,
        lambda_val=round(float(lam_opt), 8),
        shape_k=round(float(k_opt), 6),
        n_observations=n,
        log_likelihood=round(log_lik, 4),
        aic=round(aic, 4),
        bic=round(bic, 4),
    )


# ---------------------------------------------------------------------------
# Batch profile builder
# ---------------------------------------------------------------------------


def build_parametric_profiles(
    trades: list[TradeRecord],
    resolutions: dict[str, bool],
    horizons: dict[str, float],
    profiles: dict[str, BettorProfile],
    *,
    min_markets: int = MIN_OBS_EXPONENTIAL,
    fit_weibull_model: bool = True,
    prior_lambda: float | None = None,
) -> dict[str, ParametricResult]:
    """Build parametric estimates for profiled bettors.

    Only fits bettors in INFORMED tier with sufficient resolved markets.

    Args:
        trades: All trade records.
        resolutions: market_id → resolved_yes.
        horizons: market_id → horizon_days.
        profiles: Pre-built profiles (user_id → BettorProfile).
        min_markets: Minimum resolved markets with known horizons.
        fit_weibull_model: Also fit Weibull (requires n >= 20).
        prior_lambda: Bayesian prior for Exp fit (None = pure MLE).

    Returns:
        Dict user_id → ParametricResult.
    """
    from collections import defaultdict

    from src.inverse.profiler import aggregate_position

    # Group trades by user → market
    user_market_trades: dict[str, dict[str, list[TradeRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for t in trades:
        user_market_trades[t.user_id][t.market_id].append(t)

    results: dict[str, ParametricResult] = {}

    for user_id, profile in profiles.items():
        if profile.tier != BettorTier.INFORMED:
            continue

        # Collect (position, horizon) pairs for resolved markets
        positions: list[float] = []
        market_horizons: list[float] = []

        user_markets = user_market_trades.get(user_id, {})
        for market_id, mtrades in user_markets.items():
            if market_id not in resolutions or market_id not in horizons:
                continue
            pos, _ = aggregate_position(mtrades)
            positions.append(pos)
            market_horizons.append(horizons[market_id])

        if len(positions) < min_markets:
            continue

        # Fit Exp(λ)
        exp_fit = fit_exponential(
            positions,
            market_horizons,
            user_id=user_id,
            prior_lambda=prior_lambda,
        )
        if exp_fit is None:
            continue

        # Optionally fit Weibull(λ, k)
        wb_fit = None
        if fit_weibull_model and len(positions) >= MIN_OBS_WEIBULL:
            wb_fit = fit_weibull(
                positions,
                market_horizons,
                user_id=user_id,
                initial_lambda=exp_fit.lambda_val,
            )

        # Model selection by AIC
        preferred: Literal["exponential", "weibull"] = "exponential"
        delta_aic = 0.0
        if wb_fit is not None:
            # AIC for Exp: 2*1 - 2*LL
            aic_exp = 2 - 2 * exp_fit.log_likelihood
            delta_aic = aic_exp - wb_fit.aic
            if delta_aic > DELTA_AIC_THRESHOLD:
                preferred = "weibull"

        results[user_id] = ParametricResult(
            user_id=user_id,
            preferred_model=preferred,
            exp_fit=exp_fit,
            weibull_fit=wb_fit,
            delta_aic=round(delta_aic, 4),
        )

    logger.info(
        "Built %d parametric profiles (%d with Weibull)",
        len(results),
        sum(1 for r in results.values() if r.weibull_fit is not None),
    )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _exp_log_likelihood(
    positions: list[float],
    horizons: list[float],
    lambda_val: float,
) -> float:
    """Approximate log-likelihood for Exp(λ) model.

    Uses Gaussian error model: -LL ∝ Σ(p_obs - p_pred)^2.
    """
    ll = 0.0
    n = 0
    for p, h in zip(positions, horizons):
        if h <= 0:
            continue
        p_clamped = max(_POS_CLAMP_LOW, min(_POS_CLAMP_HIGH, p))
        predicted = 1.0 - math.exp(-lambda_val * h)
        ll -= 0.5 * (p_clamped - predicted) ** 2
        n += 1
    return ll
