"""Profile persistence — save/load bettor profiles as Parquet or JSON.

Pipeline stage: Offline (build) + Online (load at pipeline startup).
Spec: tasks/research/polymarket_inverse_problem.md §5.

Contract:
    Save: list[BettorProfile] + ProfileSummary → parquet/json file.
    Load: file → (dict[str, BettorProfile], ProfileSummary).

Parquet (recommended): ~60 MB for 1.7M profiles (ZSTD), predicate pushdown
for tier filtering. Requires pyarrow (in [inverse] optional extra).

JSON (legacy): Human-readable, no extra deps. ~506 MB for 1.7M profiles.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.inverse.schemas import BettorProfile, BettorTier, ProfileSummary

logger = logging.getLogger(__name__)

__all__ = [
    "load_profiles",
    "save_profiles",
]

# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------

DEFAULT_PROFILES_PATH = Path("data/inverse/bettor_profiles.parquet")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_profiles(
    profiles: list[BettorProfile],
    summary: ProfileSummary,
    path: Path = DEFAULT_PROFILES_PATH,
) -> None:
    """Persist profiles and summary to a Parquet or JSON file.

    Format is determined by file extension:
        .parquet → Parquet (ZSTD) + sidecar _summary.json.
        .json → JSON (legacy, for backward compatibility).

    Args:
        profiles: List of bettor profiles to save.
        summary: Aggregate summary statistics.
        path: Output file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix == ".parquet":
        _save_parquet(profiles, summary, path)
    else:
        _save_json(profiles, summary, path)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_profiles(
    path: Path = DEFAULT_PROFILES_PATH,
    *,
    tier_filter: str | None = "informed",
) -> tuple[dict[str, BettorProfile], ProfileSummary]:
    """Load pre-built profiles from Parquet or JSON file.

    Format is determined by file extension.

    Args:
        path: Path to the profiles file (.parquet or .json).
        tier_filter: Only return profiles with this tier value.
            Default "informed" — loads only INFORMED tier (optimal for pipeline).
            Pass None to load all profiles (for research/analysis).

    Returns:
        Tuple of (user_id → BettorProfile dict, ProfileSummary).

    Raises:
        FileNotFoundError: If profiles haven't been built yet.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Profile store not found: {path}. Run scripts/build_bettor_profiles.py first."
        raise FileNotFoundError(msg)

    if path.suffix == ".parquet":
        return _load_parquet(path, tier_filter=tier_filter)
    return _load_json(path, tier_filter=tier_filter)


# ---------------------------------------------------------------------------
# Parquet implementation
# ---------------------------------------------------------------------------


def _save_parquet(
    profiles: list[BettorProfile],
    summary: ProfileSummary,
    path: Path,
) -> None:
    """Save profiles as Parquet (ZSTD) + sidecar summary JSON."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [p.model_dump() for p in profiles]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")
    logger.info("Saved %d profiles to %s (Parquet/ZSTD)", len(profiles), path)

    # Sidecar summary
    summary_path = _summary_sidecar_path(path)
    summary_path.write_text(
        json.dumps(summary.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Saved summary to %s", summary_path)


def _load_parquet(
    path: Path,
    *,
    tier_filter: str | None,
) -> tuple[dict[str, BettorProfile], ProfileSummary]:
    """Load profiles from Parquet with optional predicate pushdown."""
    import pyarrow.parquet as pq

    # Apply predicate pushdown for tier filtering
    filters = None
    if tier_filter is not None:
        filters = [("tier", "=", tier_filter)]

    table = pq.read_table(path, filters=filters)
    rows = table.to_pylist()

    profiles: dict[str, BettorProfile] = {}
    for raw in rows:
        profile = BettorProfile(**raw)
        profiles[profile.user_id] = profile

    # Load summary from sidecar
    summary = _load_summary_sidecar(path, profiles, tier_filter)

    logger.info(
        "Loaded %d profiles from %s (tier_filter=%s)",
        len(profiles),
        path,
        tier_filter,
    )
    return profiles, summary


def _summary_sidecar_path(parquet_path: Path) -> Path:
    """Compute sidecar summary path from Parquet path."""
    return parquet_path.with_name(parquet_path.stem + "_summary.json")


def _load_summary_sidecar(
    parquet_path: Path,
    profiles: dict[str, BettorProfile],
    tier_filter: str | None,
) -> ProfileSummary:
    """Load ProfileSummary from sidecar JSON, or reconstruct from profiles."""
    summary_path = _summary_sidecar_path(parquet_path)
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        return ProfileSummary(**data)

    # Reconstruct from loaded profiles (fallback)
    brier_scores = [p.brier_score for p in profiles.values()]
    if not brier_scores:
        return ProfileSummary(
            total_users=0,
            profiled_users=0,
            informed_count=0,
            moderate_count=0,
            noise_count=0,
            median_brier=0.0,
            p10_brier=0.0,
            p90_brier=0.0,
        )

    brier_scores.sort()
    n = len(brier_scores)
    informed = sum(1 for p in profiles.values() if p.tier == BettorTier.INFORMED)
    moderate = sum(1 for p in profiles.values() if p.tier == BettorTier.MODERATE)
    noise = sum(1 for p in profiles.values() if p.tier == BettorTier.NOISE)

    return ProfileSummary(
        total_users=n,
        profiled_users=n,
        informed_count=informed,
        moderate_count=moderate,
        noise_count=noise,
        median_brier=brier_scores[n // 2],
        p10_brier=brier_scores[max(0, int(n * 0.10) - 1)],
        p90_brier=brier_scores[min(n - 1, int(n * 0.90))],
    )


# ---------------------------------------------------------------------------
# JSON implementation (legacy)
# ---------------------------------------------------------------------------


def _save_json(
    profiles: list[BettorProfile],
    summary: ProfileSummary,
    path: Path,
) -> None:
    """Persist profiles and summary to a JSON file (legacy format)."""
    data = {
        "summary": summary.model_dump(),
        "profiles": [p.model_dump() for p in profiles],
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info("Saved %d profiles to %s (JSON)", len(profiles), path)


def _load_json(
    path: Path,
    *,
    tier_filter: str | None,
) -> tuple[dict[str, BettorProfile], ProfileSummary]:
    """Load profiles from JSON file with optional tier filtering."""
    data = json.loads(path.read_text(encoding="utf-8"))

    summary = ProfileSummary(**data["summary"])
    profiles: dict[str, BettorProfile] = {}
    for raw in data["profiles"]:
        if tier_filter is not None and raw.get("tier") != tier_filter:
            continue
        profile = BettorProfile(**raw)
        profiles[profile.user_id] = profile

    logger.info(
        "Loaded %d profiles from %s (tier_filter=%s)",
        len(profiles),
        path,
        tier_filter,
    )
    return profiles, summary
