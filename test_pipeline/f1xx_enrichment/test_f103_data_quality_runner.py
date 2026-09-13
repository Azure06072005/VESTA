"""Test Runner for F103: Enterprise Data Quality Pipeline.

Executes all 11 DQ audit techniques against target test database (db/vesta_test.duckdb).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.ml.data_validation.data_quality import DataQualityPipeline, generate_report


def run_f103_test(db_path: str = "db/vesta_test.duckdb") -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)
    print(f"[F103] Testing Enterprise 11-Technique Data Quality on {db_path}...")

    dq = DataQualityPipeline(con)
    results = dq.run_all_techniques()
    report = generate_report(results)

    summary = report["summary"]
    print(f"  -> Total Checks: {summary['total_checks']}")
    print(f"  -> Passed: {summary['passed']}")
    print(f"  -> Failed: {summary['failed']}")
    print(f"  -> Status: {summary['status']}")

    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F103 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    args = parser.parse_args()
    res = run_f103_test(args.db_path)
    print(f"Result: {res['summary']['status']}")
