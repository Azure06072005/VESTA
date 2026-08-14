"""F002 verification.

normalize_ohlcv/write_ohlcv are pure/DB-only and tested here without
network access. fetch_raw() (the live vnstock call) is NOT covered --
this sandbox cannot reach vnstock's API domain. Run
discover_ohlcv_schema.py against a real key to confirm RAW_COLUMN_ALIASES
in src/crawlers/market_ohlcv.py still matches reality.
"""
from __future__ import annotations

import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402
from crawlers import market_ohlcv  # noqa: E402


def _sample_raw_df(n_days: int = 5) -> pd.DataFrame:
    # UNCONFIRMED column names -- see market_ohlcv.py module docstring.
    dates = pd.date_range("2024-01-02", periods=n_days, freq="B")
    return pd.DataFrame(
        {
            "time": dates,
            "open": [93.4 + i for i in range(n_days)],
            "high": [94.0 + i for i in range(n_days)],
            "low": [93.0 + i for i in range(n_days)],
            "close": [93.9 + i for i in range(n_days)],
            "volume": [1_000_000 + i * 1000 for i in range(n_days)],
        }
    )


def test_normalize_ohlcv_maps_columns_and_adds_symbol():
    out = market_ohlcv.normalize_ohlcv(_sample_raw_df(), "FPT")
    assert list(out.columns) == market_ohlcv.OHLCV_COLUMNS
    assert (out["symbol"] == "FPT").all()
    assert len(out) == 5


def test_normalize_ohlcv_raises_clearly_on_schema_drift():
    # Simulate the real API returning different column names than assumed --
    # this must fail loudly with an actionable message, not silently misread.
    drifted = _sample_raw_df().rename(columns={"time": "trade_date_totally_different"})
    with pytest.raises(ValueError, match="Could not find a source column for 'date'"):
        market_ohlcv.normalize_ohlcv(drifted, "FPT")


def test_normalize_ohlcv_rejects_empty_fetch():
    with pytest.raises(EmptyResultError):
        market_ohlcv.normalize_ohlcv(pd.DataFrame(), "FPT")


def test_normalize_ohlcv_raises_on_duplicate_symbol_date():
    dupe_raw = pd.concat([_sample_raw_df(1), _sample_raw_df(1)])
    with pytest.raises(ValueError, match="duplicate"):
        market_ohlcv.normalize_ohlcv(dupe_raw, "FPT")


def test_write_ohlcv_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = market_ohlcv.normalize_ohlcv(_sample_raw_df(), "FPT")

    n1 = market_ohlcv.write_ohlcv(normalized, con)
    n2 = market_ohlcv.write_ohlcv(normalized, con)  # re-run, same input
    assert n1 == n2 == 5

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.market_ohlcv_daily WHERE symbol = 'FPT'"
    ).fetchone()[0]
    assert row_count == 5  # not doubled by the second write


def test_write_ohlcv_only_touches_promoted_symbols(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    fpt = market_ohlcv.normalize_ohlcv(_sample_raw_df(3), "FPT")
    vnm = market_ohlcv.normalize_ohlcv(_sample_raw_df(3), "VNM")

    market_ohlcv.write_ohlcv(fpt, con)
    market_ohlcv.write_ohlcv(vnm, con)

    fpt_count = con.execute(
        "SELECT COUNT(*) FROM core.market_ohlcv_daily WHERE symbol = 'FPT'"
    ).fetchone()[0]
    vnm_count = con.execute(
        "SELECT COUNT(*) FROM core.market_ohlcv_daily WHERE symbol = 'VNM'"
    ).fetchone()[0]
    assert fpt_count == 3
    assert vnm_count == 3


def test_write_ohlcv_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        market_ohlcv.write_ohlcv(bad_df, con)