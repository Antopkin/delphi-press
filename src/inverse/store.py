"""Profile persistence — save/load bettor profiles as Parquet or JSON.

Pipeline stage: Offline (build) + Online (load at pipeline startup).
Spec: docs-site/docs/methodology/inverse-phases.md §5.

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
from collections.abc import ItemsView, KeysView, ValuesView
from dataclasses import dataclass
from pathlib import Path

from src.inverse.schemas import BettorProfile, BettorTier, ProfileSummary

logger = logging.getLogger(__name__)

__all__ = [
    "CompactProfile",
    "CompactProfileStore",
    "load_profiles",
    "load_profiles_compact",
    "save_profiles",
]


# ---------------------------------------------------------------------------
# Compact profile store (~70 MiB instead of ~500 MiB for 348K profiles)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompactProfile:
    """Minimal profile data for signal computation.

    Stores only the 3 fields accessed at runtime by compute_informed_signal():
    tier, brier_score, recency_weight. Uses slots for ~83% memory reduction
    vs full BettorProfile Pydantic model (213 vs 1,254 bytes per object).
    """

    brier_score: float
    recency_weight: float
    tier: BettorTier = BettorTier.INFORMED


class CompactProfileStore:
    """Memory-efficient profile store for the web app.

    Drop-in replacement for dict[str, BettorProfile] in read paths:
    supports .get(), [], in, len(), .keys(), .values(), .items().

    Used by MarketSignalService and compute_informed_signal() at runtime.
    The full BettorProfile dict is still used by the worker for offline tasks.
    """

    def __init__(self, profiles: dict[str, CompactProfile]) -> None:
        self._profiles = profiles

    def get(self, user_id: str, default: CompactProfile | None = None) -> CompactProfile | None:
        return self._profiles.get(user_id, default)

    def __contains__(self, user_id: str) -> bool:
        return user_id in self._profiles

    def __getitem__(self, user_id: str) -> CompactProfile:
        return self._profiles[user_id]

    def __len__(self) -> int:
        return len(self._profiles)

    def __bool__(self) -> bool:
        return bool(self._profiles)

    def keys(self) -> KeysView[str]:
        return self._profiles.keys()

    def values(self) -> ValuesView[CompactProfile]:
        return self._profiles.values()

    def items(self) -> ItemsView[str, CompactProfile]:
        return self._profiles.items()


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


def load_profiles_compact(
    path: Path = DEFAULT_PROFILES_PATH,
    *,
    tier_filter: str | None = "informed",
) -> tuple[CompactProfileStore, ProfileSummary]:
    """Load profiles in compact form — only brier_score, recency_weight, tier.

    Memory-efficient alternative to load_profiles() for the web app.
    Uses ~70 MiB instead of ~500 MiB for 348K profiles (column projection
    + slots dataclass instead of full Pydantic model).

    Args:
        path: Path to the profiles file (.parquet or .json).
        tier_filter: Only return profiles with this tier value.

    Returns:
        Tuple of (CompactProfileStore, ProfileSummary).

    Raises:
        FileNotFoundError: If profiles haven't been built yet.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Profile store not found: {path}. Run scripts/build_bettor_profiles.py first."
        raise FileNotFoundError(msg)

    if path.suffix == ".parquet":
        return _load_parquet_compact(path, tier_filter=tier_filter)
    return _load_json_compact(path, tier_filter=tier_filter)


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
        profiles[profile.user_id.lower()] = profile

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


def _load_parquet_compact(
    path: Path,
    *,
    tier_filter: str | None,
) -> tuple[CompactProfileStore, ProfileSummary]:
    """Load profiles from Parquet with column projection (memory-efficient).

    Reads only user_id + brier_score + recency_weight columns, skipping
    the 7 unused columns entirely. Builds CompactProfile dataclass objects
    instead of full BettorProfile Pydantic models.
    """
    import pyarrow.parquet as pq

    filters = None
    if tier_filter is not None:
        filters = [("tier", "=", tier_filter)]

    # Column projection: read only the 3 columns we need.
    # Empty Parquet files (0 profiles) have no columns — read without projection.
    metadata = pq.read_metadata(path)
    if metadata.num_rows == 0:
        summary_path = _summary_sidecar_path(path)
        if summary_path.exists():
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            summary = ProfileSummary(**data)
        else:
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
        return CompactProfileStore({}), summary

    table = pq.read_table(
        path,
        filters=filters,
        columns=["user_id", "brier_score", "recency_weight"],
    )

    user_ids = table.column("user_id").to_pylist()
    brier_scores = table.column("brier_score").to_pylist()
    recency_weights = table.column("recency_weight").to_pylist()

    del table  # Release pyarrow memory immediately

    tier = BettorTier(tier_filter) if tier_filter is not None else BettorTier.INFORMED
    profiles = {
        uid.lower(): CompactProfile(
            brier_score=bs,
            recency_weight=rw,
            tier=tier,
        )
        for uid, bs, rw in zip(user_ids, brier_scores, recency_weights)
    }

    del user_ids, brier_scores, recency_weights

    # Load summary from sidecar JSON only (no fallback reconstruction)
    summary_path = _summary_sidecar_path(path)
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        summary = ProfileSummary(**data)
    else:
        logger.warning(
            "Summary sidecar %s not found; /markets stats will show zeros",
            summary_path,
        )
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

    store = CompactProfileStore(profiles)
    logger.info(
        "Loaded %d compact profiles from %s (tier_filter=%s)",
        len(store),
        path,
        tier_filter,
    )
    return store, summary


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
        profiles[profile.user_id.lower()] = profile

    logger.info(
        "Loaded %d profiles from %s (tier_filter=%s)",
        len(profiles),
        path,
        tier_filter,
    )
    return profiles, summary


def _load_json_compact(
    path: Path,
    *,
    tier_filter: str | None,
) -> tuple[CompactProfileStore, ProfileSummary]:
    """Load profiles from JSON in compact form (memory-efficient)."""
    data = json.loads(path.read_text(encoding="utf-8"))

    summary = ProfileSummary(**data["summary"])
    tier = BettorTier(tier_filter) if tier_filter is not None else BettorTier.INFORMED
    profiles: dict[str, CompactProfile] = {}
    for raw in data["profiles"]:
        if tier_filter is not None and raw.get("tier") != tier_filter:
            continue
        profiles[raw["user_id"].lower()] = CompactProfile(
            brier_score=raw["brier_score"],
            recency_weight=raw.get("recency_weight", 1.0),
            tier=tier,
        )

    store = CompactProfileStore(profiles)
    logger.info(
        "Loaded %d compact profiles from %s (tier_filter=%s)",
        len(store),
        path,
        tier_filter,
    )
    return store, summary
