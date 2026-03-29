#!/usr/bin/env python3
"""One-time conversion: bettor_profiles.json → bettor_profiles.parquet.

Usage:
    uv run python scripts/convert_json_to_parquet.py \
        --input data/inverse/bettor_profiles.json \
        --output data/inverse/bettor_profiles.parquet

Reads the existing 506 MB JSON file and writes a ZSTD-compressed Parquet file
(~60 MB) plus a sidecar _summary.json. The JSON file is not deleted.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inverse.store import load_profiles, save_profiles

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert bettor profiles JSON → Parquet.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/inverse/bettor_profiles.json"),
        help="Input JSON file path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inverse/bettor_profiles.parquet"),
        help="Output Parquet file path",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    if args.input.suffix != ".json":
        logger.error("Input must be a .json file, got: %s", args.input.suffix)
        sys.exit(1)

    if args.output.suffix != ".parquet":
        logger.error("Output must be a .parquet file, got: %s", args.output.suffix)
        sys.exit(1)

    logger.info("Loading profiles from %s ...", args.input)
    t0 = time.perf_counter()
    # Load ALL profiles (no tier filter) for full conversion
    profiles_dict, summary = load_profiles(args.input, tier_filter=None)
    profiles_list = list(profiles_dict.values())
    t_load = time.perf_counter() - t0
    logger.info("Loaded %d profiles in %.1fs", len(profiles_list), t_load)

    logger.info("Saving to %s ...", args.output)
    t1 = time.perf_counter()
    save_profiles(profiles_list, summary, args.output)
    t_save = time.perf_counter() - t1
    logger.info("Saved in %.1fs", t_save)

    # Report sizes
    input_size = args.input.stat().st_size / (1024 * 1024)
    output_size = args.output.stat().st_size / (1024 * 1024)
    ratio = input_size / output_size if output_size > 0 else 0
    logger.info(
        "Compression: %.1f MB → %.1f MB (%.1fx reduction)",
        input_size,
        output_size,
        ratio,
    )


if __name__ == "__main__":
    main()
