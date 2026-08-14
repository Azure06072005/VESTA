"""F007 verification (shrunk scope: realtime quote snapshot only).

normalize_snapshot/write_snapshot are pure/DB-only and tested here without
network access. fetch_raw() (the live vnstock call) is NOT covered --
this sandbox cannot reach vnstock's API domain. Run
discover_price_board_schema.py against a real key to confirm the real
column shape assumed in normalize_snapshot().
"""
from __future__ import annotations

import json
import sys
import pathlib
import time

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402
from crawlers import snapshots  # noqa: E402


def _sample_price_board_df() -> pd.DataFrame:
    # UNCONFIRMED column names -- see snapshots.py module docstring.
    return pd.DataFrame(
        {
            "symbol": ["FPT", "VNM"],
            "match_price": [93.9, 62.1],
            "volume": [1714500, 980200],
        }
    )


def test_normalize_snapshot_produces_one_row_per_symbol():
    out = snapshots.normalize_snapshot(_sample_price_board_df())
    assert list(out.columns) == snapshots.SNAPSHOT_COLUMNS
    assert len(out) == 2
    assert set(out["symbol"]) == {"FPT", "VNM"}


def test_normalize_snapshot_preserves_full_row_as_json():
    out = snapshots.normalize_snapshot(_sample_price_board_df())
    fpt_row = out[out["symbol"] == "FPT"].iloc[0]
    parsed = json.loads(fpt_row["data_json"])
    assert parsed["match_price"] == 93.9
    assert parsed["volume"] == 1714500


def test_normalize_snapshot_accepts_ticker_column_alias():
    ticker_df = pd.DataFrame({"ticker": ["FPT"], "match_price": [93.9]})
    out = snapshots.normalize_snapshot(ticker_df)
    assert out.iloc[0]["symbol"] == "FPT"


def test_normalize_snapshot_raises_clearly_on_missing_symbol_column():
    no_symbol_df = pd.DataFrame({"match_price": [93.9]})
    with pytest.raises(ValueError, match="Could not find a 'symbol' or 'ticker' column"):
        snapshots.normalize_snapshot(no_symbol_df)


def test_normalize_snapshot_raises_empty_result_error_on_empty_fetch():
    with pytest.raises(EmptyResultError):
        snapshots.normalize_snapshot(pd.DataFrame())


def test_write_snapshot_accumulates_across_separate_fetches(tmp_path):
    # ACCUMULATE retention policy (DECISIONS.md 2026-08-14): two distinct
    # snapshots for the same symbol must both be kept, not overwritten.
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)

    first = snapshots.normalize_snapshot(_sample_price_board_df())
    n1 = snapshots.write_snapshot(first, con)
    time.sleep(0.01)  # ensure a distinct snapshot_at timestamp
    second = snapshots.normalize_snapshot(_sample_price_board_df())
    n2 = snapshots.write_snapshot(second, con)

    assert n1 == n2 == 2
    row_count = con.execute(
        "SELECT COUNT(*) FROM core.realtime_quote_snapshot WHERE symbol = 'FPT'"
    ).fetchone()[0]
    assert row_count == 2  # both snapshots retained, not deduped away


def test_write_snapshot_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        snapshots.write_snapshot(bad_df, con)