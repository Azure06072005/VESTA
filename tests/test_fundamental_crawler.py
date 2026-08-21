"""F005 verification.

melt_pivoted_statement/write_statements are pure/DB-only and tested here
without network access. fetch_raw() (the live vnstock call) is NOT covered
-- this sandbox cannot reach vnstock's API domain. Fixtures below match
the pivoted shape confirmed live 2026-08-12: rows are financial line
items, columns after the id column are period labels ('YYYY-Qn' or
'YYYY').
"""
from __future__ import annotations

import datetime as dt
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


def test_write_statements_is_idempotent_on_unchanged_data(tmp_path):
    # APPEND-ONLY semantics (fixed 2026-08-16): a re-crawl with identical
    # data is a no-op -- returns 0 written, row count stays the same. This
    # replaces the old DELETE+INSERT idempotency test, since "idempotent"
    # now means "correctly detects nothing changed", not "same count both
    # times" (see get_as_reported/get_as_of tests below for the revision
    # case, where counts SHOULD differ).
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")

    n1 = fundamentals.write_statements(normalized, con)
    n2 = fundamentals.write_statements(normalized, con)  # re-run, identical data
    assert n1 == 2
    assert n2 == 0  # nothing changed -- correctly skipped, not reinserted

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE symbol = 'FPT' AND report_type = 'income_statement'"
    ).fetchone()[0]
    assert row_count == 2  # not doubled


def test_write_statements_appends_revision_when_data_changes(tmp_path):
    # THE ACTUAL BUG FIX (2026-08-16, DECISIONS.md F009 item 3): a
    # restated period must be recorded as an ADDITIONAL row, not silently
    # overwrite the original -- otherwise a backtest querying "what was
    # known as of date X" would see the revised figure even for dates
    # before the revision happened (look-ahead bias).
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    original = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    fundamentals.write_statements(original, con)

    # Simulate a restatement: same periods, one value revised.
    restated_raw = _sample_pivoted_df().copy()
    restated_raw.loc[restated_raw["item_id"] == "revenue", "2026-Q1"] = 99999.9
    restated = fundamentals.melt_pivoted_statement(restated_raw, "FPT", "income_statement")

    n2 = fundamentals.write_statements(restated, con)
    assert n2 == 1  # only the changed period_end got a new revision row

    total_rows = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE symbol = 'FPT' AND report_type = 'income_statement'"
    ).fetchone()[0]
    assert total_rows == 3  # 2 original periods + 1 new revision -- original NOT deleted


def test_get_as_reported_returns_first_seen_vintage_not_the_revision(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    original = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    fundamentals.write_statements(original, con)

    restated_raw = _sample_pivoted_df().copy()
    restated_raw.loc[restated_raw["item_id"] == "revenue", "2026-Q1"] = 99999.9
    restated = fundamentals.melt_pivoted_statement(restated_raw, "FPT", "income_statement")
    fundamentals.write_statements(restated, con)

    as_reported = fundamentals.get_as_reported(con, "FPT", "income_statement")
    q1_row = as_reported[as_reported["period_end"].astype(str) == "2026-03-31"].iloc[0]
    metrics = json.loads(q1_row["data_json"])
    assert metrics["revenue"] == 12000.5  # the ORIGINAL value, not 99999.9


def test_get_as_of_surfaces_revision_once_both_observed_and_disclosed(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    original = fundamentals.melt_pivoted_statement(_sample_pivoted_df(), "FPT", "income_statement")
    fundamentals.write_statements(original, con)

    restated_raw = _sample_pivoted_df().copy()
    restated_raw.loc[restated_raw["item_id"] == "revenue", "2026-Q1"] = 99999.9
    restated = fundamentals.melt_pivoted_statement(restated_raw, "FPT", "income_statement")
    fundamentals.write_statements(restated, con)

    far_future = dt.date(2099, 1, 1)
    as_of = fundamentals.get_as_of(con, "FPT", "income_statement", far_future)
    q1_row = as_of[as_of["period_end"].astype(str) == "2026-03-31"].iloc[0]
    metrics = json.loads(q1_row["data_json"])
    assert metrics["revenue"] == 99999.9  # the revision, since it's now fully in the past


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


def test_run_with_report_type_all_aggregates_across_report_types(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    con = db.bootstrap_schema(db_path)
    monkeypatch.setattr(fundamentals.db, "bootstrap_schema", lambda *a, **kw: con)

    call_log: list[str] = []

    def fake_fetch_raw(symbol: str, report_type: str, period: str = "quarter") -> pd.DataFrame:
        call_log.append(report_type)
        if report_type == "balance_sheet":
            return pd.DataFrame()
        return _sample_pivoted_df()

    monkeypatch.setattr(fundamentals, "fetch_raw", fake_fetch_raw)

    total = fundamentals.run("FPT")

    assert set(call_log) == set(fundamentals.REPORT_TYPES)
    assert total > 0

    written_types = {
        r[0]
        for r in con.execute("SELECT DISTINCT report_type FROM core.fundamentals WHERE symbol = 'FPT'").fetchall()
    }
    assert written_types == {"income_statement", "cash_flow", "ratio"}


def test_run_with_report_type_all_raises_only_if_every_type_is_empty(tmp_path, monkeypatch):
    from etl.retry_failed_jobs import EmptyResultError

    db_path = tmp_path / "test.duckdb"
    con = db.bootstrap_schema(db_path)
    monkeypatch.setattr(fundamentals.db, "bootstrap_schema", lambda *a, **kw: con)

    def always_empty_fetch(symbol: str, report_type: str, period: str = "quarter") -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr(fundamentals, "fetch_raw", always_empty_fetch)

    with pytest.raises(EmptyResultError):
        fundamentals.run("DELISTED_SYMBOL")