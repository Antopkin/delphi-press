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
    "load_holders_from_dataset",
    "load_market_horizons",
    "load_market_prices",
    "load_market_timestamps",
    "load_resolutions_csv",
    "load_resolutions_with_dates",
    "load_trades_csv",
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


def load_market_timestamps(
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> dict[str, tuple[datetime, datetime]]:
    """Load market open/close timestamps for timing_score computation.

    Returns (start_datetime, end_datetime) pairs for each market.
    Markets without both dates are skipped.

    Args:
        path: Path to markets CSV.
        column_map: Maps logical names to CSV columns. Auto-detected if None.

    Returns:
        Dict mapping market_id → (start_dt, end_dt).
    """
    path = Path(path)
    if not path.exists():
        msg = f"Market CSV not found: {path}"
        raise FileNotFoundError(msg)

    market_cmap = column_map or _detect_market_columns(path)
    date_cmap = _detect_date_columns(path) if column_map is None else {}
    merged = {**date_cmap, **market_cmap}
    if column_map:
        merged.update(column_map)

    market_id_col = merged.get("market_id")
    end_col = merged.get("end_date")
    start_col = merged.get("start_date")

    if not market_id_col or not end_col or not start_col:
        return {}

    results: dict[str, tuple[datetime, datetime]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = row.get(market_id_col, "").strip()
            if not mid:
                continue
            start_dt = _parse_timestamp(row.get(start_col, ""))
            end_dt = _parse_timestamp(row.get(end_col, ""))
            if start_dt is not None and end_dt is not None and end_dt > start_dt:
                results[mid] = (start_dt, end_dt)

    logger.info("Loaded timestamps for %d markets from %s", len(results), path.name)
    return results


def load_resolutions_with_dates(
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> dict[str, tuple[bool, datetime]]:
    """Load market resolutions with resolution timestamps.

    Like load_resolutions_csv but includes the resolution date for each market.
    Required for walk-forward validation to filter resolutions by as_of cutoff.

    Args:
        path: Path to CSV with market data.
        column_map: Maps logical names to CSV columns.

    Returns:
        Dict mapping market_id → (resolved_yes, resolution_date).
    """
    path = Path(path)
    if not path.exists():
        msg = f"Market CSV not found: {path}"
        raise FileNotFoundError(msg)

    cmap = column_map or _detect_market_columns(path)
    date_cmap = _detect_date_columns(path) if column_map is None else {}
    merged = {**date_cmap, **cmap}
    if column_map:
        merged.update(column_map)

    end_col = merged.get("end_date")

    results: dict[str, tuple[bool, datetime]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = _parse_resolution_row(row, cmap)
            if parsed is None:
                continue

            market_id, resolved_yes = parsed

            # Parse resolution date
            res_date = None
            if end_col:
                res_date = _parse_timestamp(row.get(end_col, ""))

            if res_date is not None:
                results[market_id] = (resolved_yes, res_date)
            else:
                # No date available — still include with a sentinel far-past date
                # so walk-forward without dates degrades gracefully
                results[market_id] = (resolved_yes, datetime.min.replace(tzinfo=timezone.utc))

    logger.info(
        "Loaded %d resolved markets with dates from %s",
        len(results),
        path.name,
    )
    return results


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
    # Prefer conditionId over id — conditionId matches holder NDJSON data
    for candidate in ("conditionid", "condition_id", "id", "market_id"):
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

    # ISO 8601 (Python 3.11+ fromisoformat handles timezone offsets)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    # Fallback: common formats without timezone
    for fmt in ("%Y-%m-%d %H:%M:%S",):
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
    # Priority: closed=True means resolved (regardless of active flag).
    # On Polymarket, active=True can coexist with closed=True.
    closed_col = cmap.get("closed")
    if closed_col:
        closed_val = row.get(closed_col, "").strip().lower()
        if closed_val in ("false", "0", "no"):
            return None  # Not closed yet
    else:
        # Fallback: check active only if closed column is missing
        active_col = cmap.get("active")
        if active_col:
            active_val = row.get(active_col, "").strip().lower()
            if active_val in ("true", "1", "yes"):
                return None  # Still active

    # Parse outcomePrices — JSON-stringified array: '["1.0", "0.0"]' or '[1.0, 0.0]'
    raw_prices = row.get(outcome_col, "").strip()
    if not raw_prices:
        return None

    try:
        prices: list[Any] = json.loads(raw_prices)
    except json.JSONDecodeError:
        return None

    if not isinstance(prices, list) or not prices:
        return None

    try:
        yes_price = float(prices[0])
    except (ValueError, TypeError, KeyError):
        return None

    # Resolved: outcomePrices[0] == 1.0 → YES, == 0.0 → NO
    if abs(yes_price - 1.0) < 0.01:
        return (market_id, True)
    if abs(yes_price - 0.0) < 0.01:
        return (market_id, False)

    # Ambiguous (e.g. 0.65) — market not clearly resolved
    return None


# ---------------------------------------------------------------------------
# Market prices loader (for holder enrichment)
# ---------------------------------------------------------------------------


def load_market_prices(path: Path) -> dict[str, float]:
    """Load last trade prices from markets CSV.

    Returns mapping conditionId → YES probability (lastTradePrice or outcomePrices[0]).
    Used to enrich holder positions with realistic price data.

    Args:
        path: Path to markets CSV (ismetsemedov dataset).

    Returns:
        Dict mapping conditionId → float price in [0, 1].
    """
    path = Path(path)
    if not path.exists():
        return {}

    cmap = _detect_market_columns(path)
    market_id_col = cmap.get("market_id")
    if not market_id_col:
        return {}

    prices: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = row.get(market_id_col, "").strip()
            if not mid:
                continue

            # Try lastTradePrice first, then outcomePrices[0]
            ltp = row.get("lastTradePrice", "").strip()
            if ltp:
                try:
                    p = float(ltp)
                    if 0.0 < p < 1.0:
                        prices[mid] = p
                        continue
                except ValueError:
                    pass

            # Fallback to outcomePrices
            outcome_col = cmap.get("outcome_prices")
            if outcome_col:
                raw = row.get(outcome_col, "").strip()
                if raw:
                    try:
                        parsed = json.loads(raw)
                        p = float(parsed[0])
                        if 0.0 < p < 1.0:
                            prices[mid] = p
                    except (json.JSONDecodeError, ValueError, IndexError, TypeError):
                        pass

    logger.info("Loaded prices for %d markets from %s", len(prices), path.name)
    return prices


# ---------------------------------------------------------------------------
# Market horizons loader
# ---------------------------------------------------------------------------


def load_market_horizons(
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """Load market horizons (duration in days) from markets CSV.

    Horizon = endDate - createdDate (or first available date).
    Markets without both dates are skipped.

    Args:
        path: Path to markets CSV (e.g., ismetsemedov dataset).
        column_map: Maps logical names to CSV columns. Auto-detected if None.
            Recognised logical keys: ``market_id``, ``end_date``, ``start_date``.

    Returns:
        Dict mapping market_id → horizon_days.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Market CSV not found: {path}"
        raise FileNotFoundError(msg)

    market_cmap = column_map or _detect_market_columns(path)
    date_cmap = _detect_date_columns(path) if column_map is None else {}

    # Merge: explicit column_map may supply end_date/start_date directly
    merged: dict[str, str] = {**date_cmap, **market_cmap}
    if column_map:
        merged.update(column_map)

    market_id_col = merged.get("market_id")
    end_col = merged.get("end_date")
    start_col = merged.get("start_date")

    if not market_id_col or not end_col or not start_col:
        logger.warning(
            "load_market_horizons: could not resolve required columns "
            "(market_id=%r, end_date=%r, start_date=%r) in %s",
            market_id_col,
            end_col,
            start_col,
            path.name,
        )
        return {}

    horizons: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            market_id = row.get(market_id_col, "").strip()
            if not market_id:
                continue

            end_dt = _parse_timestamp(row.get(end_col, ""))
            start_dt = _parse_timestamp(row.get(start_col, ""))

            if end_dt is None or start_dt is None:
                continue

            horizon_days = (end_dt - start_dt).total_seconds() / 86400.0
            if horizon_days <= 0:
                continue

            horizons[market_id] = horizon_days

    logger.info("Loaded horizons for %d markets from %s", len(horizons), path.name)
    return horizons


def _detect_date_columns(path: Path) -> dict[str, str]:
    """Auto-detect end_date and start_date columns for market CSV."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

    header_lower = {col.strip().lower(): col.strip() for col in header}

    cmap: dict[str, str] = {}

    # end_date: endDate / end_date / closeTime / close_time / closedTime
    for candidate in ("enddate", "end_date", "closetime", "close_time", "closedtime"):
        if candidate in header_lower:
            cmap["end_date"] = header_lower[candidate]
            break

    # start_date: createdAt / created_at / startDate / start_date / created_time
    for candidate in ("createdat", "created_at", "startdate", "start_date", "created_time"):
        if candidate in header_lower:
            cmap["start_date"] = header_lower[candidate]
            break

    return cmap


# ---------------------------------------------------------------------------
# Holder NDJSON loader (sandeepkumarfromin Polymarket_dataset)
# ---------------------------------------------------------------------------


def load_holders_from_dataset(
    dataset_dir: Path,
    *,
    market_prices: dict[str, float] | None = None,
    min_amount: float = 0.0,
) -> list[TradeRecord]:
    """Load holder positions from Polymarket_dataset NDJSON files.

    Walks market=0x.../holder/*.ndjson directories and converts each
    holder position into a TradeRecord.

    Args:
        dataset_dir: Root of Polymarket_dataset (contains market=0x... dirs).
        market_prices: Optional mapping conditionId → last market price (YES).
            Used as trade price. If not provided, defaults to 0.5.
        min_amount: Minimum holder amount to include.

    Returns:
        List of TradeRecord objects (one per holder per token per market).

    Raises:
        FileNotFoundError: If dataset_dir does not exist.
    """
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.exists():
        msg = f"Dataset directory not found: {dataset_dir}"
        raise FileNotFoundError(msg)

    records: list[TradeRecord] = []
    market_dirs = [d for d in dataset_dir.iterdir() if d.is_dir() and d.name.startswith("market=")]

    for market_dir in market_dirs:
        holder_dir = market_dir / "holder"
        if not holder_dir.exists():
            continue

        for ndjson_file in holder_dir.iterdir():
            if ndjson_file.suffix != ".ndjson":
                continue

            parsed = _parse_holder_ndjson(
                ndjson_file,
                market_prices=market_prices,
                min_amount=min_amount,
            )
            records.extend(parsed)

    logger.info(
        "Loaded %d holder positions from %d markets in %s",
        len(records),
        len(market_dirs),
        dataset_dir.name,
    )
    return records


def _parse_holder_ndjson(
    path: Path,
    *,
    market_prices: dict[str, float] | None = None,
    min_amount: float = 0.0,
) -> list[TradeRecord]:
    """Parse a single holder NDJSON file.

    Each file contains space-separated JSON objects (not newline-separated).
    Each object has: conditionId, token_id, holders[].
    Each holder has: proxyWallet, amount, outcomeIndex, name.
    """
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []

    records: list[TradeRecord] = []
    decoder = json.JSONDecoder()
    pos = 0
    length = len(raw)

    while pos < length:
        # Skip whitespace
        while pos < length and raw[pos] in " \n\r\t":
            pos += 1
        if pos >= length:
            break

        try:
            obj, end = decoder.raw_decode(raw, pos)
            pos = end
        except json.JSONDecodeError:
            break

        condition_id = obj.get("conditionId", "")
        capture_ts = obj.get("capture_ts_ms")
        timestamp = (
            datetime.fromtimestamp(capture_ts / 1000, tz=timezone.utc)
            if capture_ts
            else datetime(2026, 1, 1, tzinfo=timezone.utc)
        )

        # Default price: use market_prices if available, else 0.5
        default_price = 0.5
        if market_prices and condition_id in market_prices:
            default_price = market_prices[condition_id]

        for holder in obj.get("holders", []):
            wallet = holder.get("proxyWallet", "").strip()
            amount = holder.get("amount", 0)
            outcome_index = holder.get("outcomeIndex", 0)

            if not wallet or amount <= min_amount:
                continue

            side = "YES" if outcome_index == 0 else "NO"
            # For holders: price = confidence proxy.
            # YES holder → implied YES probability = default_price
            # NO holder → implied YES probability = 1 - default_price
            price = max(0.01, min(0.99, default_price if side == "YES" else (1.0 - default_price)))

            records.append(
                TradeRecord(
                    user_id=wallet,
                    market_id=condition_id,
                    side=side,
                    price=price,
                    size=float(amount),
                    timestamp=timestamp,
                )
            )

    return records
