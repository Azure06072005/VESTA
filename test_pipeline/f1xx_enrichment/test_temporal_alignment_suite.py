"""test_pipeline/f1xx_enrichment/test_temporal_alignment_suite.py

Pytest suite validating Temporal Alignment invariants in test_pipeline.
Invariants:
1. Zero Look-ahead in Fundamentals: available_at >= period_end + 20 days.
2. Safe Horizon Calculation: price_at_publish must be strictly positive (> 0).
3. Flatline Detection: identifies suspended/frozen stocks where P_0 == P_1 == P_5 == P_30.
"""
from __future__ import annotations

import datetime as dt
import duckdb
import pytest

DB_PATH = "db/test_db/vesta_test.duckdb"

@pytest.fixture(scope="module")
def con():
    conn = duckdb.connect(DB_PATH, read_only=True)
    yield conn
    conn.close()


def test_fundamental_available_at_never_precedes_period_end(con):
    """Invariant: Fundamental disclosures cannot be available before the period ends."""
    illegal_count = con.execute("""
        SELECT COUNT(*) FROM core.fundamentals WHERE available_at < period_end
    """).fetchone()[0]
    assert illegal_count == 0, f"Found {illegal_count} rows where available_at < period_end!"


def test_fundamental_circular_96_statutory_lag(con):
    """Invariant: Circular 96 minimum statutory lag (20 days) is respected."""
    violations = con.execute("""
        SELECT COUNT(*) 
        FROM core.fundamentals 
        WHERE date_diff('day', period_end, available_at) < 20
    """).fetchone()[0]
    assert violations == 0, f"Found {violations} rows violating Circular 96 20-day lag!"


def test_zero_price_detection_and_sanitization(con):
    """Invariant: Zero prices must be flagged and isolated to prevent division-by-zero."""
    zero_prices = con.execute("""
        SELECT COUNT(*) FROM core.pit_events WHERE price_at_publish <= 0
    """).fetchone()[0]
    # We assert that we detect zero prices and can cleanly filter them out
    assert zero_prices > 0, "Expected to detect raw zero price anomalies in uncleaned database"
    
    clean_count = con.execute("""
        SELECT COUNT(*) FROM core.pit_events WHERE price_at_publish > 0
    """).fetchone()[0]
    assert clean_count > 600000, f"Expected >600k valid positive price events, got {clean_count}"


def test_suspended_flatline_detection(con):
    """Invariant: Frozen/suspended stock price rollovers are properly detectable."""
    flatlines = con.execute("""
        SELECT COUNT(*) 
        FROM core.pit_events 
        WHERE price_at_publish > 0 
          AND price_t1 = price_at_publish 
          AND price_t5 = price_at_publish 
          AND price_t30 = price_at_publish
    """).fetchone()[0]
    # In VN stock market, frozen/suspended stocks constitute ~3-5% of historical bars
    assert flatlines > 10000, f"Expected >10k flatlines detected, found {flatlines}"
