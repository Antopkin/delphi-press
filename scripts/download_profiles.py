#!/usr/bin/env python3
"""Download pre-built Polymarket bettor profiles from GitHub Releases.

Usage:
    uv run python scripts/download_profiles.py

Downloads bettor_profiles.parquet (~62 MB) and bettor_profiles_summary.json
into data/inverse/. Verifies SHA-256 checksum. No-op if data already exists
and is verified.

Spec: tasks/research/polymarket_inverse_problem.md
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — update these when publishing a new data release
# ---------------------------------------------------------------------------

DATA_VERSION = "v1"
GITHUB_REPO = "Antopkin/delphi-press"

FILES = {
    "bettor_profiles.parquet": {
        "sha256": "9242b63ad52d94cb0cd6c5905082010baf1b0e3b4bb4f598e79914d4659f9db2",
    },
    "bettor_profiles_summary.json": {
        "sha256": None,  # small sidecar, no strict check
    },
}

BASE_URL = f"https://github.com/{GITHUB_REPO}/releases/download/data-{DATA_VERSION}"

DEST_DIR = Path(__file__).resolve().parent.parent / "data" / "inverse"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    """Download URL to dest with a simple progress indicator."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    req = urllib.request.Request(url, headers={"User-Agent": "DelphiPress/1.0"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    bar = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))
                    print(
                        f"\r  {bar} {downloaded >> 20}/{total >> 20} MB ({pct:.0f}%)",
                        end="",
                        flush=True,
                    )
        print()

    tmp.rename(dest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def download_profiles() -> None:
    """Download all data files from the GitHub Release."""
    for filename, meta in FILES.items():
        dest = DEST_DIR / filename
        expected_sha = meta["sha256"]

        # Already exists and verified?
        if dest.exists() and expected_sha:
            actual = _sha256(dest)
            if actual == expected_sha:
                print(f"✓ {filename} already verified ({dest})")
                continue
            print(f"✗ {filename} checksum mismatch, re-downloading...")

        url = f"{BASE_URL}/{filename}"
        print(f"↓ Downloading {filename} from release data-{DATA_VERSION}...")
        _download(url, dest)

        # Verify checksum
        if expected_sha:
            actual = _sha256(dest)
            if actual != expected_sha:
                dest.unlink(missing_ok=True)
                print(f"✗ Checksum mismatch for {filename}!")
                print(f"  Expected: {expected_sha}")
                print(f"  Got:      {actual}")
                sys.exit(1)
            print(f"✓ {filename} verified ({dest})")
        else:
            print(f"✓ {filename} saved ({dest})")


if __name__ == "__main__":
    download_profiles()
