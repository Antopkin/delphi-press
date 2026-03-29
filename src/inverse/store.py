"""Profile persistence — save/load bettor profiles as Parquet or JSON.

Pipeline stage: Offline (build) + Online (load at pipeline startup).
Spec: tasks/research/polymarket_inverse_problem.md §5.

Contract:
    Save: list[BettorProfile] + ProfileSummary → parquet/json file.
    Load: file → (dict[str, BettorProfile], ProfileSummary).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.inverse.schemas import BettorProfile, ProfileSummary

logger = logging.getLogger(__name__)

__all__ = [
    "load_profiles",
    "save_profiles",
]

# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------

DEFAULT_PROFILES_PATH = Path("data/inverse/bettor_profiles.json")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_profiles(
    profiles: list[BettorProfile],
    summary: ProfileSummary,
    path: Path = DEFAULT_PROFILES_PATH,
) -> None:
    """Persist profiles and summary to a JSON file.

    Args:
        profiles: List of bettor profiles to save.
        summary: Aggregate summary statistics.
        path: Output file path (default: data/inverse/bettor_profiles.json).

    Uses JSON (not Parquet) to avoid pyarrow dependency for small profile sets.
    For >100K profiles, consider switching to Parquet.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "summary": summary.model_dump(),
        "profiles": [p.model_dump() for p in profiles],
    }

    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info("Saved %d profiles to %s", len(profiles), path)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_profiles(
    path: Path = DEFAULT_PROFILES_PATH,
) -> tuple[dict[str, BettorProfile], ProfileSummary]:
    """Load pre-built profiles from JSON file.

    Args:
        path: Path to the profiles file.

    Returns:
        Tuple of (user_id → BettorProfile dict, ProfileSummary).

    Raises:
        FileNotFoundError: If profiles haven't been built yet.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Profile store not found: {path}. Run scripts/build_bettor_profiles.py first."
        raise FileNotFoundError(msg)

    data = json.loads(path.read_text(encoding="utf-8"))

    summary = ProfileSummary(**data["summary"])
    profiles: dict[str, BettorProfile] = {}
    for raw in data["profiles"]:
        profile = BettorProfile(**raw)
        profiles[profile.user_id] = profile

    logger.info("Loaded %d profiles from %s", len(profiles), path)
    return profiles, summary
