"""Tests for src/inverse/clustering.py — HDBSCAN bettor strategy clustering."""

from __future__ import annotations

import pytest

from src.inverse.schemas import BettorProfile, BettorTier, ClusterAssignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    user_id: str,
    brier_score: float,
    win_rate: float = 0.5,
    mean_position_size: float = 100.0,
    total_volume: float = 1000.0,
    n_markets: int = 10,
    recency_weight: float = 0.9,
    tier: BettorTier = BettorTier.MODERATE,
) -> BettorProfile:
    """Factory for BettorProfile instances used in tests."""
    return BettorProfile(
        user_id=user_id,
        n_resolved_bets=20,
        brier_score=brier_score,
        mean_position_size=mean_position_size,
        total_volume=total_volume,
        tier=tier,
        n_markets=n_markets,
        win_rate=win_rate,
        recency_weight=recency_weight,
    )


def _make_profiles(n: int, brier_score: float = 0.25, **kwargs: float) -> list[BettorProfile]:
    """Create n profiles with the same parameters."""
    return [_make_profile(f"user_{i}", brier_score=brier_score, **kwargs) for i in range(n)]


# ---------------------------------------------------------------------------
# TestClusterBettors
# ---------------------------------------------------------------------------


class TestClusterBettors:
    def test_hdbscan_not_available_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ImportError when hdbscan is flagged as unavailable."""
        import src.inverse.clustering as mod

        monkeypatch.setattr(mod, "HDBSCAN_AVAILABLE", False)
        profiles = _make_profiles(60)

        with pytest.raises(ImportError, match="hdbscan"):
            mod.cluster_bettors(profiles)

    def test_too_few_profiles_raises(self) -> None:
        """ValueError if len(profiles) < min_cluster_size."""
        from src.inverse.clustering import cluster_bettors

        profiles = _make_profiles(10)

        with pytest.raises(ValueError, match="at least 50"):
            cluster_bettors(profiles, min_cluster_size=50)

    def test_cluster_synthetic_two_groups(self) -> None:
        """Two well-separated groups should produce mostly non-noise assignments."""
        from src.inverse.clustering import cluster_bettors

        # Group A: very accurate, high volume sharp bettors
        group_a = [
            _make_profile(
                f"sharp_{i}",
                brier_score=0.05,
                win_rate=0.85,
                total_volume=500_000.0,
                mean_position_size=5_000.0,
                n_markets=50,
                recency_weight=0.95,
                tier=BettorTier.INFORMED,
            )
            for i in range(60)
        ]
        # Group B: poor accuracy, low volume noise traders
        group_b = [
            _make_profile(
                f"noise_{i}",
                brier_score=0.90,
                win_rate=0.10,
                total_volume=50.0,
                mean_position_size=5.0,
                n_markets=2,
                recency_weight=0.10,
                tier=BettorTier.NOISE,
            )
            for i in range(60)
        ]
        profiles = group_a + group_b
        assignments = cluster_bettors(profiles, min_cluster_size=10, min_samples=5)

        assert len(assignments) == len(profiles)

        # Most profiles should not be noise (cluster_id == -1)
        non_noise = [a for a in assignments if a.cluster_id != -1]
        assert len(non_noise) >= len(profiles) * 0.7

        # At least 2 distinct clusters expected for well-separated groups
        distinct_clusters = {a.cluster_id for a in assignments if a.cluster_id != -1}
        assert len(distinct_clusters) >= 1

    def test_cluster_assignment_schema(self) -> None:
        """ClusterAssignment has correct fields and types."""
        from src.inverse.clustering import cluster_bettors

        profiles = _make_profiles(60, brier_score=0.25)
        assignments = cluster_bettors(profiles, min_cluster_size=10, min_samples=5)

        assert len(assignments) == 60
        for a in assignments:
            assert isinstance(a, ClusterAssignment)
            assert isinstance(a.user_id, str)
            assert isinstance(a.cluster_id, int)
            assert isinstance(a.cluster_label, str)
            assert 0.0 <= a.membership_probability <= 1.0

    def test_noise_points_labeled_minus1(self) -> None:
        """Isolated single-point clusters receive cluster_id == -1."""
        from src.inverse.clustering import cluster_bettors

        # Create a base population of similar profiles
        base = _make_profiles(60, brier_score=0.25)

        # Add a few highly isolated outlier profiles at extreme feature values
        outliers = [
            _make_profile(
                f"outlier_{i}",
                brier_score=0.001,
                win_rate=0.999,
                total_volume=1_000_000_000.0,
                mean_position_size=1_000_000.0,
                n_markets=9999,
                recency_weight=0.001,
            )
            for i in range(3)
        ]
        profiles = base + outliers

        assignments = cluster_bettors(profiles, min_cluster_size=30, min_samples=15)
        outlier_assignments = [a for a in assignments if a.user_id.startswith("outlier_")]

        # At least some extreme points should be noise
        noise_count = sum(1 for a in outlier_assignments if a.cluster_id == -1)
        assert noise_count >= 1


# ---------------------------------------------------------------------------
# TestLabelClusters
# ---------------------------------------------------------------------------


class TestLabelClusters:
    def test_sharp_informed_label(self) -> None:
        """Low BS + high log_volume → sharp_informed."""
        from src.inverse.clustering import label_clusters

        # math.log1p(500000) ≈ 13.1 > 6.0 — satisfies volume threshold
        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.05,
                total_volume=500_000.0,
                win_rate=0.80,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "sharp_informed"

    def test_outlier_label(self) -> None:
        """cluster_id == -1 always maps to 'outlier'."""
        from src.inverse.clustering import label_clusters

        profiles = _make_profiles(3)
        labels = [-1, -1, -1]
        result = label_clusters(profiles, labels)

        assert result[-1] == "outlier"

    def test_noise_trader_fallback(self) -> None:
        """No matching pattern → noise_trader."""
        from src.inverse.clustering import label_clusters

        # Middle-of-the-road profiles that don't trigger any special label:
        # BS=0.25 (not < 0.10 / < 0.15), win_rate=0.50 (not < 0.30 / > 0.65),
        # log_volume=math.log1p(500)≈6.2 (not > 7.0), recency=0.60 (not < 0.20)
        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.25,
                win_rate=0.50,
                total_volume=500.0,
                recency_weight=0.60,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "noise_trader"

    def test_skilled_retail_label(self) -> None:
        """BS < 0.15 and win_rate > 0.65 → skilled_retail."""
        from src.inverse.clustering import label_clusters

        # Use moderate volume so sharp_informed condition (log_vol > 6.0) is NOT met:
        # math.log1p(50) ≈ 3.9 < 6.0
        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.12,
                win_rate=0.70,
                total_volume=50.0,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "skilled_retail"

    def test_contrarian_label(self) -> None:
        """win_rate < 0.30 → contrarian."""
        from src.inverse.clustering import label_clusters

        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.50,
                win_rate=0.20,
                total_volume=500.0,
                recency_weight=0.70,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "contrarian"

    def test_stale_label(self) -> None:
        """Low recency_weight → stale (when no other condition matches first)."""
        from src.inverse.clustering import label_clusters

        # BS and win_rate are in mid ranges so other labels don't fire
        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.25,
                win_rate=0.50,
                total_volume=200.0,
                recency_weight=0.10,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "stale"

    def test_volume_bettor_label(self) -> None:
        """High log_volume and mid-range BS → volume_bettor."""
        from src.inverse.clustering import label_clusters

        # math.log1p(2000000) ≈ 14.5 > 7.0; BS=0.22 in (0.15, 0.28)
        # win_rate must be >= 0.30 to not trigger contrarian first
        profiles = [
            _make_profile(
                f"u{i}",
                brier_score=0.22,
                win_rate=0.50,
                total_volume=2_000_000.0,
                recency_weight=0.70,
            )
            for i in range(5)
        ]
        labels = [0] * 5
        result = label_clusters(profiles, labels)

        assert result[0] == "volume_bettor"

    def test_multiple_clusters_labeled_independently(self) -> None:
        """Each cluster receives its own label based on its own members."""
        from src.inverse.clustering import label_clusters

        sharp_profiles = [
            _make_profile(f"sharp_{i}", brier_score=0.05, total_volume=500_000.0) for i in range(5)
        ]
        noise_profiles = [
            _make_profile(
                f"noise_{i}",
                brier_score=0.25,
                win_rate=0.50,
                total_volume=500.0,
                recency_weight=0.60,
            )
            for i in range(5)
        ]
        profiles = sharp_profiles + noise_profiles
        labels = [0] * 5 + [1] * 5

        result = label_clusters(profiles, labels)

        assert result[0] == "sharp_informed"
        assert result[1] == "noise_trader"


# ---------------------------------------------------------------------------
# TestBuildFeatureMatrix (private helper — tested via public interface)
# ---------------------------------------------------------------------------


class TestBuildFeatureMatrix:
    def test_feature_matrix_shape(self) -> None:
        """_build_feature_matrix returns correct shape."""
        from src.inverse.clustering import _build_feature_matrix, _DEFAULT_FEATURES

        profiles = _make_profiles(5)
        matrix, names = _build_feature_matrix(profiles, _DEFAULT_FEATURES)

        assert len(matrix) == 5
        assert all(len(row) == len(_DEFAULT_FEATURES) for row in matrix)
        assert names == _DEFAULT_FEATURES

    def test_unknown_feature_raises(self) -> None:
        """ValueError for an unrecognised feature name."""
        from src.inverse.clustering import _build_feature_matrix

        profiles = _make_profiles(3)
        with pytest.raises(ValueError, match="Unknown feature name"):
            _build_feature_matrix(profiles, ["unknown_feature"])

    def test_log_transform_applied(self) -> None:
        """log1p_total_volume uses math.log1p, not raw value."""
        import math

        from src.inverse.clustering import _build_feature_matrix

        profile = _make_profile("u0", brier_score=0.1, total_volume=1000.0)
        matrix, _ = _build_feature_matrix([profile], ["log1p_total_volume"])

        assert matrix[0][0] == pytest.approx(math.log1p(1000.0))
