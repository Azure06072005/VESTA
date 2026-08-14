"""F005 verification.

melt_pivoted_statement/write_statements are pure/DB-only and tested here
without network access. fetch_raw() (the live vnstock call) is NOT covered
-- this sandbox cannot reach vnstock's API domain. Fixtures below match
the pivoted shape confirmed live 2026-08-12: rows are financial line
items, columns after the id column are period labels ('YYYY-Qn' or
'YYYY').
"""
from __future__ import annotations

import json
import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from crawlers import fundamentals  # noqa: E402


def _sample_pivoted_df() -> pd.DataFrame:
    # Confirmed live shape 2026-08-12: id column ('item_id') + period
    # label columns. Exact id column name is a best guess among
    # ID_COLUMN_CANDIDATES -- see module docstring.
    return pd.DataFrame(
        {
            "item_id": ["revenue", "net_profit"],
            "2026-Q1": [12000.5, 1800.1],
            "2025-Q4": [11500.2, 1700.3],
        }
    )


def test_melt_pivoted_statement_produces_one_row_per_period():
    out = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    assert list(out.columns) == fundamentals.FUNDAMENTAL_COLUMNS
    assert len(out) == 2  # two period columns -> two period rows
    periods = sorted(out["period_end"].tolist())
    assert periods[0].isoformat() == "2025-12-31"  # 2025-Q4 end
    assert periods[1].isoformat() == "2026-03-31"  # 2026-Q1 end


def test_melt_pivoted_statement_packs_metrics_into_json():
    out = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    q1_row = out[out["period_end"].astype(str) == "2026-03-31"].iloc[0]
    metrics = json.loads(q1_row["data_json"])
    assert metrics["revenue"] == 12000.5
    assert metrics["net_profit"] == 1800.1


def test_melt_pivoted_statement_handles_bare_year_columns():
    yearly = pd.DataFrame({"item_id": ["revenue"], "2025": [50000.0], "2024": [45000.0]})
    out = fundamentals.melt_pivoted_statement(yearly, "FPT", "income_statement")
    periods = sorted(p.isoformat() for p in out["period_end"])
    assert periods == ["2024-12-31", "2025-12-31"]


def test_melt_pivoted_statement_computes_available_at_from_lag():
    out = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    row = out.iloc[0]
    assert (row["available_at"] - row["period_end"]).days == fundamentals.DISCLOSURE_LAG_DAYS


def test_melt_pivoted_statement_raises_clearly_when_no_period_columns():
    no_periods = pd.DataFrame({"item_id": ["revenue"], "notes": ["some text"]})
    with pytest.raises(ValueError, match="No period-label columns"):
        fundamentals.melt_pivoted_statement(no_periods, "FPT", "income_statement")


def test_balance_sheet_empty_response_fails_loudly():
    """FORMALLY ACCEPTED (2026-08-12, see DECISIONS.md): balance_sheet()
    returns a completely empty DataFrame live. This is treated as a real
    vnstock API gap, not a bug in this crawler. The correct behavior is
    to keep failing loudly (never silently substitute/skip), which is
    what this asserts -- do not "fix" this by catching the error and
    returning an empty result.
    """
    from etl.retry_failed_jobs import EmptyResultError

    with pytest.raises(EmptyResultError):
        fundamentals.melt_pivoted_statement(pd.DataFrame(), "FPT", "balance_sheet")


def test_fetch_raw_rejects_unknown_report_type():
    with pytest.raises(ValueError, match="Unknown report_type"):
        fundamentals.fetch_raw("FPT", "not_a_real_type")


def test_write_statements_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")

    n1 = fundamentals.write_statements(normalized, con)
    n2 = fundamentals.write_statements(normalized, con)  # re-run, same input
    assert n1 == n2 == 2

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE symbol = 'FPT' AND report_type = 'income_statement'"
    ).fetchone()[0]
    assert row_count == 2  # not doubled


def test_write_statements_keeps_report_types_independent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    income = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    ratio_raw = pd.DataFrame({"item_id": ["pe"], "2025-Q4": [15.2]})
    ratio = fundamentals.melt_pivoted_statement(ratio_raw, "FPT", "ratio")

    fundamentals.write_statements(income, con)
    fundamentals.write_statements(ratio, con)

    income_count = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE report_type = 'income_statement'"
    ).fetchone()[0]
    ratio_count = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE report_type = 'ratio'"
    ).fetchone()[0]
    assert income_count == 2
    assert ratio_count == 1


def test_write_statements_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        fundamentals.write_statements(bad_df, con)