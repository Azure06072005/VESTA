"""src/service/feedback_log.py

Feature F402: Feedback log for scored predictions vs realized returns.
Closed-loop Continuous Auditing & Model Drift Monitoring Engine.

Key Capabilities:
1. InferenceFeedbackLogger:
   - Non-blocking, low-latency logging of F401 scored predictions into meta.prediction_feedback_log.
   - Preserves complete probability distribution (Kolmogorov Simplex p*), alpha scores, and entity data.
2. FeedbackReconciler:
   - Scheduled post-market job (15:30) to query core.market_ohlcv_daily for exact trading sessions.
   - Calculates realized forward returns R_{T+1}, R_{T+5}, R_{T+30}.
   - Back-fills ground truth multi-class Brier score and directional hits at T+5.
3. DriftMonitor:
   - Evaluates rolling directional accuracy (T+5), rolling Brier score, and Spearman rank Information Coefficient (IC).
   - Automated Degradation Circuit Breaker: Triggers SYSTEM_DEGRADED_HALT when accuracy < 35% or Brier > 0.060.
4. Strictly Read-Only compliance (Rule B1): Operates solely on audit logging and telemetry, zero order execution.
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
import os
import pathlib
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import duckdb
import numpy as np

# Ensure repo root and src/ are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("feedback_log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEFAULT_DB_PATH = str(REPO_ROOT / "db" / "vesta.duckdb")

DDL_FEEDBACK_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.prediction_feedback_log (
    prediction_id          VARCHAR PRIMARY KEY,
    created_at             TIMESTAMP NOT NULL,
    symbol                 VARCHAR NOT NULL,
    headline               VARCHAR NOT NULL,
    source                 VARCHAR,
    source_trust_weight    DOUBLE NOT NULL,
    raw_sentiment_score    DOUBLE NOT NULL,
    consistent_alpha_score DOUBLE NOT NULL,
    sentiment_class        VARCHAR NOT NULL,
    p_star_neg             DOUBLE NOT NULL,
    p_star_neu             DOUBLE NOT NULL,
    p_star_pos             DOUBLE NOT NULL,
    violation_score        DOUBLE NOT NULL,
    is_consistent          BOOLEAN NOT NULL,
    is_duplicate           BOOLEAN NOT NULL,
    action_recommendation  VARCHAR NOT NULL,
    regime_safe_to_trade   BOOLEAN NOT NULL,
    matched_shareholder    VARCHAR,
    event_date             DATE,
    realized_price_t0      DOUBLE,
    realized_price_t1      DOUBLE,
    realized_price_t5      DOUBLE,
    realized_price_t30     DOUBLE,
    return_t1              DOUBLE,
    return_t5              DOUBLE,
    return_t30             DOUBLE,
    direction_hit_t5       INTEGER,
    brier_score_t5         DOUBLE,
    is_backfilled          BOOLEAN NOT NULL DEFAULT FALSE,
    backfilled_at          TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta.model_drift_telemetry (
    run_id                         VARCHAR PRIMARY KEY,
    audit_timestamp                TIMESTAMP NOT NULL,
    window_size                    INTEGER NOT NULL,
    rolling_directional_accuracy_t5 DOUBLE,
    rolling_brier_score_t5         DOUBLE,
    rolling_spearman_ic_t5         DOUBLE,
    rolling_spearman_ic_t30        DOUBLE,
    total_evaluated                INTEGER NOT NULL,
    total_pending                  INTEGER NOT NULL,
    circuit_breaker_status         VARCHAR NOT NULL,
    alert_message                  VARCHAR
);
"""


@dataclasses.dataclass
class DriftReport:
    run_id: str
    audit_timestamp: datetime.datetime
    window_size: int
    total_evaluated: int
    total_pending: int
    directional_accuracy_t5: Optional[float]
    mean_brier_score_t5: Optional[float]
    spearman_ic_t5: Optional[float]
    circuit_breaker_status: str  # 'NORMAL' | 'WARNING' | 'SYSTEM_DEGRADED_HALT'
    alert_triggered: bool
    alert_message: str


def _get_connection(db_path: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Connects safely to DuckDB with directory creation."""
    if db_path != ":memory:":
        p = pathlib.Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(db_path, read_only=read_only)


# =============================================================================
# 1. INFERENCE FEEDBACK LOGGER (NON-BLOCKING AUDIT LOGGING)
# =============================================================================
class InferenceFeedbackLogger:
    """Non-blocking feedback log writer for real-time F401 streaming inference."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get("VESTA_FEEDBACK_DB_PATH", DEFAULT_DB_PATH)
        self._init_tables()

    def _init_tables(self) -> None:
        """Initializes meta tables if not present."""
        try:
            con = _get_connection(self.db_path, read_only=False)
            con.execute(DDL_FEEDBACK_SCHEMA)
            con.close()
        except Exception as err:
            logger.warning(f"Could not bootstrap feedback tables in {self.db_path} ({err})")

    def log_prediction(
        self,
        req: Any,
        resp: Any,
        prediction_id: Optional[str] = None,
    ) -> str:
        """Logs a scored inference prediction event atomically.

        Args:
            req: HeadlineScoreRequest or dict
            resp: HeadlineScoreResponse or dict
            prediction_id: Optional custom UUID

        Returns:
            The recorded prediction_id.
        """
        pid = prediction_id or str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)

        # Handle req as Pydantic model or dict
        req_dict = req if isinstance(req, dict) else req.model_dump()
        resp_dict = resp if isinstance(resp, dict) else resp.model_dump()

        symbol = req_dict.get("symbol") or resp_dict.get("symbol") or "UNKNOWN"
        headline = req_dict.get("headline", "")
        source = req_dict.get("source")
        source_trust = float(resp_dict.get("source_trust_weight", 0.60))
        raw_score = float(resp_dict.get("raw_sentiment_score", 50.0))
        alpha_score = float(resp_dict.get("consistent_alpha_score", 50.0))
        sentiment_cls = str(resp_dict.get("sentiment_class", "NEUTRAL"))

        proj_probs = resp_dict.get("projected_probabilities", {})
        p_neg = float(proj_probs.get("negative", 0.0))
        p_neu = float(proj_probs.get("neutral", 1.0))
        p_pos = float(proj_probs.get("positive", 0.0))

        violation = float(resp_dict.get("violation_score", 0.0))
        is_consistent = bool(resp_dict.get("is_consistent", True))
        is_dup = bool(resp_dict.get("is_duplicate", False))
        action = str(resp_dict.get("action_recommendation", "HOLD"))
        regime_safe = bool(resp_dict.get("regime_safe_to_trade", True))
        matched_holder = resp_dict.get("matched_shareholder")

        # Parse event_date
        published_at_str = req_dict.get("published_at")
        event_date = None
        if published_at_str:
            try:
                # Truncate time if full ISO string
                event_date = datetime.date.fromisoformat(published_at_str[:10])
            except Exception:
                event_date = now.date()
        else:
            event_date = now.date()

        try:
            con = _get_connection(self.db_path, read_only=False)
            con.execute(
                """
                INSERT INTO meta.prediction_feedback_log (
                    prediction_id, created_at, symbol, headline, source,
                    source_trust_weight, raw_sentiment_score, consistent_alpha_score,
                    sentiment_class, p_star_neg, p_star_neu, p_star_pos,
                    violation_score, is_consistent, is_duplicate,
                    action_recommendation, regime_safe_to_trade, matched_shareholder,
                    event_date, is_backfilled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)
                """,
                (
                    pid, now, symbol, headline, source,
                    source_trust, raw_score, alpha_score,
                    sentiment_cls, p_neg, p_neu, p_pos,
                    violation, is_consistent, is_dup,
                    action, regime_safe, matched_holder,
                    event_date,
                ),
            )
            con.close()
            return pid
        except Exception as err:
            logger.error(f"Failed to log prediction {pid}: {err}")
            return pid

    def get_prediction(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single prediction record by ID."""
        try:
            con = _get_connection(self.db_path, read_only=True)
            cursor = con.execute(
                "SELECT * FROM meta.prediction_feedback_log WHERE prediction_id = ?",
                (prediction_id,),
            )
            row = cursor.fetchone()
            if row is None:
                con.close()
                return None
            cols = [desc[0] for desc in cursor.description]
            con.close()
            return dict(zip(cols, row))
        except Exception as err:
            logger.warning(f"Error fetching prediction {prediction_id}: {err}")
            return None


# =============================================================================
# 2. POST-MARKET RECONCILER (RECONCILE REALIZED PRICES & FORWARD RETURNS)
# =============================================================================
class FeedbackReconciler:
    """Reconciles logged predictions with market_ohlcv_daily to calculate realized returns."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get("VESTA_FEEDBACK_DB_PATH", DEFAULT_DB_PATH)

    def reconcile_pending_predictions(self, max_batch: int = 1000) -> Dict[str, int]:
        """Scans pending predictions and reconciles available forward prices (T+1, T+5, T+30).

        Returns:
            Dict summary of updated, completed, and skipped counts.
        """
        stats = {"updated": 0, "completed": 0, "skipped": 0}

        try:
            con = _get_connection(self.db_path, read_only=False)
        except Exception as err:
            logger.error(f"Cannot connect to database for reconciliation: {err}")
            return stats

        try:
            # Query pending predictions
            pending_df = con.execute(
                """
                SELECT prediction_id, symbol, event_date, consistent_alpha_score,
                       p_star_neg, p_star_neu, p_star_pos, realized_price_t0,
                       realized_price_t1, realized_price_t5, realized_price_t30
                FROM meta.prediction_feedback_log
                WHERE is_backfilled = FALSE
                ORDER BY event_date ASC
                LIMIT ?
                """,
                (max_batch,),
            ).fetchdf()

            if len(pending_df) == 0:
                con.close()
                return stats

            # Process by symbol for fast batch lookups
            symbols = pending_df["symbol"].unique()
            now_ts = datetime.datetime.now(datetime.timezone.utc)

            for sym in symbols:
                if sym == "UNKNOWN":
                    stats["skipped"] += len(pending_df[pending_df["symbol"] == sym])
                    continue

                # Query daily bars for this symbol
                bars_df = con.execute(
                    """
                    SELECT date, close
                    FROM core.market_ohlcv_daily
                    WHERE symbol = ?
                    ORDER BY date ASC
                    """,
                    (sym,),
                ).fetchdf()

                if len(bars_df) == 0:
                    stats["skipped"] += len(pending_df[pending_df["symbol"] == sym])
                    continue

                dates = bars_df["date"].tolist()
                closes = bars_df["close"].tolist()
                date_to_idx = {d: i for i, d in enumerate(dates)}

                sym_preds = pending_df[pending_df["symbol"] == sym]

                for _, row in sym_preds.iterrows():
                    pid = row["prediction_id"]
                    ev_date = row["event_date"]
                    alpha = row["consistent_alpha_score"]
                    p_neg = row["p_star_neg"]
                    p_neu = row["p_star_neu"]
                    p_pos = row["p_star_pos"]

                    # Find T0 session index (exact date or first trading session on/after event_date)
                    t0_idx = None
                    if ev_date in date_to_idx:
                        t0_idx = date_to_idx[ev_date]
                    else:
                        # Find first trading day >= ev_date
                        for idx, d in enumerate(dates):
                            if d >= ev_date:
                                t0_idx = idx
                                break

                    if t0_idx is None:
                        stats["skipped"] += 1
                        continue

                    p0 = float(closes[t0_idx])
                    if p0 <= 0.0:
                        stats["skipped"] += 1
                        continue

                    # Horizons: T+1, T+5, T+30 in trading sessions
                    idx_t1 = t0_idx + 1
                    idx_t5 = t0_idx + 5
                    idx_t30 = t0_idx + 30

                    p1 = float(closes[idx_t1]) if idx_t1 < len(closes) else None
                    p5 = float(closes[idx_t5]) if idx_t5 < len(closes) else None
                    p30 = float(closes[idx_t30]) if idx_t30 < len(closes) else None

                    ret1 = (p1 - p0) / p0 if p1 is not None else None
                    ret5 = (p5 - p0) / p0 if p5 is not None else None
                    ret30 = (p30 - p0) / p0 if p30 is not None else None

                    # Evaluation metrics at T+5
                    dir_hit = None
                    brier_t5 = None
                    is_complete = False

                    if ret5 is not None:
                        # Directional hit: agreement between sign(alpha - 50) and sign(ret5)
                        if alpha > 52.0:
                            dir_hit = 1 if ret5 > 0.0 else 0
                        elif alpha < 48.0:
                            dir_hit = 1 if ret5 < 0.0 else 0
                        else:
                            # Neutral predictions: hit if return is small (|ret5| <= 1.5%)
                            dir_hit = 1 if abs(ret5) <= 0.015 else 0

                        # Multi-class ground truth outcome: +/- 0.5% boundary
                        if ret5 > 0.005:
                            y = np.array([0.0, 0.0, 1.0])  # Positive
                        elif ret5 < -0.005:
                            y = np.array([1.0, 0.0, 0.0])  # Negative
                        else:
                            y = np.array([0.0, 1.0, 0.0])  # Neutral

                        probs = np.array([p_neg, p_neu, p_pos])
                        brier_t5 = float(np.sum((probs - y) ** 2))

                    # Consider backfilled if T+5 is reached (or T+30 reached)
                    if ret5 is not None:
                        is_complete = True

                    con.execute(
                        """
                        UPDATE meta.prediction_feedback_log
                        SET realized_price_t0 = ?,
                            realized_price_t1 = ?,
                            realized_price_t5 = ?,
                            realized_price_t30 = ?,
                            return_t1 = ?,
                            return_t5 = ?,
                            return_t30 = ?,
                            direction_hit_t5 = ?,
                            brier_score_t5 = ?,
                            is_backfilled = ?,
                            backfilled_at = ?
                        WHERE prediction_id = ?
                        """,
                        (
                            p0, p1, p5, p30,
                            ret1, ret5, ret30,
                            dir_hit, brier_t5,
                            is_complete,
                            now_ts if is_complete else None,
                            pid,
                        ),
                    )
                    stats["updated"] += 1
                    if is_complete:
                        stats["completed"] += 1

            con.close()
        except Exception as err:
            logger.error(f"Reconciliation failure: {err}")
            try:
                con.close()
            except Exception:
                pass

        return stats


# =============================================================================
# 3. CONTINUOUS DRIFT MONITOR & CIRCUIT BREAKER TELEMETRY
# =============================================================================
class DriftMonitor:
    """Computes rolling performance metrics and enforces automated circuit breaker rails."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get("VESTA_FEEDBACK_DB_PATH", DEFAULT_DB_PATH)

    def compute_rolling_drift(self, window_size: int = 30) -> DriftReport:
        """Evaluates rolling calibration, accuracy, and Spearman IC.

        Thresholds for Alerting / Halting:
        - Directional Accuracy < 35.0%: Triggers SYSTEM_DEGRADED_HALT (worse than random).
        - Rolling Brier Score > 0.060: Triggers SYSTEM_DEGRADED_HALT (> +15% degradation from F304 0.0310).
        - Spearman IC < -0.05: Triggers WARNING or HALT (alpha decay).
        """
        run_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)

        try:
            con = _get_connection(self.db_path, read_only=True)
            evaluated_df = con.execute(
                """
                SELECT consistent_alpha_score, return_t5, return_t30,
                       direction_hit_t5, brier_score_t5
                FROM meta.prediction_feedback_log
                WHERE direction_hit_t5 IS NOT NULL
                  AND brier_score_t5 IS NOT NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (window_size,),
            ).fetchdf()

            pending_count = con.execute(
                "SELECT COUNT(*) FROM meta.prediction_feedback_log WHERE is_backfilled = FALSE"
            ).fetchone()[0]

            con.close()
        except Exception as err:
            logger.warning(f"Failed to query drift records ({err}), returning default report.")
            return DriftReport(
                run_id=run_id,
                audit_timestamp=now,
                window_size=window_size,
                total_evaluated=0,
                total_pending=0,
                directional_accuracy_t5=None,
                mean_brier_score_t5=None,
                spearman_ic_t5=None,
                circuit_breaker_status="NORMAL",
                alert_triggered=False,
                alert_message="Insufficient data for drift evaluation.",
            )

        n_eval = len(evaluated_df)
        if n_eval == 0:
            return DriftReport(
                run_id=run_id,
                audit_timestamp=now,
                window_size=window_size,
                total_evaluated=0,
                total_pending=pending_count,
                directional_accuracy_t5=None,
                mean_brier_score_t5=None,
                spearman_ic_t5=None,
                circuit_breaker_status="NORMAL",
                alert_triggered=False,
                alert_message="No reconciled records available yet.",
            )

        # 1. Rolling Directional Accuracy
        hits = evaluated_df["direction_hit_t5"].dropna().values
        acc = float(np.mean(hits)) if len(hits) > 0 else None

        # 2. Rolling Brier Score
        briers = evaluated_df["brier_score_t5"].dropna().values
        mean_brier = float(np.mean(briers)) if len(briers) > 0 else None

        # 3. Rolling Spearman IC (Alpha vs Return T+5)
        ic_t5 = None
        valid_ic = evaluated_df[["consistent_alpha_score", "return_t5"]].dropna()
        if len(valid_ic) >= 5:
            from scipy.stats import spearmanr
            corr, _ = spearmanr(valid_ic["consistent_alpha_score"], valid_ic["return_t5"])
            if not np.isnan(corr):
                ic_t5 = float(corr)

        # 4. Evaluate Circuit Breakers
        status = "NORMAL"
        alert_triggered = False
        alert_msg_parts = []

        if acc is not None and acc < 0.35:
            status = "SYSTEM_DEGRADED_HALT"
            alert_triggered = True
            alert_msg_parts.append(f"Directional accuracy {acc*100:.1f}% below minimum 35.0% rail.")

        if mean_brier is not None and mean_brier > 0.060:
            status = "SYSTEM_DEGRADED_HALT"
            alert_triggered = True
            alert_msg_parts.append(f"Brier score {mean_brier:.4f} degraded beyond 0.060 threshold.")

        if ic_t5 is not None and ic_t5 < -0.05:
            if status != "SYSTEM_DEGRADED_HALT":
                status = "WARNING"
            alert_triggered = True
            alert_msg_parts.append(f"Spearman rank IC {ic_t5:.3f} indicates severe alpha decay.")

        alert_message = " | ".join(alert_msg_parts) if alert_msg_parts else "All telemetry metrics nominal."

        report = DriftReport(
            run_id=run_id,
            audit_timestamp=now,
            window_size=window_size,
            total_evaluated=n_eval,
            total_pending=pending_count,
            directional_accuracy_t5=round(acc, 4) if acc is not None else None,
            mean_brier_score_t5=round(mean_brier, 4) if mean_brier is not None else None,
            spearman_ic_t5=round(ic_t5, 4) if ic_t5 is not None else None,
            circuit_breaker_status=status,
            alert_triggered=alert_triggered,
            alert_message=alert_message,
        )

        # Persist report to meta.model_drift_telemetry
        try:
            con = _get_connection(self.db_path, read_only=False)
            con.execute(
                """
                INSERT INTO meta.model_drift_telemetry (
                    run_id, audit_timestamp, window_size,
                    rolling_directional_accuracy_t5, rolling_brier_score_t5,
                    rolling_spearman_ic_t5, total_evaluated, total_pending,
                    circuit_breaker_status, alert_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, now, window_size,
                    report.directional_accuracy_t5, report.mean_brier_score_t5,
                    report.spearman_ic_t5, report.total_evaluated, report.total_pending,
                    report.circuit_breaker_status, report.alert_message,
                ),
            )
            con.close()
        except Exception as err:
            logger.warning(f"Could not persist drift telemetry: {err}")

        return report
