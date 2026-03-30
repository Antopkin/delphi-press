#!/usr/bin/env bash
# Weekly refresh of Polymarket bettor profiles.
#
# Downloads fresh trades.parquet from HuggingFace (if updated),
# rebuilds bucketed aggregates and bettor profiles, then restarts
# the worker container to pick up new data.
#
# Cron: 0 3 * * 0  /home/deploy/delphi_press/scripts/refresh_profiles.sh
#
# Requirements:
#   - huggingface-cli (pip install huggingface-hub)
#   - DuckDB (via Python: uv run python)
#   - Docker Compose

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────

REPO_DIR="${REPO_DIR:-/home/deploy/delphi_press}"
DATA_DIR="${DATA_DIR:-/home/deploy/data/inverse/hf_cache}"
HF_DATASET="SII-WANGZJ/Polymarket_data"
TRADES_FILE="trades.parquet"
STALE_DAYS=10
LOG_FILE="/var/log/inverse_refresh.log"
MEMORY_LIMIT="2GB"
THREADS=2

# ── Logging ────────────────────────────────────────────────────────

log() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "FATAL: $*"
    exit 1
}

# ── Step 0: Check disk space ───────────────────────────────────────

AVAIL_GB=$(df --output=avail -BG "$DATA_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "$AVAIL_GB" ] && [ "$AVAIL_GB" -lt 40 ]; then
    log "WARNING: Only ${AVAIL_GB}GB free. Need ~35GB for trades download."
    # Try to clean old merged positions (temporal leak version)
    OLD_MERGED="$DATA_DIR/_merged_positions.parquet"
    if [ -f "$OLD_MERGED" ]; then
        SIZE=$(du -h "$OLD_MERGED" | cut -f1)
        log "Removing old merged positions ($SIZE): $OLD_MERGED"
        rm -f "$OLD_MERGED"
    fi
fi

# ── Step 1: Check HuggingFace dataset freshness ───────────────────

log "Checking HuggingFace dataset freshness..."

LOCAL_TRADES="$DATA_DIR/$TRADES_FILE"
NEEDS_DOWNLOAD=false

if [ ! -f "$LOCAL_TRADES" ]; then
    log "No local trades file found. Full download required."
    NEEDS_DOWNLOAD=true
else
    LOCAL_MTIME=$(stat -c %Y "$LOCAL_TRADES" 2>/dev/null || stat -f %m "$LOCAL_TRADES" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    AGE_DAYS=$(( (NOW - LOCAL_MTIME) / 86400 ))
    log "Local trades age: ${AGE_DAYS} days"

    if [ "$AGE_DAYS" -ge "$STALE_DAYS" ]; then
        log "Local data is ${AGE_DAYS} days old (threshold: ${STALE_DAYS}). Downloading fresh copy."
        NEEDS_DOWNLOAD=true
    else
        log "Local data is fresh enough (${AGE_DAYS} < ${STALE_DAYS} days). Skipping download."
    fi
fi

# ── Step 2: Download trades.parquet ────────────────────────────────

if [ "$NEEDS_DOWNLOAD" = true ]; then
    log "Downloading $TRADES_FILE from HuggingFace ($HF_DATASET)..."
    TEMP_FILE="$DATA_DIR/${TRADES_FILE}.tmp"

    if command -v huggingface-cli &>/dev/null; then
        huggingface-cli download "$HF_DATASET" "$TRADES_FILE" \
            --repo-type dataset \
            --local-dir "$DATA_DIR" \
            --local-dir-use-symlinks False \
            2>&1 | tee -a "$LOG_FILE"
    else
        # Fallback: direct URL download
        HF_URL="https://huggingface.co/datasets/${HF_DATASET}/resolve/main/${TRADES_FILE}"
        log "huggingface-cli not found. Using wget: $HF_URL"
        wget -q --show-progress -O "$TEMP_FILE" "$HF_URL" 2>&1 | tee -a "$LOG_FILE" \
            && mv "$TEMP_FILE" "$LOCAL_TRADES" \
            || die "Download failed"
    fi

    log "Download complete. Size: $(du -h "$LOCAL_TRADES" | cut -f1)"
else
    log "Skipping download."
fi

# ── Step 3: Rebuild bucketed aggregates ────────────────────────────

log "Rebuilding bucketed aggregates..."
cd "$REPO_DIR"

uv run python scripts/duckdb_build_bucketed.py \
    --data-dir "$DATA_DIR" \
    --memory-limit "$MEMORY_LIMIT" \
    --threads "$THREADS" \
    --verbose \
    2>&1 | tee -a "$LOG_FILE"

BUCKETED="$DATA_DIR/_merged_bucketed.parquet"
if [ ! -f "$BUCKETED" ]; then
    die "Bucketed file not created: $BUCKETED"
fi
log "Bucketed file: $(du -h "$BUCKETED" | cut -f1)"

# ── Step 4: Rebuild bettor profiles ────────────────────────────────

log "Rebuilding bettor profiles..."

uv run python scripts/duckdb_build_profiles.py \
    --data-dir "$DATA_DIR" \
    --memory-limit "$MEMORY_LIMIT" \
    --threads "$THREADS" \
    --verbose \
    2>&1 | tee -a "$LOG_FILE"

PROFILES="$(dirname "$DATA_DIR")/bettor_profiles.parquet"
if [ ! -f "$PROFILES" ]; then
    # Check alternate location
    PROFILES="$DATA_DIR/../bettor_profiles.parquet"
fi
log "Profiles: $(du -h "$PROFILES" 2>/dev/null | cut -f1 || echo 'not found')"

# ── Step 5: Restart worker ─────────────────────────────────────────

log "Restarting worker container..."
cd "$REPO_DIR"

if docker compose ps worker --format '{{.Status}}' 2>/dev/null | grep -q "Up"; then
    docker compose restart worker 2>&1 | tee -a "$LOG_FILE"
    log "Worker restarted."
else
    log "WARNING: Worker container not running. Skipping restart."
fi

# ── Summary ────────────────────────────────────────────────────────

log "Profile refresh complete."
log "  Trades:   $(du -h "$LOCAL_TRADES" 2>/dev/null | cut -f1)"
log "  Bucketed: $(du -h "$BUCKETED" 2>/dev/null | cut -f1)"
log "  Profiles: $(du -h "$PROFILES" 2>/dev/null | cut -f1)"
log "  Disk:     $(df -h "$DATA_DIR" 2>/dev/null | tail -1 | awk '{print $4 " free"}')"
