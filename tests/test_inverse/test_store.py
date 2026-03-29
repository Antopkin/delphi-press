"""Tests for src/inverse/store.py — profile persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.inverse.schemas import BettorProfile, BettorTier, ProfileSummary
from src.inverse.store import load_profiles, save_profiles


@pytest.fixture()
def sample_data() -> tuple[list[BettorProfile], ProfileSummary]:
    profiles = [
        BettorProfile(
            user_id="0xAAA",
            n_resolved_bets=30,
            brier_score=0.08,
            mean_position_size=500.0,
            total_volume=15000.0,
            tier=BettorTier.INFORMED,
            n_markets=25,
            win_rate=0.80,
            recency_weight=0.95,
        ),
        BettorProfile(
            user_id="0xBBB",
            n_resolved_bets=25,
            brier_score=0.22,
            mean_position_size=200.0,
            total_volume=5000.0,
            tier=BettorTier.MODERATE,
            n_markets=20,
            win_rate=0.56,
            recency_weight=0.88,
        ),
        BettorProfile(
            user_id="0xCCC",
            n_resolved_bets=20,
            brier_score=0.38,
            mean_position_size=100.0,
            total_volume=2000.0,
            tier=BettorTier.NOISE,
            n_markets=18,
            win_rate=0.35,
            recency_weight=0.70,
        ),
    ]
    summary = ProfileSummary(
        total_users=1000,
        profiled_users=3,
        informed_count=1,
        moderate_count=1,
        noise_count=1,
        median_brier=0.22,
        p10_brier=0.08,
        p90_brier=0.38,
    )
    return profiles, summary


class TestSaveLoadRoundTrip:
    def test_roundtrip(self, tmp_path: Path, sample_data: tuple) -> None:
        profiles, summary = sample_data
        path = tmp_path / "profiles.json"

        save_profiles(profiles, summary, path)
        assert path.exists()

        loaded, loaded_summary = load_profiles(path)
        assert len(loaded) == 3
        assert loaded_summary.profiled_users == 3

    def test_profile_data_preserved(self, tmp_path: Path, sample_data: tuple) -> None:
        profiles, summary = sample_data
        path = tmp_path / "profiles.json"
        save_profiles(profiles, summary, path)

        loaded, _ = load_profiles(path)
        p = loaded["0xAAA"]
        assert p.user_id == "0xAAA"
        assert p.brier_score == 0.08
        assert p.tier == BettorTier.INFORMED
        assert p.win_rate == 0.80
        assert p.recency_weight == 0.95

    def test_summary_preserved(self, tmp_path: Path, sample_data: tuple) -> None:
        profiles, summary = sample_data
        path = tmp_path / "profiles.json"
        save_profiles(profiles, summary, path)

        _, loaded_summary = load_profiles(path)
        assert loaded_summary.total_users == 1000
        assert loaded_summary.median_brier == 0.22
        assert loaded_summary.p10_brier == 0.08

    def test_loaded_as_dict_keyed_by_user_id(self, tmp_path: Path, sample_data: tuple) -> None:
        profiles, summary = sample_data
        path = tmp_path / "profiles.json"
        save_profiles(profiles, summary, path)

        loaded, _ = load_profiles(path)
        assert set(loaded.keys()) == {"0xAAA", "0xBBB", "0xCCC"}

    def test_creates_parent_dirs(self, tmp_path: Path, sample_data: tuple) -> None:
        profiles, summary = sample_data
        path = tmp_path / "nested" / "dir" / "profiles.json"
        save_profiles(profiles, summary, path)
        assert path.exists()

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Profile store not found"):
            load_profiles(tmp_path / "nonexistent.json")

    def test_empty_profiles(self, tmp_path: Path) -> None:
        summary = ProfileSummary(
            total_users=0,
            profiled_users=0,
            informed_count=0,
            moderate_count=0,
            noise_count=0,
            median_brier=0.0,
            p10_brier=0.0,
            p90_brier=0.0,
        )
        path = tmp_path / "empty.json"
        save_profiles([], summary, path)

        loaded, loaded_summary = load_profiles(path)
        assert len(loaded) == 0
        assert loaded_summary.profiled_users == 0
