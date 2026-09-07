"""Live data-quality checks against the real vesta.duckdb.

NOT a portable unit test in the usual sense -- these assertions are only
meaningful against real, current production data, not a synthetic
fixture. Per this project's testing convention (conventions.md), that
makes this closer to a live-verification report than a CI-gate test.

FIXED 2026-09-06 (was: hardcoded absolute path "d:/VESTA/db/vesta.duckdb"
baked directly into each test body -- could only ever run on one specific
machine, and failed hard rather than skipping on any other environment).
Now:
- DB path comes from the VESTA_DB_PATH env var, defaulting to the
  project-relative db/vesta.duckdb -- works from any checkout.
- Tests SKIP (not fail) if the database file doesn't exist, since this
  genuinely requires live data that a fresh clone or CI runner won't have.
- Magic-number thresholds are loosened from exact snapshot values to
  loose sanity bounds (order-of-magnitude, not exact current counts) --
  the exact values will keep growing as crawls continue, and asserting
  today's exact number against tomorrow's larger database was always
  going to start failing for the wrong reason (growth, not breakage).
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import duckdb
import pytest

from src.crawlers.verify_market_data import verify_market_data

DB_PATH = os.environ.get("VESTA_DB_PATH", "db/vesta.duckdb")

pytestmark = pytest.mark.skipif(
    not Path(DB_PATH).exists(),
    reason=f"Live database not found at {DB_PATH!r} -- these are live data-quality "
    f"checks, not fixture-based unit tests. Set VESTA_DB_PATH to point at a real "
    f"vesta.duckdb to run them.",
)


def test_verify_market_data_execution():
    """Sanity-level checks only -- loose bounds, not exact snapshot values,
    since real crawl volume grows over time and an exact-count assertion
    would eventually fail from growth, not from a real regression.
    """
    results = verify_market_data(duckdb_path=DB_PATH)
    assert "ohlcv" in results
    assert "indices" in results
    assert "research_reports" in results
    assert "vietstock_news" in results
    assert "foreign_flow" in results

    ohlcv = results["ohlcv"]
    assert ohlcv["records"] > 1_000_000  # loose sanity bound, not an exact snapshot
    assert ohlcv["symbols"] >= 1_000
    assert ohlcv["min_date"] <= dt.date(2010, 1, 1)

    indices = {row[0]: row[1] for row in results["indices"]}
    assert "VNINDEX" in indices
    assert "HNX-INDEX" in indices

    rep = results["research_reports"]
    assert rep[0] >= 1  # at least one report loaded -- presence check, not a volume target
    assert rep[1] >= 1

    ff = results["foreign_flow"]
    assert ff[0] > 0
    assert ff[1] >= 1


def test_ohlcv_data_types_and_no_null_keys():
    """Real integrity check: no NULL primary-key components, and the
    overwhelming majority of rows have a real close price. These are
    structural checks, not volume checks, so they don't need loosening.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        null_pk = con.execute(
            "SELECT count(1) FROM core.market_ohlcv_daily WHERE symbol IS NULL OR date IS NULL"
        ).fetchone()[0]
        total = con.execute("SELECT count(1) FROM core.market_ohlcv_daily").fetchone()[0]
        valid_close = con.execute(
            "SELECT count(1) FROM core.market_ohlcv_daily WHERE close IS NOT NULL"
        ).fetchone()[0]
    finally:
        con.close()

    assert null_pk == 0
    assert total > 0, "core.market_ohlcv_daily is empty -- nothing to check"
    assert (valid_close / total) > 0.9999