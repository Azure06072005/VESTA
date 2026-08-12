"""F005 verification.

normalize_statement/write_statements are pure/DB-only and tested here
without network access. fetch_raw() (the live vnstock call) is NOT covered
-- this sandbox cannot reach vnstock's API domain. Run
discover_fundamentals_schema.py against a real key to confirm
PERIOD_END_ALIASES and the DISCLOSURE_LAG_DAYS assumption in
src/crawlers/fundamentals.py.
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


def _sample_income_statement_df() -> pd.DataFrame:
    # UNCONFIRMED column names -- see fundamentals.py module docstring.
    return pd.DataFrame(
        {
            "period_end": ["2025-12-31", "2025-09-30"],
            "revenue": [12000.5, 11500.2],
            "net_profit": [1800.1, 1700.3],
        }
    )


def test_normalize_statement_computes_available_at_from_lag():
    out = fundamentals.normalize_statement(_sample_income_statement_df(), "FPT", "income_statement")
    assert list(out.columns) == fundamentals.FUNDAMENTAL_COLUMNS
    row = out.iloc[0]
    expected_lag_days = fundamentals.DISCLOSURE_LAG_DAYS
    assert (row["available_at"] - row["period_end"]).days == expected_lag_days


def test_normalize_statement_preserves_full_row_as_json():
    out = fundamentals.normalize_statement(_sample_income_statement_df(), "FPT", "income_statement")
    parsed = json.loads(out.iloc[0]["data_json"])
    assert parsed["revenue"] == 12000.5
    assert parsed["net_profit"] == 1800.1


def test_normalize_statement_raises_clearly_on_missing_period_column():
    drifted = _sample_income_statement_df().rename(columns={"period_end": "totally_different_col"})
    with pytest.raises(ValueError, match="Could not find a period-end column"):
        fundamentals.normalize_statement(drifted, "FPT", "income_statement")


def test_balance_sheet_empty_response_fails_loudly():
    """FORMALLY ACCEPTED (2026-08-12, see DECISIONS.md): balance_sheet()
    returns a completely empty DataFrame live. This is treated as a real
    vnstock API gap, not a bug in this crawler. The correct behavior is
    to keep failing loudly (never silently substitute/skip), which is
    what this asserts -- do not "fix" this by catching the error and
    returning an empty result.
    """
    with pytest.raises(ValueError, match="empty DataFrame"):
        fundamentals.normalize_statement(pd.DataFrame(), "FPT", "balance_sheet")


def test_normalize_statement_raises_on_duplicate_period():
    dupe = pd.concat([_sample_income_statement_df().iloc[[0]], _sample_income_statement_df().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate"):
        fundamentals.normalize_statement(dupe, "FPT", "income_statement")


def test_fetch_raw_rejects_unknown_report_type():
    with pytest.raises(ValueError, match="Unknown report_type"):
        fundamentals.fetch_raw("FPT", "not_a_real_type")


def test_write_statements_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = fundamentals.normalize_statement(_sample_income_statement_df(), "FPT", "income_statement")

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
    income = fundamentals.normalize_statement(_sample_income_statement_df(), "FPT", "income_statement")
    ratio = fundamentals.normalize_statement(
        pd.DataFrame({"period_end": ["2025-12-31"], "pe": [15.2]}), "FPT", "ratio"
    )

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