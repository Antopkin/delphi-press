#!/bin/sh
# Docker entrypoint: download bettor profiles if missing, then exec CMD.

PROFILES="/app/data/inverse/bettor_profiles.parquet"

if [ ! -f "$PROFILES" ]; then
    echo "[entrypoint] Bettor profiles not found, downloading..."
    python /app/scripts/download_profiles.py || echo "[entrypoint] WARNING: download failed, continuing without profiles"
fi

exec "$@"
