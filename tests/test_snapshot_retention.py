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
    # CONFIRMED live shape 2026-08-14 (real pasted output): MultiIndex
    # (category, field) columns, trimmed to a representative subset of
    # the real 82.
    columns = pd.MultiIndex.from_tuples(
        [
            ("listing", "symbol"),
            ("listing", "ceiling"),
            ("listing", "floor"),
            ("match", "match_price"),
            ("match", "foreign_buy_volume"),
            ("bid_ask", "bid_1_price"),
        ]
    )
    return pd.DataFrame(
        [
            ["FPT", 74000, 64400, 69200, 15000, 69100],
            ["VNM", 68000, 59000, 62100, 8000, 62000],
        ],
        columns=columns,
    )


def _sample_flat_df() -> pd.DataFrame:
    # A flat (non-MultiIndex) fallback shape -- for testing the alias
    # path stays robust even if a future response isn't MultiIndex.
    return pd.DataFrame({"symbol": ["FPT"], "match_price": [93.9]})


def test_normalize_snapshot_produces_one_row_per_symbol():
    out = snapshots.normalize_snapshot(_sample_price_board_df())
    assert list(out.columns) == snapshots.SNAPSHOT_COLUMNS
    assert len(out) == 2
    assert set(out["symbol"]) == {"FPT", "VNM"}


def test_normalize_snapshot_flattens_multiindex_and_preserves_full_row_as_json():
    out = snapshots.normalize_snapshot(_sample_price_board_df())
    fpt_row = out[out["symbol"] == "FPT"].iloc[0]
    parsed = json.loads(fpt_row["data_json"])
    # Flattened keys use 'category_field' naming (confirmed live 2026-08-14).
    assert parsed["match_match_price"] == 69200
    assert parsed["match_foreign_buy_volume"] == 15000
    assert parsed["bid_ask_bid_1_price"] == 69100
    assert parsed["listing_ceiling"] == 74000


def test_normalize_snapshot_accepts_flat_symbol_column_alias():
    out = snapshots.normalize_snapshot(_sample_flat_df())
    assert out.iloc[0]["symbol"] == "FPT"
    parsed = json.loads(out.iloc[0]["data_json"])
    assert parsed["match_price"] == 93.9


def test_normalize_snapshot_raises_clearly_on_missing_symbol_column():
    no_symbol_df = pd.DataFrame({"match_price": [93.9]})
    with pytest.raises(ValueError, match="Could not find a symbol column"):
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


def test_run_accepts_a_single_string_symbol(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    con = db.bootstrap_schema(db_path)
    monkeypatch.setattr(snapshots.db, "bootstrap_schema", lambda *a, **kw: con)

    captured: dict[str, list[str]] = {}

    def fake_fetch_raw(symbols: list[str]) -> pd.DataFrame:
        captured["symbols"] = symbols
        return _sample_price_board_df()

    monkeypatch.setattr(snapshots, "fetch_raw", fake_fetch_raw)

    n = snapshots.run("FPT")
    assert captured["symbols"] == ["FPT"]
    assert n == 2


def test_fetch_raw_vietcap_mock(monkeypatch):
    sample_api_response = [
        {
            "listingInfo": {"code": "VN000000FPT1", "symbol": "FPT", "refPrice": 65300, "ceiling": 69800, "floor": 60800},
            "matchPrice": {"matchPrice": 64700, "accumulatedVolume": 3543900, "foreignBuyVolume": 228305, "foreignSellVolume": 551080},
            "bidAsk": {
                "bidPrices": [{"price": 64700, "volume": 120700}],
                "askPrices": [{"price": 64800, "volume": 27500}],
            },
        }
    ]

    class FakeResponse:
        def read(self):
            return json.dumps(sample_api_response).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(snapshots.urllib.request, "urlopen", lambda *a, **kw: FakeResponse())

    df = snapshots.fetch_raw_vietcap(["FPT"])
    assert isinstance(df.columns, pd.MultiIndex)
    assert ("listing", "symbol") in df.columns
    assert df[("listing", "symbol")].iloc[0] == "FPT"
    assert df[("match", "match_price")].iloc[0] == 64700
    assert df[("bid_ask", "bid_1_price")].iloc[0] == 64700


def test_fetch_raw_cafef_fallback_mock(monkeypatch):
    sample_cafef = {
        "FPT": {
            "Symbol": "FPT",
            "Price": 64.7,
            "RefPrice": 65.3,
            "CeilingPrice": 69.8,
            "FloorPrice": 60.8,
            "Volume": 3500000,
            "BidPrice01": 64.5,
            "BidVolume01": 300000,
            "AskPrice01": 65.0,
            "AskVolume01": 15000,
            "ForeignBuyVolume": 200000,
            "ForeignSellVolume": 500000,
        }
    }

    class FakeResponse:
        def read(self):
            return json.dumps(sample_cafef).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(snapshots.urllib.request, "urlopen", lambda *a, **kw: FakeResponse())

    df = snapshots.fetch_raw_cafef(["FPT"])
    assert isinstance(df.columns, pd.MultiIndex)
    assert ("listing", "symbol") in df.columns
    assert df[("listing", "symbol")].iloc[0] == "FPT"
    assert df[("match", "match_price")].iloc[0] == 64700.0


def test_fetch_valuation_snapshot_mock(monkeypatch):
    sample_indicators = {
        "Data": [
            {"Code": "EPScoBan", "Value": "5.87"},
            {"Code": "P/E", "Value": "11.03"},
            {"Code": "Beta", "Value": "2.97"},
            {"Code": "VonHoaThiTruong", "Value": "122,008.61"},
        ]
    }

    class FakeResponse:
        def read(self):
            return json.dumps(sample_indicators).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(snapshots.urllib.request, "urlopen", lambda *a, **kw: FakeResponse())

    val = snapshots.fetch_valuation_snapshot("FPT")
    assert val["symbol"] == "FPT"
    assert val["EPScoBan"] == "5.87"
    assert val["P/E"] == "11.03"
    assert val["VonHoaThiTruong"] == "122,008.61"