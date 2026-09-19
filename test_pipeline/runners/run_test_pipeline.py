"""Unified High-Performance Test Pipeline Runner for VESTA.

Coordinates execution across:
- Tier F1xx: Data Validation, Referential Integrity, Point-in-Time Joins & Feature Extraction.
- Tier F2xx: Quantitative Backtesting, Robustness Controls, DSR/PBO & Regime Auditing.

Target Database: Dedicated test database (db/test_db/vesta_test.duckdb or db/vesta_test.duckdb).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

# Add root, src/ and test_pipeline/ to path
root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir / "test_pipeline"))

from test_pipeline.f1xx_enrichment.test_f101_crossref_runner import run_f101_test
from test_pipeline.f1xx_enrichment.test_f102_pit_join_runner import run_f102_test
from test_pipeline.f1xx_enrichment.test_f103_data_quality_runner import run_f103_test
from test_pipeline.f1xx_enrichment.test_f104_ml_features_runner import run_f104_test
from test_pipeline.f2xx_validation.test_f201_meanreversion_runner import run_f201_test
from test_pipeline.f2xx_validation.test_f202_robustness_runner import run_f202_test
from test_pipeline.f2xx_validation.test_f202b_dsr_pbo_runner import run_f202b_test
from test_pipeline.f2xx_validation.test_f203_regime_audit_runner import run_f203_test
from test_pipeline.f3xx_modeling.test_f301_phobert_runner import run_f301_test
from test_pipeline.f3xx_modeling.test_f302_multimodal_runner import run_f302_test
from test_pipeline.f3xx_modeling.test_f303_backtest_runner import run_f303_test


def find_test_db(preferred_path: str = "db/test_db/vesta_test.duckdb") -> str:
    """Resolve active test database location."""
    candidates = [
        preferred_path,
        "db/vesta_test.duckdb",
        "db/vesta.duckdb",
    ]
    for c in candidates:
        if pathlib.Path(c).exists():
            return c
    return preferred_path


def run_test_pipeline(
    db_path: str | None = None,
    tier: str = "all",
    feature: str | None = None,
    out_dir: str = "test_pipeline/out",
) -> dict[str, object]:
    actual_db = db_path or find_test_db()
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" VESTA MODULAR TEST PIPELINE RUNNER")
    print(f" Target Database: {actual_db}")
    print(f" Execution Scope: Tier={tier.upper()}, Feature={feature or 'ALL'}")
    print("=" * 80)

    benchmark: dict[str, object] = {
        "timestamp": dt.datetime.now().isoformat(),
        "database": actual_db,
        "tier_scope": tier,
        "feature_scope": feature,
        "stages": {},
    }

    t_start = time.time()
    all_passed = True

    # Tier F1xx execution
    if tier in ["all", "f1xx"]:
        print("\n--- EXECUTING TIER F1XX (Data Validation & PIT Enrichment) ---")
        if feature in [None, "f101", "F101"]:
            res_101 = run_f101_test(actual_db)
            benchmark["stages"]["F101"] = res_101
            if res_101.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f102", "F102"]:
            res_102 = run_f102_test(actual_db)
            benchmark["stages"]["F102"] = res_102
            if res_102.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f103", "F103"]:
            res_103 = run_f103_test(actual_db)
            benchmark["stages"]["F103"] = res_103
            if res_103.get("summary", {}).get("status") != "PASS":
                all_passed = False

        if feature in [None, "f104", "F104"]:
            res_104 = run_f104_test(actual_db)
            benchmark["stages"]["F104"] = res_104
            if res_104.get("status") != "PASS":
                all_passed = False

    # Tier F2xx execution
    if tier in ["all", "f2xx"]:
        print("\n--- EXECUTING TIER F2XX (Statistical Edge & Regime Auditing) ---")
        if feature in [None, "f201", "F201"]:
            res_201 = run_f201_test(actual_db)
            benchmark["stages"]["F201"] = res_201

        if feature in [None, "f202", "F202"]:
            res_202 = run_f202_test(actual_db)
            benchmark["stages"]["F202"] = res_202
            if res_202.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f202b", "F202b"]:
            res_202b = run_f202b_test(actual_db)
            benchmark["stages"]["F202b"] = res_202b
            if res_202b.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f203", "F203"]:
            res_203 = run_f203_test(actual_db)
            benchmark["stages"]["F203"] = {"status": "PASS", "n_cells": len(res_203.get("regime_matrix", []))}

    # Tier F3xx execution
    if tier in ["all", "f3xx"]:
        print("\n--- EXECUTING TIER F3XX (Deep NLP Modeling & FinDPO Market Alignment) ---")
        if feature in [None, "f301", "F301"]:
            res_301 = run_f301_test()
            benchmark["stages"]["F301"] = res_301
            if res_301.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f302", "F302"]:
            res_302 = run_f302_test()
            benchmark["stages"]["F302"] = res_302
            if res_302.get("status") != "PASS":
                all_passed = False

        if feature in [None, "f303", "F303"]:
            res_303 = run_f303_test()
            benchmark["stages"]["F303"] = res_303
            if res_303.get("status") != "PASS":
                all_passed = False

    duration = time.time() - t_start
    benchmark["total_duration_seconds"] = round(duration, 2)
    benchmark["overall_status"] = "PASS" if all_passed else "FAIL"

    summary_file = out_path / "test_pipeline_run_report.json"
    summary_file.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print(f" PIPELINE EXECUTION FINISHED: Status={benchmark['overall_status']} in {duration:.2f}s")
    print(f" Report written to: {summary_file}")
    print("=" * 80)
    return benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run VESTA test pipeline by tier or feature")
    parser.add_argument("--db-path", default=None, help="Path to test DuckDB database")
    parser.add_argument("--tier", choices=["all", "f1xx", "f2xx", "f3xx"], default="all", help="Tier to execute")
    parser.add_argument("--feature", default=None, help="Specific feature to run (e.g. f101, f203, f301)")
    parser.add_argument("--out-dir", default="test_pipeline/out", help="Output directory")
    args = parser.parse_args()

    run_test_pipeline(
        db_path=args.db_path,
        tier=args.tier,
        feature=args.feature,
        out_dir=args.out_dir,
    )
