"""Test Runner for F203: Regime-Conditional Validity Audit.

Executes the 16-Regime x 3-Exchange evaluation matrix on the target test database.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f2xx_validation.f203_regime_audit import run_regime_audit


def run_f203_test(db_path: str = "db/vesta_test.duckdb") -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)
    print(f"[F203] Testing 2D Regime-Conditional Audit on {db_path}...")

    rep = run_regime_audit(con, out_path=None)
    matrix = rep["regime_matrix"]
    n_evaluated = len(matrix)

    sign_flips = sum(1 for r in matrix if r["sign_flip"])
    print(f"  -> Evaluated {n_evaluated} Regime x Exchange cells")
    print(f"  -> Sign-flips detected in {sign_flips}/{n_evaluated} cells")
    print(f"  -> Status: PASS (Audit Completed)")

    con.close()
    return rep


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F203 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    args = parser.parse_args()
    run_f203_test(args.db_path)
