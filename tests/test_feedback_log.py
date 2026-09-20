"""tests/test_feedback_log.py

Comprehensive Test Suite for Feature F402: Feedback log for scored predictions vs realized returns.
Verifies the following core invariants:
1. Schema initialization: Creates meta.prediction_feedback_log and meta.model_drift_telemetry idempotently.
2. Inference logging: Logs F401 predictions with full Kolmogorov simplex p*, alpha, and metadata.
3. Post-market reconciliation: Accurately back-fills realized prices and forward returns (T+1, T+5, T+30)
   using trading sessions from core.market_ohlcv_daily (respecting trading days over calendar days).
4. Partial reconciliation: Correctly leaves T+5 / T+30 pending when future trading bars have not yet elapsed.
5. Drift metrics mathematical accuracy: Verifies rolling Brier Score, Directional Accuracy, and Spearman IC.
6. Circuit breaker hard rail: Triggers SYSTEM_DEGRADED_HALT when directional accuracy < 35% or Brier > 0.060.
7. FastAPI endpoint integration: Verifies /api/v1/drift_status returns valid telemetry.
8. Strictly Read-Only compliance: Proves 0% broker execution logic per Rule B1.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import sys
import uuid
from typing import Generator

import duckdb
import numpy as np
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service.feedback_log import (
    DDL_FEEDBACK_SCHEMA,
    DriftMonitor,
    FeedbackReconciler,
    InferenceFeedbackLogger,
)
from service.inference_app import app, engine


@pytest.fixture
def temp_db(tmp_path: pathlib.Path) -> str:
    """Creates an isolated temporary DuckDB file for test execution."""
    db_file = str(tmp_path / "test_feedback.duckdb")
    con = duckdb.connect(db_file)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
            symbol VARCHAR NOT NULL,
            date DATE NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
        """
    )
    con.execute(DDL_FEEDBACK_SCHEMA)
    con.close()
    return db_file


# =============================================================================
# 1. SCHEMA INITIALIZATION TEST
# =============================================================================
def test_schema_initialization(temp_db: str):
    """Verifies that InferenceFeedbackLogger initializes schema idempotently."""
    logger = InferenceFeedbackLogger(db_path=temp_db)
    con = duckdb.connect(temp_db, read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'meta'").fetchall()]
    con.close()
    assert "prediction_feedback_log" in tables
    assert "model_drift_telemetry" in tables


# =============================================================================
# 2. LOG PREDICTION RECORDING TEST
# =============================================================================
def test_log_prediction_recording(temp_db: str):
    """Verifies recording of an F401 prediction event with complete mathematical state."""
    logger = InferenceFeedbackLogger(db_path=temp_db)

    req_data = {
        "headline": "VNM công bố lợi nhuận quý 3 vượt 3,500 tỷ đồng, tăng trưởng 25%",
        "symbol": "VNM",
        "source": "CafeF",
        "published_at": "2026-09-01T08:30:00",
    }
    resp_data = {
        "symbol": "VNM",
        "sentiment_class": "POSITIVE",
        "raw_probabilities": {"negative": 0.05, "neutral": 0.15, "positive": 0.80},
        "projected_probabilities": {"negative": 0.06, "neutral": 0.14, "positive": 0.80},
        "raw_sentiment_score": 87.5,
        "consistent_alpha_score": 82.0,
        "is_consistent": True,
        "violation_score": 0.02,
        "is_duplicate": False,
        "source_trust_weight": 0.85,
        "matched_shareholder": "Mai Kiều Liên",
        "action_recommendation": "BUY_DIP",
        "regime_safe_to_trade": True,
        "latency_ms": 12.5,
    }

    pid = logger.log_prediction(req_data, resp_data)
    assert pid is not None
    assert len(pid) > 10

    # Retrieve and verify stored record
    rec = logger.get_prediction(pid)
    assert rec is not None
    assert rec["prediction_id"] == pid
    assert rec["symbol"] == "VNM"
    assert rec["headline"] == req_data["headline"]
    assert rec["consistent_alpha_score"] == 82.0
    assert rec["p_star_pos"] == 0.80
    assert rec["p_star_neg"] == 0.06
    assert rec["action_recommendation"] == "BUY_DIP"
    assert rec["is_backfilled"] is False
    assert rec["matched_shareholder"] == "Mai Kiều Liên"


# =============================================================================
# 3. POST-MARKET RECONCILIATION TEST (EXACT TRADING SESSIONS)
# =============================================================================
def test_reconciliation_exact_trading_days(temp_db: str):
    """Verifies that FeedbackReconciler matches exact trading days (T0, T+1, T+5, T+30)
    and computes percentage returns correctly given a synthetic OHLCV history.
    """
    logger = InferenceFeedbackLogger(db_path=temp_db)
    reconciler = FeedbackReconciler(db_path=temp_db)

    # 1. Populate 40 synthetic trading sessions for VNM starting 2026-09-01
    con = duckdb.connect(temp_db, read_only=False)
    base_date = datetime.date(2026, 9, 1)
    trading_dates = []
    curr = base_date
    while len(trading_dates) < 40:
        if curr.weekday() < 5:  # Monday to Friday
            trading_dates.append(curr)
        curr += datetime.timedelta(days=1)

    # Base price = 100.0, steadily appreciating
    # T0 = 100.0, T1 = 102.0 (+2%), T5 = 107.0 (+7%), T30 = 120.0 (+20%)
    prices = [100.0 + i * 0.5 for i in range(40)]
    prices[1] = 102.0  # +2% at T+1
    prices[5] = 107.0  # +7% at T+5
    prices[30] = 120.0 # +20% at T+30

    now_ts = datetime.datetime.now(datetime.timezone.utc)
    for d, p in zip(trading_dates, prices):
        con.execute(
            """
            INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("VNM", d, p, p * 1.01, p * 0.99, p, 1000000, now_ts),
        )
    con.close()

    # 2. Log a bullish prediction at T0 (2026-09-01)
    pid = logger.log_prediction(
        req={
            "headline": "Vinamilk xuất khẩu sữa sang thị trường mới",
            "symbol": "VNM",
            "published_at": "2026-09-01T09:00:00",
        },
        resp={
            "symbol": "VNM",
            "sentiment_class": "POSITIVE",
            "projected_probabilities": {"negative": 0.05, "neutral": 0.15, "positive": 0.80},
            "raw_sentiment_score": 85.0,
            "consistent_alpha_score": 80.0,  # Bullish alpha > 52.0
            "source_trust_weight": 0.85,
            "is_consistent": True,
            "violation_score": 0.0,
            "action_recommendation": "BUY_DIP",
            "regime_safe_to_trade": True,
        },
    )

    # 3. Run Reconciler
    stats = reconciler.reconcile_pending_predictions()
    assert stats["updated"] == 1
    assert stats["completed"] == 1

    # 4. Verify back-filled prices and returns
    rec = logger.get_prediction(pid)
    assert rec is not None
    assert rec["is_backfilled"] is True
    assert rec["realized_price_t0"] == pytest.approx(100.0, rel=1e-3)
    assert rec["realized_price_t1"] == pytest.approx(102.0, rel=1e-3)
    assert rec["realized_price_t5"] == pytest.approx(107.0, rel=1e-3)
    assert rec["realized_price_t30"] == pytest.approx(120.0, rel=1e-3)

    assert rec["return_t1"] == pytest.approx(0.02, rel=1e-3)  # +2.0%
    assert rec["return_t5"] == pytest.approx(0.07, rel=1e-3)  # +7.0%
    assert rec["return_t30"] == pytest.approx(0.20, rel=1e-3) # +20.0%

    # Directional hit: Bullish alpha (80.0) and positive return (+7.0%) -> hit = 1
    assert rec["direction_hit_t5"] == 1

    # Brier score at T+5: Outcome y = [0, 0, 1], p* = [0.05, 0.15, 0.80]
    # Brier = (0.05 - 0)^2 + (0.15 - 0)^2 + (0.80 - 1)^2 = 0.0025 + 0.0225 + 0.04 = 0.065
    assert rec["brier_score_t5"] == pytest.approx(0.065, rel=1e-3)


# =============================================================================
# 4. PARTIAL RECONCILIATION TEST (PENDING HORIZONS)
# =============================================================================
def test_partial_reconciliation_pending(temp_db: str):
    """Verifies that if only T+1 has elapsed (e.g. 2 bars), T+1 is filled but
    T+5 and T+30 remain None and is_backfilled remains False.
    """
    logger = InferenceFeedbackLogger(db_path=temp_db)
    reconciler = FeedbackReconciler(db_path=temp_db)

    con = duckdb.connect(temp_db, read_only=False)
    now_ts = datetime.datetime.now(datetime.timezone.utc)
    # Only 3 trading days available
    con.execute(
        """
        INSERT INTO core.market_ohlcv_daily VALUES
        ('HPG', '2026-09-01', 25.0, 25.5, 24.8, 25.0, 5000000, ?),
        ('HPG', '2026-09-02', 25.2, 25.6, 25.0, 25.5, 6000000, ?),
        ('HPG', '2026-09-03', 25.4, 25.8, 25.2, 25.8, 5500000, ?)
        """,
        (now_ts, now_ts, now_ts),
    )
    con.close()

    pid = logger.log_prediction(
        req={"headline": "Hòa Phát tăng sản lượng thép", "symbol": "HPG", "published_at": "2026-09-01T08:00:00"},
        resp={"symbol": "HPG", "consistent_alpha_score": 60.0, "projected_probabilities": {"negative": 0.1, "neutral": 0.2, "positive": 0.7}},
    )

    reconciler.reconcile_pending_predictions()

    rec = logger.get_prediction(pid)
    assert rec is not None
    assert rec["realized_price_t0"] == pytest.approx(25.0, rel=1e-3)
    assert rec["realized_price_t1"] == pytest.approx(25.5, rel=1e-3)
    assert rec["realized_price_t5"] is None or (isinstance(rec["realized_price_t5"], float) and np.isnan(rec["realized_price_t5"]))
    assert rec["realized_price_t30"] is None or (isinstance(rec["realized_price_t30"], float) and np.isnan(rec["realized_price_t30"]))
    assert rec["is_backfilled"] is False  # Still pending T+5


# =============================================================================
# 5. DRIFT METRICS & TELEMETRY TEST
# =============================================================================
def test_drift_metrics_computation(temp_db: str):
    """Verifies that DriftMonitor computes accurate rolling Brier, Accuracy, and Spearman IC."""
    logger = InferenceFeedbackLogger(db_path=temp_db)
    monitor = DriftMonitor(db_path=temp_db)

    # Insert 10 synthetic completed feedback records directly
    con = duckdb.connect(temp_db, read_only=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(10):
        pid = f"pred-{i}"
        alpha = 60.0 + i * 2.0  # [60, ..., 78]
        ret5 = 0.01 + i * 0.005  # Positive returns
        dir_hit = 1  # All hits
        brier = 0.030 + i * 0.001
        con.execute(
            """
            INSERT INTO meta.prediction_feedback_log (
                prediction_id, created_at, symbol, headline, source_trust_weight,
                raw_sentiment_score, consistent_alpha_score, sentiment_class,
                p_star_neg, p_star_neu, p_star_pos, violation_score, is_consistent,
                is_duplicate, action_recommendation, regime_safe_to_trade,
                return_t5, direction_hit_t5, brier_score_t5, is_backfilled
            ) VALUES (?, ?, 'SSI', 'Test headline', 0.85, 70.0, ?, 'POSITIVE',
                      0.1, 0.2, 0.7, 0.0, TRUE, FALSE, 'BUY_DIP', TRUE, ?, ?, ?, TRUE)
            """,
            (pid, now, alpha, ret5, dir_hit, brier),
        )
    con.close()

    report = monitor.compute_rolling_drift(window_size=10)
    assert report.total_evaluated == 10
    assert report.directional_accuracy_t5 == pytest.approx(1.0, rel=1e-3)
    assert report.mean_brier_score_t5 == pytest.approx(0.0345, rel=1e-3)
    assert report.spearman_ic_t5 == pytest.approx(1.0, rel=1e-3)  # Perfect rank correlation
    assert report.circuit_breaker_status == "NORMAL"
    assert report.alert_triggered is False


# =============================================================================
# 6. CIRCUIT BREAKER TRIP ON MODEL DEGRADATION TEST
# =============================================================================
def test_circuit_breaker_trip_on_market_degradation(temp_db: str):
    """Verifies that DriftMonitor detects catastrophic accuracy collapse (< 35%)
    and trips the SYSTEM_DEGRADED_HALT circuit breaker.
    """
    monitor = DriftMonitor(db_path=temp_db)

    # Insert 10 records with 0% accuracy (model predicted bull, market crashed)
    con = duckdb.connect(temp_db, read_only=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(10):
        pid = f"degraded-pred-{i}"
        alpha = 80.0
        ret5 = -0.08  # -8% crash
        dir_hit = 0   # 0% hit rate
        brier = 0.075 # Severely degraded Brier > 0.060
        con.execute(
            """
            INSERT INTO meta.prediction_feedback_log (
                prediction_id, created_at, symbol, headline, source_trust_weight,
                raw_sentiment_score, consistent_alpha_score, sentiment_class,
                p_star_neg, p_star_neu, p_star_pos, violation_score, is_consistent,
                is_duplicate, action_recommendation, regime_safe_to_trade,
                return_t5, direction_hit_t5, brier_score_t5, is_backfilled
            ) VALUES (?, ?, 'VIC', 'Bull trap headline', 0.85, 80.0, ?, 'POSITIVE',
                      0.05, 0.15, 0.80, 0.0, TRUE, FALSE, 'BUY_DIP', TRUE, ?, ?, ?, TRUE)
            """,
            (pid, now, alpha, ret5, dir_hit, brier),
        )
    con.close()

    report = monitor.compute_rolling_drift(window_size=10)
    assert report.total_evaluated == 10
    assert report.directional_accuracy_t5 == pytest.approx(0.0, abs=1e-3)  # 0%
    assert report.mean_brier_score_t5 == pytest.approx(0.075, rel=1e-3)
    assert report.circuit_breaker_status == "SYSTEM_DEGRADED_HALT"
    assert report.alert_triggered is True
    assert "below minimum 35.0%" in report.alert_message


# =============================================================================
# 7. FASTAPI DRIFT STATUS ENDPOINT INTEGRATION TEST
# =============================================================================
def test_fastapi_drift_status_endpoint():
    """Verifies that GET /api/v1/drift_status responds with valid telemetry structure."""
    client = TestClient(app)
    resp = client.get("/api/v1/drift_status?window_size=15")
    assert resp.status_code == 200
    data = resp.json()

    assert "run_id" in data
    assert "circuit_breaker_status" in data
    assert data["circuit_breaker_status"] in ["NORMAL", "WARNING", "SYSTEM_DEGRADED_HALT"]
    assert "total_evaluated" in data
    assert "total_pending" in data
    assert "alert_triggered" in data


# =============================================================================
# 8. STRICTLY READ-ONLY COMPLIANCE TEST (RULE B1)
# =============================================================================
def test_strictly_read_only_compliance():
    """Verifies that feedback_log.py contains zero order execution or broker logic."""
    code = (SRC_DIR / "service" / "feedback_log.py").read_text(encoding="utf-8").lower()
    prohibited_terms = [
        "place_order",
        "cancel_order",
        "submit_order",
        "buy_order",
        "sell_order",
        "broker_client",
        "dnse_token",
        "ssi_private_key",
        "fix_session",
    ]
    for term in prohibited_terms:
        assert term not in code, f"Prohibited broker execution term '{term}' found in feedback_log.py!"
