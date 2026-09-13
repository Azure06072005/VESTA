"""Forwarding shim for test_pipeline.runners.run_test_pipeline."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runners.run_test_pipeline import main, run_test_pipeline

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run VESTA test pipeline (forwarded)")
    parser.add_argument("--db-path", default=None, help="Target test database")
    parser.add_argument("--tier", choices=["all", "f1xx", "f2xx"], default="all", help="Tier")
    parser.add_argument("--feature", default=None, help="Feature")
    parser.add_argument("--out-dir", default="test_pipeline/out", help="Output directory")
    args = parser.parse_args()

    run_test_pipeline(
        db_path=args.db_path,
        tier=args.tier,
        feature=args.feature,
        out_dir=args.out_dir,
    )
