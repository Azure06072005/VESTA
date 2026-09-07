"""Tests for the 2026-09-06 source-column fix to fundamentals.py's
get_as_reported()/get_as_of(). Uses synthetic duckdb fixtures matching
the REAL two-schema situation found in production: vnstock_data rows use
BS_*/IS_*/CF_*/RT_* keys, cafef rows use Vietnamese line-item strings.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.fundamentals import get_as_of, get_as_reported


@pytest.fixture()
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA core")
    c.execute(
        """
        CREATE TABLE core.fundamentals (
            symbol VARCHAR, report_type VARCHAR, period_end DATE,
            available_at DATE, data_json VARCHAR, fetched_at TIMESTAMP,
            source VARCHAR
        )
        """
    )
    yield c
    c.close()


def _insert(con, symbol, report_type, period_end, available_at, data, fetched_at, source):
    con.execute(
        "INSERT INTO core.fundamentals VALUES (?, ?, ?, ?, ?, ?, ?)",
        [symbol, report_type, period_end, available_at, json.dumps(data), fetched_at, source],
    )


def test_get_as_reported_ignores_source_uses_chronological_order_only(con):
    """The real bug this guards against: source preference must NOT
    override 'first observed' -- even if cafef is the preferred/default
    source elsewhere, get_as_reported() must return whichever row was
    genuinely fetched first, or it silently reintroduces look-ahead bias.
    """
    _insert(con, "FPT", "income_statement", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"note": "cafef, fetched first"}, dt.datetime(2026, 8, 1), "cafef")
    _insert(con, "FPT", "income_statement", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"IS_NET_REVENUE": 123}, dt.datetime(2026, 9, 6), "vnstock_data")

    df = get_as_reported(con, "FPT", "income_statement")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["source"] == "cafef"  # earliest fetched_at wins, regardless of source
    assert json.loads(row["data_json"]) == {"note": "cafef, fetched first"}


def test_get_as_of_prefers_vnstock_data_when_both_available(con):
    _insert(con, "FPT", "income_statement", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"raw": "vietnamese keys"}, dt.datetime(2026, 8, 1), "cafef")
    _insert(con, "FPT", "income_statement", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"IS_NET_REVENUE": 123}, dt.datetime(2026, 8, 2), "vnstock_data")

    df = get_as_of(con, "FPT", "income_statement", dt.date(2026, 9, 1))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["source"] == "vnstock_data"
    assert json.loads(row["data_json"]) == {"IS_NET_REVENUE": 123}


def test_get_as_of_falls_back_to_cafef_when_vnstock_data_absent(con):
    """The real case that matters for OTC/unlisted symbols: no
    vnstock_data row exists at all -- must not return empty just because
    the preferred source has nothing.
    """
    _insert(con, "SOMEOTC", "balance_sheet", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"1. Tài sản ngắn hạn": 999}, dt.datetime(2026, 9, 6), "cafef")

    df = get_as_of(con, "SOMEOTC", "balance_sheet", dt.date(2026, 9, 10))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["source"] == "cafef"
    assert json.loads(row["data_json"]) == {"1. Tài sản ngắn hạn": 999}


def test_get_as_of_respects_explicit_preferred_source_override(con):
    _insert(con, "FPT", "ratio", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"RT_VALUE_PE": 11.9}, dt.datetime(2026, 8, 1), "vnstock_data")
    _insert(con, "FPT", "ratio", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"PE raw": 11.9}, dt.datetime(2026, 9, 6), "cafef")

    df = get_as_of(con, "FPT", "ratio", dt.date(2026, 9, 10), preferred_source="cafef")
    assert df.iloc[0]["source"] == "cafef"


def test_get_as_of_still_respects_availability_gate(con):
    """Unchanged core guarantee: a row isn't returned just because it was
    fetched -- available_at must also have passed as of the query date.
    """
    _insert(con, "FPT", "income_statement", dt.date(2026, 6, 30), dt.date(2026, 7, 30),
            {"IS_NET_REVENUE": 123}, dt.datetime(2026, 7, 1), "vnstock_data")

    df = get_as_of(con, "FPT", "income_statement", dt.date(2026, 7, 15))
    assert len(df) == 0  # available_at (7/30) hasn't passed yet as of 7/15