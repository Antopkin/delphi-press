"""Strategy clustering — discover natural bettor archetypes via HDBSCAN.

Pipeline stage: Offline analysis (extends bettor profiling).
Spec: docs-site/docs/methodology/inverse-phases.md §3.

Contract:
    Input: list[BettorProfile] (from profiler.py).
    Output: list[ClusterAssignment] + dict[int, str] (cluster labels).
"""

from __future__ import annotations

import logging
import math

from src.inverse.schemas import BettorProfile, ClusterAssignment

try:
    import hdbscan as _hdbscan_lib

    HDBSCAN_AVAILABLE = True
except ImportError:
    _hdbscan_lib = None  # type: ignore[assignment]
    HDBSCAN_AVAILABLE = False

__all__ = [
    "HDBSCAN_AVAILABLE",
    "cluster_bettors",
    "label_clusters",
]

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default feature set
# ---------------------------------------------------------------------------

_DEFAULT_FEATURES: list[str] = [
    "brier_score",
    "win_rate",
    "log1p_mean_position_size",
    "log1p_total_volume",
    "n_markets",
    "recency_weight",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cluster_bettors(
    profiles: list[BettorProfile],
    *,
    min_cluster_size: int = 50,
    min_samples: int = 10,
    features: list[str] | None = None,
) -> list[ClusterAssignment]:
    """HDBSCAN clustering on behavioral features.

    Features (default): brier_score, win_rate, log1p(mean_position_size),
    log1p(total_volume), n_markets, recency_weight.

    Normalization: StandardScaler after log-transform for right-skewed features.

    Args:
        profiles: List of bettor profiles to cluster.
        min_cluster_size: Minimum number of profiles to form a cluster.
        min_samples: HDBSCAN min_samples parameter (controls noise tolerance).
        features: Feature names to use. Defaults to the standard six features.

    Returns:
        List of ClusterAssignment, one per profile, in the same order.

    Raises:
        ImportError: If hdbscan is not installed.
        ValueError: If fewer than min_cluster_size profiles are provided.
    """
    if not HDBSCAN_AVAILABLE:
        raise ImportError("hdbscan is not installed. Install it with: pip install hdbscan")

    if len(profiles) < min_cluster_size:
        raise ValueError(
            f"Need at least {min_cluster_size} profiles to cluster "
            f"(got {len(profiles)}). Reduce min_cluster_size or provide more data."
        )

    import numpy as np
    from sklearn.preprocessing import StandardScaler

    feature_names = features if features is not None else _DEFAULT_FEATURES

    raw_matrix, used_features = _build_feature_matrix(profiles, feature_names)

    X = np.array(raw_matrix, dtype=np.float64)
    X = StandardScaler().fit_transform(X)

    clusterer = _hdbscan_lib.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )
    clusterer.fit(X)

    labels: list[int] = clusterer.labels_.tolist()

    # Soft membership probabilities (HDBSCAN stores these in probabilities_)
    probs: list[float] = clusterer.probabilities_.tolist()

    cluster_label_map = label_clusters(profiles, labels)

    assignments: list[ClusterAssignment] = []
    for profile, cluster_id, prob in zip(profiles, labels, probs):
        assignments.append(
            ClusterAssignment(
                user_id=profile.user_id,
                cluster_id=cluster_id,
                cluster_label=cluster_label_map.get(cluster_id, "noise_trader"),
                membership_probability=max(0.0, min(1.0, prob)),
            )
        )

    n_clusters = len({lbl for lbl in labels if lbl != -1})
    n_noise = labels.count(-1)
    _log.info(
        "HDBSCAN produced %d clusters, %d noise points from %d profiles",
        n_clusters,
        n_noise,
        len(profiles),
    )

    return assignments


def label_clusters(
    profiles: list[BettorProfile],
    labels: list[int],
) -> dict[int, str]:
    """Auto-label clusters by dominant behavioral feature.

    Labels:
    - sharp_informed: median BS < 0.10, median log_volume > 6.0
    - skilled_retail: median BS < 0.15, median win_rate > 0.65
    - volume_bettor: median log_volume > 7.0, 0.15 < median BS < 0.28
    - contrarian: median win_rate < 0.30
    - stale: median recency < 0.20
    - noise_trader: everything else
    - outlier: cluster_id == -1

    Args:
        profiles: Bettor profiles in the same order as labels.
        labels: Integer cluster labels returned by HDBSCAN.

    Returns:
        Mapping cluster_id → human-readable label string.
    """
    from statistics import median

    cluster_ids = sorted({lbl for lbl in labels if lbl != -1})

    result: dict[int, str] = {-1: "outlier"}

    for cid in cluster_ids:
        members = [p for p, lbl in zip(profiles, labels) if lbl == cid]
        if not members:
            result[cid] = "noise_trader"
            continue

        med_bs = median(p.brier_score for p in members)
        med_win = median(p.win_rate for p in members)
        med_log_vol = median(math.log1p(p.total_volume) for p in members)
        med_recency = median(p.recency_weight for p in members)

        if med_bs < 0.10 and med_log_vol > 6.0:
            result[cid] = "sharp_informed"
        elif med_bs < 0.15 and med_win > 0.65:
            result[cid] = "skilled_retail"
        elif med_log_vol > 7.0 and 0.15 < med_bs < 0.28:
            result[cid] = "volume_bettor"
        elif med_win < 0.30:
            result[cid] = "contrarian"
        elif med_recency < 0.20:
            result[cid] = "stale"
        else:
            result[cid] = "noise_trader"

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_feature_matrix(
    profiles: list[BettorProfile],
    feature_names: list[str],
) -> tuple[list[list[float]], list[str]]:
    """Extract and transform features from profiles into a 2D matrix.

    Supported feature names:
        - brier_score
        - win_rate
        - log1p_mean_position_size  (log1p transform applied)
        - log1p_total_volume        (log1p transform applied)
        - n_markets
        - recency_weight

    Args:
        profiles: Source bettor profiles.
        feature_names: Ordered list of feature names to extract.

    Returns:
        Tuple of (matrix, used_feature_names) where matrix is
        list[list[float]] with shape (n_profiles, n_features).
    """
    matrix: list[list[float]] = []

    for p in profiles:
        row: list[float] = []
        for fname in feature_names:
            if fname == "brier_score":
                row.append(p.brier_score)
            elif fname == "win_rate":
                row.append(p.win_rate)
            elif fname == "log1p_mean_position_size":
                row.append(math.log1p(p.mean_position_size))
            elif fname == "log1p_total_volume":
                row.append(math.log1p(p.total_volume))
            elif fname == "n_markets":
                row.append(float(p.n_markets))
            elif fname == "recency_weight":
                row.append(p.recency_weight)
            else:
                raise ValueError(f"Unknown feature name: {fname!r}")
        matrix.append(row)

    return matrix, list(feature_names)
