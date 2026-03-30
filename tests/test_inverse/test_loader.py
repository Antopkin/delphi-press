"""Tests for src/inverse/loader.py — CSV loading and parsing."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest

from src.inverse.loader import (
    _map_data_api_side,
    _normalize_side,
    _parse_timestamp,
    adapt_data_api_trades,
    load_market_horizons,
    load_resolutions_csv,
    load_trades_csv,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures: tiny CSV files
# ---------------------------------------------------------------------------


@pytest.fixture()
def trades_csv(tmp_path: Path) -> Path:
    """Create a minimal trades CSV file."""
    p = tmp_path / "trades.csv"
    p.write_text(
        "maker_address,market,side,price,size,timestamp\n"
        "0xAAA,market-1,BUY,0.65,100.0,1711929600\n"
        "0xBBB,market-1,SELL,0.35,50.0,1711933200\n"
        "0xAAA,market-2,BUY,0.80,200.0,2026-03-15T12:00:00Z\n"
        "0xCCC,market-2,BUY,0.50,0.0,1711940400\n"  # size=0 → skip
        "bad_row,market-3,BUY,not_a_number,100.0,1711944000\n"  # invalid price → skip
    )
    return p


@pytest.fixture()
def markets_csv(tmp_path: Path) -> Path:
    """Create a minimal markets CSV with resolutions."""
    p = tmp_path / "markets.csv"
    p.write_text(
        "id,question,outcomePrices,active,closed\n"
        'market-1,"Will X happen?","[""1.0"", ""0.0""]",false,true\n'
        'market-2,"Will Y happen?","[""0.0"", ""1.0""]",false,true\n'
        'market-3,"Will Z happen?","[""0.65"", ""0.35""]",false,true\n'  # ambiguous
        'market-4,"Still active?","[""0.50"", ""0.50""]",true,false\n'  # active → skip
    )
    return p


# ---------------------------------------------------------------------------
# load_trades_csv
# ---------------------------------------------------------------------------


class TestLoadTradesCsv:
    def test_loads_valid_trades(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv)
        assert len(trades) == 3  # 5 rows - 1 size=0 - 1 bad price

    def test_first_trade_fields(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv)
        t = trades[0]
        assert t.user_id == "0xaaa"
        assert t.market_id == "market-1"
        assert t.side == "YES"  # BUY → YES
        assert t.price == 0.65
        assert t.size == 100.0

    def test_sell_maps_to_no(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv)
        t = trades[1]
        assert t.side == "NO"

    def test_iso_timestamp_parsed(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv)
        t = trades[2]
        assert t.timestamp.year == 2026
        assert t.timestamp.month == 3

    def test_max_rows(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv, max_rows=2)
        assert len(trades) <= 2

    def test_min_size_filter(self, trades_csv: Path) -> None:
        trades = load_trades_csv(trades_csv, min_size=100.0)
        assert all(t.size >= 100.0 for t in trades)

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_trades_csv(tmp_path / "nonexistent.csv")

    def test_custom_column_map(self, tmp_path: Path) -> None:
        p = tmp_path / "custom.csv"
        p.write_text("wallet,mkt,direction,px,amt,ts\n0xAAA,m1,YES,0.70,100.0,1711929600\n")
        cmap = {
            "user_id": "wallet",
            "market_id": "mkt",
            "side": "direction",
            "price": "px",
            "size": "amt",
            "timestamp": "ts",
        }
        trades = load_trades_csv(p, column_map=cmap)
        assert len(trades) == 1
        assert trades[0].user_id == "0xaaa"

    def test_missing_columns_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.csv"
        p.write_text("col1,col2\na,b\n")
        with pytest.raises(ValueError, match="missing required fields"):
            load_trades_csv(p)


# ---------------------------------------------------------------------------
# load_resolutions_csv
# ---------------------------------------------------------------------------


class TestLoadResolutionsCsv:
    def test_loads_resolved_markets(self, markets_csv: Path) -> None:
        res = load_resolutions_csv(markets_csv)
        assert len(res) == 2  # market-1 YES, market-2 NO; market-3 ambiguous, market-4 active

    def test_yes_resolution(self, markets_csv: Path) -> None:
        res = load_resolutions_csv(markets_csv)
        assert res["market-1"] is True

    def test_no_resolution(self, markets_csv: Path) -> None:
        res = load_resolutions_csv(markets_csv)
        assert res["market-2"] is False

    def test_ambiguous_skipped(self, markets_csv: Path) -> None:
        res = load_resolutions_csv(markets_csv)
        assert "market-3" not in res

    def test_active_skipped(self, markets_csv: Path) -> None:
        res = load_resolutions_csv(markets_csv)
        assert "market-4" not in res

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_resolutions_csv(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestNormalizeSide:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("YES", "YES"),
            ("BUY", "YES"),
            ("LONG", "YES"),
            ("1", "YES"),
            ("TRUE", "YES"),
            ("NO", "NO"),
            ("SELL", "NO"),
            ("SHORT", "NO"),
            ("0", "NO"),
            ("FALSE", "NO"),
        ],
    )
    def test_known_values(self, raw: str, expected: str) -> None:
        assert _normalize_side(raw) == expected

    def test_unknown_returns_none(self) -> None:
        assert _normalize_side("MAYBE") is None
        assert _normalize_side("") is None


class TestParseTimestamp:
    def test_unix_seconds(self) -> None:
        ts = _parse_timestamp("1711929600")
        assert ts is not None
        assert ts.tzinfo == timezone.utc

    def test_unix_milliseconds(self) -> None:
        ts = _parse_timestamp("1711929600000")
        assert ts is not None
        assert ts.year >= 2024

    def test_iso_format(self) -> None:
        ts = _parse_timestamp("2026-03-15T12:00:00Z")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 3

    def test_empty_returns_none(self) -> None:
        assert _parse_timestamp("") is None
        assert _parse_timestamp("   ") is None

    def test_garbage_returns_none(self) -> None:
        assert _parse_timestamp("not-a-date") is None


# ---------------------------------------------------------------------------
# load_market_horizons
# ---------------------------------------------------------------------------


class TestLoadMarketHorizons:
    def test_basic_horizons(self, tmp_path: Path) -> None:
        """CSV with endDate and createdAt columns, 2 markets with known dates."""
        p = tmp_path / "markets.csv"
        p.write_text(
            "id,endDate,createdAt\n"
            "market-1,2026-01-11T00:00:00Z,2026-01-01T00:00:00Z\n"  # 10 days
            "market-2,2026-02-01T00:00:00Z,2026-01-01T00:00:00Z\n"  # 31 days
        )
        horizons = load_market_horizons(p)
        assert len(horizons) == 2
        assert abs(horizons["market-1"] - 10.0) < 0.01
        assert abs(horizons["market-2"] - 31.0) < 0.01

    def test_missing_dates_skipped(self, tmp_path: Path) -> None:
        """Markets without end/start dates are excluded."""
        p = tmp_path / "markets.csv"
        p.write_text(
            "id,endDate,createdAt\n"
            "market-1,2026-01-11T00:00:00Z,2026-01-01T00:00:00Z\n"
            "market-2,,\n"  # both missing → skip
            "market-3,2026-01-11T00:00:00Z,\n"  # start missing → skip
        )
        horizons = load_market_horizons(p)
        assert list(horizons.keys()) == ["market-1"]

    def test_negative_horizon_skipped(self, tmp_path: Path) -> None:
        """endDate before startDate → skipped."""
        p = tmp_path / "markets.csv"
        p.write_text(
            "id,endDate,createdAt\n"
            "market-bad,2026-01-01T00:00:00Z,2026-01-11T00:00:00Z\n"  # end < start
            "market-ok,2026-01-11T00:00:00Z,2026-01-01T00:00:00Z\n"
        )
        horizons = load_market_horizons(p)
        assert "market-bad" not in horizons
        assert "market-ok" in horizons

    def test_auto_detect_columns(self, tmp_path: Path) -> None:
        """closeTime + startDate column names are auto-detected."""
        p = tmp_path / "markets.csv"
        p.write_text(
            "id,closeTime,startDate\n"
            "market-1,2026-03-01T00:00:00Z,2026-02-01T00:00:00Z\n"  # 28 days
        )
        horizons = load_market_horizons(p)
        assert "market-1" in horizons
        assert abs(horizons["market-1"] - 28.0) < 0.01

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_market_horizons(tmp_path / "nonexistent.csv")

    def test_unix_timestamp_dates(self, tmp_path: Path) -> None:
        """Horizons computed correctly when dates are stored as Unix timestamps."""
        p = tmp_path / "markets.csv"
        # 1711929600 = 2024-04-01T00:00:00Z, +7 days = 1712534400
        p.write_text("id,endDate,createdAt\nmarket-1,1712534400,1711929600\n")
        horizons = load_market_horizons(p)
        assert "market-1" in horizons
        assert abs(horizons["market-1"] - 7.0) < 0.01


# ---------------------------------------------------------------------------
# _map_data_api_side
# ---------------------------------------------------------------------------


class TestMapDataApiSide:
    def test_buy_yes_token(self) -> None:
        assert _map_data_api_side("BUY", 0) == "YES"

    def test_buy_no_token(self) -> None:
        assert _map_data_api_side("BUY", 1) == "NO"

    def test_sell_yes_token(self) -> None:
        assert _map_data_api_side("SELL", 0) == "NO"

    def test_sell_no_token(self) -> None:
        assert _map_data_api_side("SELL", 1) == "YES"

    def test_unknown_side_returns_none(self) -> None:
        assert _map_data_api_side("HOLD", 0) is None
        assert _map_data_api_side("", 1) is None


# ---------------------------------------------------------------------------
# adapt_data_api_trades
# ---------------------------------------------------------------------------

# Sample Data API response (realistic field types — all strings from JSON)
_SAMPLE_TRADES = [
    {
        "proxyWallet": "0xAbc123",
        "side": "BUY",
        "conditionId": "0xcond1",
        "size": "150.00",
        "price": "0.65",
        "timestamp": "2026-03-29T10:00:00Z",
        "outcome": "Yes",
        "outcomeIndex": "0",
    },
    {
        "proxyWallet": "0xDef456",
        "side": "SELL",
        "conditionId": "0xcond1",
        "size": "80.00",
        "price": "0.70",
        "timestamp": "2026-03-29T11:00:00Z",
        "outcome": "Yes",
        "outcomeIndex": "0",
    },
    {
        "proxyWallet": "0xGhi789",
        "side": "BUY",
        "conditionId": "0xcond1",
        "size": "200.00",
        "price": "0.35",
        "timestamp": "1711929600",
        "outcome": "No",
        "outcomeIndex": "1",
    },
]


class TestAdaptDataApiTrades:
    def test_happy_path_maps_all_fields(self) -> None:
        """BUY on YES token → side='YES', price preserved, wallet lowered."""
        records = adapt_data_api_trades([_SAMPLE_TRADES[0]], "0xcond1")
        assert len(records) == 1
        r = records[0]
        assert r.user_id == "0xabc123"  # lowercased
        assert r.market_id == "0xcond1"
        assert r.side == "YES"
        assert r.price == 0.65
        assert r.size == 150.0
        assert r.timestamp.year == 2026

    def test_sell_yes_token_maps_to_no(self) -> None:
        """SELL on outcomeIndex=0 (YES token) → side='NO'."""
        records = adapt_data_api_trades([_SAMPLE_TRADES[1]], "0xcond1")
        assert len(records) == 1
        assert records[0].side == "NO"
        assert records[0].price == 0.70

    def test_buy_no_token_maps_to_no(self) -> None:
        """BUY on outcomeIndex=1 (NO token) → side='NO'."""
        records = adapt_data_api_trades([_SAMPLE_TRADES[2]], "0xcond1")
        assert len(records) == 1
        assert records[0].side == "NO"
        assert records[0].price == 0.35

    def test_multiple_trades(self) -> None:
        """All 3 sample trades convert successfully."""
        records = adapt_data_api_trades(_SAMPLE_TRADES, "0xcond1")
        assert len(records) == 3

    def test_skips_invalid_price(self) -> None:
        """Price outside [0, 1] is skipped."""
        bad = {**_SAMPLE_TRADES[0], "price": "1.50"}
        records = adapt_data_api_trades([bad], "0xcond1")
        assert len(records) == 0

    def test_skips_empty_wallet(self) -> None:
        """Empty proxyWallet is skipped."""
        bad = {**_SAMPLE_TRADES[0], "proxyWallet": "  "}
        records = adapt_data_api_trades([bad], "0xcond1")
        assert len(records) == 0

    def test_skips_zero_size(self) -> None:
        """Size <= 0 is skipped."""
        bad = {**_SAMPLE_TRADES[0], "size": "0"}
        records = adapt_data_api_trades([bad], "0xcond1")
        assert len(records) == 0

    def test_parses_unix_timestamp(self) -> None:
        """Unix timestamp string is parsed to datetime."""
        records = adapt_data_api_trades([_SAMPLE_TRADES[2]], "0xcond1")
        assert len(records) == 1
        assert records[0].timestamp.tzinfo == timezone.utc

    def test_empty_input(self) -> None:
        """Empty list returns empty list."""
        assert adapt_data_api_trades([], "0xcond1") == []

    def test_missing_timestamp_skipped(self) -> None:
        """Trade with missing/unparseable timestamp is skipped (no now() fallback)."""
        trade_no_ts = {
            "proxyWallet": "0xWallet1",
            "side": "BUY",
            "outcomeIndex": "0",
            "price": "0.60",
            "size": "100.0",
            # no timestamp field
        }
        trade_bad_ts = {
            "proxyWallet": "0xWallet2",
            "side": "BUY",
            "outcomeIndex": "0",
            "price": "0.60",
            "size": "100.0",
            "timestamp": "not-a-date",
        }
        records = adapt_data_api_trades([trade_no_ts, trade_bad_ts], "0xcond1")
        assert len(records) == 0

    def test_null_outcome_index_handled(self) -> None:
        """outcomeIndex: null in JSON should not crash — trade skipped."""
        trade = {
            "proxyWallet": "0xWallet1",
            "side": "BUY",
            "outcomeIndex": None,  # JSON null
            "price": "0.60",
            "size": "100.0",
            "timestamp": "1711929600",
        }
        records = adapt_data_api_trades([trade], "0xcond1")
        # Should not crash; trade skipped or defaults gracefully
        assert len(records) <= 1

    def test_wallet_case_normalized_to_lowercase(self) -> None:
        """proxyWallet is lowercased to match profile keys from all loaders."""
        # Data API returns mixed-case EIP-55 checksummed addresses
        trade = {
            "proxyWallet": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12",
            "side": "BUY",
            "outcomeIndex": "0",
            "price": "0.60",
            "size": "100.0",
            "timestamp": "1711929600",
        }
        records = adapt_data_api_trades([trade], "0xcond1")
        assert len(records) == 1
        assert records[0].user_id == "0xabcdef1234567890abcdef1234567890abcdef12"


class TestWalletCaseConsistency:
    """Verify all loaders produce lowercase user_id for cross-source matching."""

    def test_parse_trade_row_lowercases_user_id(self) -> None:
        """CSV trade loader lowercases maker_address."""
        from src.inverse.loader import _parse_trade_row

        row = {
            "maker_address": "0xAbCdEf",
            "market": "m1",
            "side": "BUY",
            "price": "0.50",
            "size": "100.0",
            "timestamp": "1711929600",
        }
        cmap = {
            "user_id": "maker_address",
            "market_id": "market",
            "side": "side",
            "price": "price",
            "size": "size",
            "timestamp": "timestamp",
        }
        record = _parse_trade_row(row, cmap, min_size=0.0)
        assert record is not None
        assert record.user_id == "0xabcdef"

    def test_holder_ndjson_lowercases_wallet(self, tmp_path: Path) -> None:
        """NDJSON holder loader lowercases proxyWallet."""
        import json

        from src.inverse.loader import _parse_holder_ndjson

        data = {
            "conditionId": "0xcond1",
            "endDate": "2026-01-01T00:00:00Z",
            "holders": [{"proxyWallet": "0xAbCdEf", "amount": 100, "outcomeIndex": 0}],
        }
        p = tmp_path / "holders.ndjson"
        p.write_text(json.dumps(data) + "\n")
        records = _parse_holder_ndjson(p)
        assert len(records) == 1
        assert records[0].user_id == "0xabcdef"
