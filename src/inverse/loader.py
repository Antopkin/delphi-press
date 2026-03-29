"""Dataset loaders for Polymarket trade and market data.

Pipeline stage: Offline data ingestion (pre-profiling).
Spec: tasks/research/polymarket_inverse_problem.md §6.

Contract:
    Input: CSV/Parquet files from Kaggle datasets.
    Output: list[TradeRecord], dict[str, bool] (market_id → resolved_yes).

Supported datasets:
    - sandeepkumarfromin/full-market-data-from-polymarket (trades, CC0)
    - ismetsemedov/polymarket-prediction-markets (markets + resolutions)
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.inverse.schemas import TradeRecord

logger = logging.getLogger(__name__)

__all__ = [
    "load_trades_csv",
    "load_resolutions_csv",
]

# ---------------------------------------------------------------------------
# Column mapping presets for known Kaggle datasets
# ---------------------------------------------------------------------------

#: sandeepkumarfromin dataset — trade-level data with maker/taker
TRADE_COLUMNS_SANDEEP = {
    "user_id": "maker_address",
    "market_id": "market",
    "side": "side",
    "price": "price",
    "size": "size",
    "timestamp": "timestamp",
}

#: ismetsemedov dataset — market metadata with resolution outcomes
MARKET_COLUMNS_ISMET = {
    "market_id": "id",
    "question": "question",
    "outcome_prices": "outcomePrices",
    "active": "active",
    "closed": "closed",
}


# ---------------------------------------------------------------------------
# Trade loader
# ---------------------------------------------------------------------------


def load_trades_csv(
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
    min_size: float = 0.0,
    max_rows: int | None = None,
) -> list[TradeRecord]:
    """Load trades from a CSV file.

    Args:
        path: Path to CSV file with trade data.
        column_map: Maps logical names (user_id, market_id, side, price, size,
            timestamp) to actual CSV column names. Defaults to auto-detection.
        min_size: Minimum trade size in USD to include.
        max_rows: Cap on number of rows to load (None = all).

    Returns:
        List of TradeRecord objects.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Trade CSV not found: {path}"
        raise FileNotFoundError(msg)

    cmap = column_map or _detect_trade_columns(path)
    _validate_column_map(cmap, {"user_id", "market_id", "side", "price", "size", "timestamp"})

    trades: list[TradeRecord] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if max_rows is not None and i >= max_rows:
                break
            trade = _parse_trade_row(row, cmap, min_size)
            if trade is not None:
                trades.append(trade)

    logger.info("Loaded %d trades from %s", len(trades), path.name)
    return trades


# ---------------------------------------------------------------------------
# Resolution loader
# ---------------------------------------------------------------------------


def load_resolutions_csv(
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> dict[str, bool]:
    """Load market resolution outcomes from a CSV file.

    Determines resolution from outcomePrices field: if first outcome price == 1.0,
    market resolved YES; if == 0.0, resolved NO. Markets still active or with
    ambiguous outcomes are skipped.

    Args:
        path: Path to CSV with market data.
        column_map: Maps logical names to CSV columns. Defaults to auto-detection.

    Returns:
        Dict mapping market_id → resolved_yes (bool).

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Market CSV not found: {path}"
        raise FileNotFoundError(msg)

    cmap = column_map or _detect_market_columns(path)

    resolutions: dict[str, bool] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result = _parse_resolution_row(row, cmap)
            if result is not None:
                market_id, resolved_yes = result
                resolutions[market_id] = resolved_yes

    logger.info("Loaded %d resolved markets from %s", len(resolutions), path.name)
    return resolutions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_trade_columns(path: Path) -> dict[str, str]:
    """Auto-detect column mapping by reading the CSV header."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

    header_lower = {col.strip().lower(): col.strip() for col in header}

    # Try known patterns
    cmap: dict[str, str] = {}

    # user_id: maker_address, maker, user, user_id, wallet
    for candidate in ("maker_address", "maker", "user_id", "user", "wallet", "taker_address"):
        if candidate in header_lower:
            cmap["user_id"] = header_lower[candidate]
            break

    # market_id: market, market_id, condition_id, market_slug
    for candidate in ("market", "market_id", "condition_id", "market_slug"):
        if candidate in header_lower:
            cmap["market_id"] = header_lower[candidate]
            break

    # side: side, outcome, type
    for candidate in ("side", "outcome", "type"):
        if candidate in header_lower:
            cmap["side"] = header_lower[candidate]
            break

    # price: price, avg_price, trade_price
    for candidate in ("price", "avg_price", "trade_price"):
        if candidate in header_lower:
            cmap["price"] = header_lower[candidate]
            break

    # size: size, amount, volume, shares
    for candidate in ("size", "amount", "volume", "shares"):
        if candidate in header_lower:
            cmap["size"] = header_lower[candidate]
            break

    # timestamp: timestamp, created_at, time, ts
    for candidate in ("timestamp", "created_at", "time", "ts", "date"):
        if candidate in header_lower:
            cmap["timestamp"] = header_lower[candidate]
            break

    return cmap


def _detect_market_columns(path: Path) -> dict[str, str]:
    """Auto-detect column mapping for market CSV."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

    header_lower = {col.strip().lower(): col.strip() for col in header}

    cmap: dict[str, str] = {}
    for candidate in ("id", "market_id", "condition_id"):
        if candidate in header_lower:
            cmap["market_id"] = header_lower[candidate]
            break

    for candidate in ("outcomeprices", "outcome_prices"):
        if candidate in header_lower:
            cmap["outcome_prices"] = header_lower[candidate]
            break

    for candidate in ("active",):
        if candidate in header_lower:
            cmap["active"] = header_lower[candidate]
            break

    for candidate in ("closed",):
        if candidate in header_lower:
            cmap["closed"] = header_lower[candidate]
            break

    return cmap


def _validate_column_map(cmap: dict[str, str], required: set[str]) -> None:
    """Raise ValueError if required logical columns are missing from mapping."""
    missing = required - set(cmap)
    if missing:
        msg = f"Column mapping missing required fields: {sorted(missing)}"
        raise ValueError(msg)


def _parse_trade_row(
    row: dict[str, str],
    cmap: dict[str, str],
    min_size: float,
) -> TradeRecord | None:
    """Parse a single CSV row into a TradeRecord, or None if invalid."""
    try:
        price = float(row[cmap["price"]])
        size = float(row[cmap["size"]])
    except (ValueError, KeyError):
        return None

    if size < min_size or size <= 0:
        return None
    if price < 0.0 or price > 1.0:
        return None

    raw_side = row.get(cmap["side"], "").strip().upper()
    side = _normalize_side(raw_side)
    if side is None:
        return None

    timestamp = _parse_timestamp(row.get(cmap["timestamp"], ""))
    if timestamp is None:
        return None

    return TradeRecord(
        user_id=row[cmap["user_id"]].strip(),
        market_id=row[cmap["market_id"]].strip(),
        side=side,
        price=price,
        size=size,
        timestamp=timestamp,
    )


def _normalize_side(raw: str) -> str | None:
    """Normalize trade side to 'YES' or 'NO'."""
    if raw in ("YES", "BUY", "LONG", "1", "TRUE"):
        return "YES"
    if raw in ("NO", "SELL", "SHORT", "0", "FALSE"):
        return "NO"
    return None


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse timestamp from various formats."""
    raw = raw.strip()
    if not raw:
        return None

    # Unix timestamp (seconds or milliseconds)
    try:
        val = float(raw)
        if val > 1e12:  # milliseconds
            val /= 1000
        return datetime.fromtimestamp(val, tz=timezone.utc)
    except ValueError:
        pass

    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _parse_resolution_row(
    row: dict[str, str],
    cmap: dict[str, str],
) -> tuple[str, bool] | None:
    """Parse a market row into (market_id, resolved_yes), or None if unresolved."""
    market_id_col = cmap.get("market_id")
    outcome_col = cmap.get("outcome_prices")
    if not market_id_col or not outcome_col:
        return None

    market_id = row.get(market_id_col, "").strip()
    if not market_id:
        return None

    # Check if market is closed/resolved
    active_col = cmap.get("active")
    closed_col = cmap.get("closed")
    if active_col:
        active_val = row.get(active_col, "").strip().lower()
        if active_val in ("true", "1", "yes"):
            return None  # Still active

    if closed_col:
        closed_val = row.get(closed_col, "").strip().lower()
        if closed_val in ("false", "0", "no"):
            return None  # Not closed yet

    # Parse outcomePrices — JSON-stringified array: '["1.0", "0.0"]' or '[1.0, 0.0]'
    raw_prices = row.get(outcome_col, "").strip()
    if not raw_prices:
        return None

    try:
        prices: list[Any] = json.loads(raw_prices)
    except json.JSONDecodeError:
        return None

    if not prices or len(prices) < 1:
        return None

    try:
        yes_price = float(prices[0])
    except (ValueError, TypeError):
        return None

    # Resolved: outcomePrices[0] == 1.0 → YES, == 0.0 → NO
    if abs(yes_price - 1.0) < 0.01:
        return (market_id, True)
    if abs(yes_price - 0.0) < 0.01:
        return (market_id, False)

    # Ambiguous (e.g. 0.65) — market not clearly resolved
    return None
