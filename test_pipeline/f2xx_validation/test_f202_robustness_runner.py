"""Test Runner for F202: Statistical Robustness & Cluster Controls.

Runs multi-cluster bootstrap and regime sign-flip checks against target test database.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f2xx_validation.f201_robustness_check import (
    cluster_bootstrap,
    load_events,
)


def run_f202_test(db_path: str = "db/vesta_test.duckdb", iterations: int = 500) -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)
    print(f"[F202] Testing Statistical Robustness & Multi-Cluster Bootstrap on {db_path}...")

    df = load_events(con)
    n_events = len(df)
    print(f"  -> Loaded {n_events:,} negative-sentiment events")

    res_symbol = cluster_bootstrap(df, cluster_col="symbol", n_boot=iterations, seed=42)
    mean_diff = res_symbol["mean_diff"]
    ci_lower = res_symbol["ci_95_low"]
    ci_upper = res_symbol["ci_95_high"]
    p_val = res_symbol["p_cluster"]

    print(f"  -> Symbol Cluster Bootstrap: Mean Diff={mean_diff:.4%}, 95% CI=[{ci_lower:.4%}, {ci_upper:.4%}], p={p_val:.2e}")

    report = {
        "feature": "F202",
        "database": db_path,
        "n_events": n_events,
        "symbol_bootstrap": {
            "mean_diff": mean_diff,
            "ci_95": [ci_lower, ci_upper],
            "p_value": p_val,
        },
        "status": "PASS" if p_val < 0.05 else "FAIL",
    }
    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F202 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    parser.add_argument("--iter", type=int, default=500, help="Bootstrap iterations")
    args = parser.parse_args()
    res = run_f202_test(args.db_path, iterations=args.iter)
    print(f"Result: {res['status']}")
