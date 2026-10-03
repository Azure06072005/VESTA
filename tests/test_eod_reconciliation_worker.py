"""tests/test_eod_reconciliation_worker.py

Unit test suite for Feature F402 & F403: EOD Reconciliation & Continuous Retraining Worker.
Verifies automated post-market reconciliation, model drift telemetry, and continuous retraining dispatch.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import sys
from typing import Dict

import duckdb
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service.eod_reconciliation_worker import EODExecutionSummary, EODReconciliationWorker
from service.feedback_log import DDL_FEEDBACK_SCHEMA


@pytest.fixture
def temp_eod_env(tmp_path: pathlib.Path) -> Dict[str, str]:
    """Sets up a temporary DuckDB database with mock schema, predictions, and OHLCV prices."""
    db_file = str(tmp_path / "test_eod.duckdb")

    con = duckdb.connect(db_file)
    con.execute(DDL_FEEDBACK_SCHEMA)

    # Create mock core.market_ohlcv_daily
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
            symbol VARCHAR NOT NULL,
            date DATE NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE NOT NULL,
            volume DOUBLE NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)

    # Populate 10 consecutive trading days for VNM
    dates = [
        datetime.date(2026, 9, 1) + datetime.timedelta(days=i)
        for i in range(15)
        if (datetime.date(2026, 9, 1) + datetime.timedelta(days=i)).weekday() < 5
    ]
    base_price = 80.0
    for i, d in enumerate(dates):
        price = base_price * (1.0 + 0.01 * i)
        con.execute(
            """
            INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume)
            VALUES ('VNM', ?, ?, ?, ?, ?, 1000000.0)
            """,
            (d, price, price + 0.5, price - 0.5, price),
        )

    # Insert mock predictions
    t0_date = dates[0]
    t0_time = datetime.datetime.combine(t0_date, datetime.time(9, 30))
    for idx in range(5):
        con.execute(
            """
            INSERT INTO meta.prediction_feedback_log (
                prediction_id, created_at, symbol, headline, source, source_trust_weight,
                raw_sentiment_score, consistent_alpha_score, sentiment_class,
                p_star_neg, p_star_neu, p_star_pos, violation_score, is_consistent,
                is_duplicate, action_recommendation, regime_safe_to_trade,
                event_date, is_backfilled
            ) VALUES (?, ?, 'VNM', 'VNM doanh thu quý tăng trưởng tốt', 'CafeF', 0.85,
                      65.0, 70.0, 'POSITIVE', 0.1, 0.2, 0.7, 0.02, TRUE,
                      FALSE, 'HOLD', TRUE, ?, FALSE)
            """,
            (f"pred-eod-{idx}", t0_time, t0_date),
        )

    con.close()

    return {"db_path": db_file}


def test_eod_worker_initialization(temp_eod_env: Dict[str, str]):
    """Verifies that EODReconciliationWorker initializes correctly with DuckDB."""
    worker = EODReconciliationWorker(db_path=temp_eod_env["db_path"])
    assert worker.db_path == temp_eod_env["db_path"]
    assert worker.reconciler is not None
    assert worker.drift_monitor is not None
    assert worker.ct_orchestrator is not None


def test_eod_worker_dry_run(temp_eod_env: Dict[str, str]):
    """Verifies that dry-run mode reconciles and audits without triggering model retraining."""
    worker = EODReconciliationWorker(db_path=temp_eod_env["db_path"])
    summary: EODExecutionSummary = worker.run_eod_cycle(dry_run=True)

    assert summary.execution_id.startswith("eod_")
    assert summary.reconciliation_stats is not None
    assert summary.retraining_dispatched is False
    assert summary.system_status in ("HEALTHY", "DEGRADED")
    assert "EOD Cycle complete" in summary.message


def test_eod_worker_reconciliation_cycle(temp_eod_env: Dict[str, str]):
    """Verifies that EOD cycle back-fills prices and computes realized forward returns."""
    worker = EODReconciliationWorker(db_path=temp_eod_env["db_path"])
    summary = worker.run_eod_cycle(dry_run=False)

    con = duckdb.connect(temp_eod_env["db_path"])
    rows = con.execute("""
        SELECT prediction_id, realized_price_t0, realized_price_t1, return_t1, is_backfilled
        FROM meta.prediction_feedback_log
    """).fetchall()
    con.close()

    assert len(rows) == 5
    for r in rows:
        assert r[1] is not None  # realized_price_t0
        assert r[2] is not None  # realized_price_t1
        assert r[3] is not None  # return_t1


def test_strictly_read_only_compliance():
    """Confirms EOD worker contains strictly NO broker execution or order placement logic (Rule B1)."""
    worker_file = REPO_ROOT / "src" / "service" / "eod_reconciliation_worker.py"
    with open(worker_file, "r", encoding="utf-8") as f:
        code = f.read()

    forbidden_tokens = [
        "place_order",
        "submit_order",
        "broker.buy",
        "broker.sell",
        "fix_client",
        "dnse_token",
        "ssi_secret",
        "order_stream",
    ]
    for token in forbidden_tokens:
        assert token not in code.lower(), f"Security violation: Found forbidden trading token '{token}' in EOD worker!"
