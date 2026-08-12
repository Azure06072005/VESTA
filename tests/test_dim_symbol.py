"""F001 verification.

build_dim_symbol/write_dim_symbol are pure/DB-only and tested here without
network access. fetch_raw() (the live vnstock call) is NOT covered by these
tests -- this sandbox cannot reach vnstock's API domain. Run
discover_vnstock_schema.py against a real key to confirm fetch_raw() still
matches the schema these tests assume.
"""
from __future__ import annotations

import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from crawlers import dim_symbol  # noqa: E402


def _sample_exchange_df() -> pd.DataFrame:
    # Shape confirmed live 2026-08-11 against vnstock==4.0.5.
    return pd.DataFrame(
        {
            "symbol": ["FPT", "VNM", "DPP"],
            "organ_name": ["CTCP FPT", "CTCP Vinamilk", "CTCP Dược Đồng Nai"],
            "en_organ_name": ["FPT Corp", "Vinamilk JSC", "Dong Nai Pharma JSC"],
            "exchange": ["HOSE", "HOSE", "UPCOM"],
            "type": ["stock", "stock", "stock"],
            "id": [1, 2, 3],
        }
    )


def _sample_industry_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["FPT", "VNM"],  # DPP intentionally missing -> left-join null
            "industry_code": ["11", "22"],
            "industry_name": ["Công nghệ thông tin", "Thực phẩm"],
        }
    )


def test_build_dim_symbol_joins_on_symbol():
    out = dim_symbol.build_dim_symbol(_sample_exchange_df(), _sample_industry_df())
    assert list(out.columns) == dim_symbol.DIM_SYMBOL_COLUMNS
    assert len(out) == 3
    fpt_row = out[out["symbol"] == "FPT"].iloc[0]
    assert fpt_row["industry_name"] == "Công nghệ thông tin"


def test_build_dim_symbol_left_join_keeps_unmatched_symbol_with_null_industry():
    out = dim_symbol.build_dim_symbol(_sample_exchange_df(), _sample_industry_df())
    dpp_row = out[out["symbol"] == "DPP"].iloc[0]
    assert pd.isna(dpp_row["industry_code"])


def test_build_dim_symbol_rejects_missing_required_column():
    bad_df = _sample_exchange_df().drop(columns=["symbol"])
    with pytest.raises(ValueError, match="missing required column"):
        dim_symbol.build_dim_symbol(bad_df, _sample_industry_df())


def test_build_dim_symbol_raises_on_duplicate_symbols():
    dupe_df = pd.concat([_sample_exchange_df(), _sample_exchange_df().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate symbol"):
        dim_symbol.build_dim_symbol(dupe_df, _sample_industry_df())


def test_write_dim_symbol_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    out = dim_symbol.build_dim_symbol(_sample_exchange_df(), _sample_industry_df())

    n1 = dim_symbol.write_dim_symbol(out, con)
    n2 = dim_symbol.write_dim_symbol(out, con)  # re-run, same input
    assert n1 == n2 == 3

    row_count = con.execute("SELECT COUNT(*) FROM core.dim_symbol").fetchone()[0]
    assert row_count == 3  # not doubled by the second write


def test_write_dim_symbol_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        dim_symbol.write_dim_symbol(bad_df, con)


@pytest.mark.xfail(
    reason=(
        "KNOWN GAP (2026-08-11): vnstock's unified API does not expose "
        "delisted symbols. As formally accepted in DECISIONS.md, we are "
        "deferring the creation of a fragile web scraper until F201 "
        "validation proves that survivorship bias artificially inflates "
        "our backtest. This test retains its xfail status to explicitly "
        "track this accepted limitation -- do not delete it to make F001 "
        "look perfectly resolved."
    ),
    strict=True,
)
def test_delisted_symbol_has_non_null_delisted_date():
    out = dim_symbol.build_dim_symbol(_sample_exchange_df(), _sample_industry_df())
    # No delisted symbols exist in the current data source at all, so this
    # assertion is unsatisfiable today -- that's the point of the xfail.
    assert out["delisted_date"].notna().any()