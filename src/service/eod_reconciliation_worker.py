"""src/service/eod_reconciliation_worker.py

Feature F402 & F403 Production Pipeline Bridge:
Automated End-Of-Day (EOD) Reconciliation, Drift Audit & Continuous Retraining Dispatcher.

Workflow (Runs at 15:30 EOD or on-demand):
1. Reconciles pending prediction records in meta.prediction_feedback_log with realized OHLCV closing prices.
2. Computes multi-horizon forward returns R_{T+1}, R_{T+5}, R_{T+30}, directional accuracy, and Brier scores.
3. Computes rolling Information Coefficient (IC), Brier calibration, and Population Stability Index (PSI).
4. If performance degrades (Brier > 0.050, Acc < 40%) or accumulated samples >= 2,000:
   Automatically dispatches ContinuousTrainingOrchestrator (F403) with the PEFT Shadow Model Gate!
5. Strictly read-only compliance (Rule B1): Operates solely on audit logging and telemetry, zero order execution.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import logging
import os
import pathlib
import sys
from typing import Any, Dict, Optional

# Ensure repo root and src/ are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service.continuous_training import ContinuousTrainingPipeline, TrainingRunResult
from service.feedback_log import DriftMonitor, DriftReport, FeedbackReconciler

logger = logging.getLogger("eod_reconciliation_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEFAULT_DB_PATH = str(REPO_ROOT / "db" / "vesta.duckdb")


@dataclasses.dataclass
class EODExecutionSummary:
    execution_id: str
    executed_at: str
    reconciliation_stats: Dict[str, Any]
    drift_report: Optional[Dict[str, Any]]
    retraining_dispatched: bool
    retraining_result: Optional[Dict[str, Any]]
    system_status: str
    message: str


class EODReconciliationWorker:
    """Automates post-market EOD reconciliation and triggers continuous retraining."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        retrain_on_drift: bool = True,
        sample_threshold: int = 2000,
    ) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.retrain_on_drift = retrain_on_drift
        self.sample_threshold = sample_threshold
        self.reconciler = FeedbackReconciler(db_path=self.db_path)
        self.drift_monitor = DriftMonitor(db_path=self.db_path)
        self.ct_pipeline = ContinuousTrainingPipeline(db_path=self.db_path)
        self.ct_orchestrator = self.ct_pipeline

    def run_eod_cycle(
        self,
        as_of_date: Optional[datetime.date] = None,
        dry_run: bool = False,
    ) -> EODExecutionSummary:
        """Executes the full post-market reconciliation, drift evaluation, and retrain loop."""
        now = datetime.datetime.now(datetime.timezone.utc)
        exec_id = f"eod_{now.strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"[{exec_id}] Starting EOD reconciliation cycle on {self.db_path}...")

        # Step 1: Reconcile pending predictions with realized OHLCV prices
        reconcile_stats = self.reconciler.reconcile_pending_predictions(max_batch=1000)
        logger.info(f"[{exec_id}] Reconciled: {reconcile_stats}")

        # Step 2: Evaluate model drift telemetry
        drift_report: Optional[DriftReport] = None
        try:
            drift_report = self.drift_monitor.compute_rolling_drift(window_size=100)
            logger.info(
                f"[{exec_id}] Drift Audit complete. Circuit Breaker: {drift_report.circuit_breaker_status} "
                f"(Acc={drift_report.directional_accuracy_t5}, Brier={drift_report.mean_brier_score_t5})"
            )
        except Exception as err:
            logger.warning(f"[{exec_id}] Drift audit could not be evaluated: {err}")

        # Step 3: Determine if Continuous Retraining (F403) should be triggered
        should_retrain, retrain_reason = self.ct_pipeline.check_triggers(
            min_sample_threshold=self.sample_threshold,
            drift_report=drift_report,
        )
        retrain_dispatched = False
        retrain_summary: Optional[Dict[str, Any]] = None

        if should_retrain and self.retrain_on_drift and not dry_run:
            logger.info(f"[{exec_id}] Dispatching Automated Continuous Retraining (Reason: {retrain_reason})...")
            try:
                run_res: TrainingRunResult = self.ct_pipeline.execute_training_cycle(
                    epochs=3,
                    batch_size=16,
                    trigger_reason_override=retrain_reason,
                )
                retrain_dispatched = True
                retrain_summary = {
                    "run_id": run_res.training_run_id,
                    "is_promoted": run_res.is_promoted,
                    "prev_accuracy": run_res.prev_val_accuracy,
                    "shadow_accuracy": run_res.shadow_val_accuracy,
                    "message": run_res.message,
                }
            except Exception as err:
                logger.error(f"[{exec_id}] Continuous Retraining failed: {err}")
                retrain_summary = {"error": str(err)}
        elif dry_run and should_retrain:
            logger.info(f"[{exec_id}] Dry-run: Continuous Retraining trigger detected ({retrain_reason}) but not dispatched.")

        # Determine overall system status
        sys_status = "HEALTHY"
        if drift_report and drift_report.circuit_breaker_status == "SYSTEM_DEGRADED_HALT":
            sys_status = "DEGRADED"

        summary = EODExecutionSummary(
            execution_id=exec_id,
            executed_at=now.isoformat(),
            reconciliation_stats=reconcile_stats,
            drift_report=dataclasses.asdict(drift_report) if drift_report else None,
            retraining_dispatched=retrain_dispatched,
            retraining_result=retrain_summary,
            system_status=sys_status,
            message=(
                f"EOD Cycle complete. Updated {reconcile_stats.get('updated', 0)} items, "
                f"Completed {reconcile_stats.get('completed', 0)} items. "
                f"Status: {sys_status}. Retrained: {retrain_dispatched}."
            ),
        )

        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA EOD Reconciliation & Drift Retraining Worker")
    parser.add_argument("--db-path", type=str, default=DEFAULT_DB_PATH, help="Path to DuckDB database")
    parser.add_argument("--dry-run", action="store_true", help="Perform reconciliation audit without model retraining")
    parser.add_argument("--run-now", action="store_true", help="Execute single cycle immediately")
    args = parser.parse_args()

    worker = EODReconciliationWorker(db_path=args.db_path)
    summary = worker.run_eod_cycle(dry_run=args.dry_run)
    print("\n" + "=" * 65)
    print("         VESTA POST-MARKET EOD RECONCILIATION SUMMARY          ")
    print("=" * 65)
    print(f"Execution ID:          {summary.execution_id}")
    print(f"Timestamp:             {summary.executed_at}")
    print(f"System Status:         {summary.system_status}")
    print(f"Total Reconciled:      {summary.reconciliation_stats.get('total_reconciled', 0)}")
    print(f"Pending Labels:        {summary.reconciliation_stats.get('pending_count', 0)}")
    print(f"Retraining Dispatched: {summary.retraining_dispatched}")
    if summary.retraining_result:
        print(f"Retraining Result:     {summary.retraining_result.get('message', '')}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
