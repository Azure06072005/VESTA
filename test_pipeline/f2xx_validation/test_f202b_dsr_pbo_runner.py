"""Test Runner for F202b: Formal Deflated Sharpe Ratio & CSCV PBO.

Computes DSR and Probability of Backtest Overfitting (PBO) against target test database.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f2xx_validation.f202b_dsr_pbo import run_f202b_analysis


def run_f202b_test(db_path: str = "db/vesta_test.duckdb") -> dict[str, object]:
    print(f"[F202b] Testing Deflated Sharpe Ratio & CSCV PBO on {db_path}...")

    rep = run_f202b_analysis(db_path=db_path, report_path=None)
    meta = rep.get("meta", {})
    treatments = rep.get("treatments", {})
    pbo_res = rep.get("pbo_analysis", {})

    raw_kurt = treatments.get("raw_unadjusted", {}).get("kurtosis", 0.0)
    win_dsr = treatments.get("winsorized_0_5pct", {}).get("trials", {}).get("N_1", {}).get("dsr", 0.0)
    pbo_val = pbo_res.get("pbo", 0.0)

    passed = (win_dsr >= 0.95) and (pbo_val < 0.10)
    report = {
        "feature": "F202b",
        "database": db_path,
        "n_events": meta.get("total_negative_events", 0),
        "raw_kurtosis": round(raw_kurt, 2),
        "winsorized_0_5pct_dsr_n1": round(win_dsr, 4),
        "cscv_pbo": round(pbo_val, 4),
        "status": "PASS" if passed else "FAIL",
    }

    print(f"  -> Raw Kurtosis: {raw_kurt:.2f}")
    print(f"  -> Winsorized (0.5%) DSR (N=1): {win_dsr:.4f}")
    print(f"  -> CSCV PBO: {pbo_val:.4f}")
    print(f"  -> Status: {report['status']}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F202b test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    args = parser.parse_args()
    res = run_f202b_test(args.db_path)
    print(f"Result: {res['status']}")
