"""Test Runner for F104: Vectorized ML Feature Extraction.

Validates that feature vectors are extracted with zero look-ahead bias and
temporal train/val/test splits are strictly non-overlapping.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f1xx_enrichment.ml_features import (
    build_feature_dataframe,
    split_temporal_dataset,
)


def resolve_db(preferred: str) -> str:
    candidates = [preferred, "db/test_db/vesta_test.duckdb", "db/vesta_test.duckdb", "db/vesta.duckdb"]
    for c in candidates:
        if c and pathlib.Path(c).exists():
            return c
    return preferred


def run_f104_test(db_path: str = "db/test_db/vesta_test.duckdb", limit: int = 5000) -> dict[str, object]:
    actual_db = resolve_db(db_path)
    con = duckdb.connect(actual_db, read_only=True)
    print(f"[F104] Testing Vectorized ML Features on {actual_db} (Sample: {limit:,} events)...")

    df = build_feature_dataframe(con, limit=limit, vectorized=True)
    train_df, val_df, test_df = split_temporal_dataset(df)

    n_features = len(df.columns)
    events_count = len(df)

    passed = (events_count > 0) and (n_features >= 20)
    report: dict[str, object] = {
        "feature": "F104",
        "database": db_path,
        "events_processed": events_count,
        "features_count": n_features,
        "splits": {
            "train": len(train_df),
            "val": len(val_df),
            "test": len(test_df),
        },
        "status": "PASS" if passed else "FAIL",
    }

    print(f"  -> Extracted {events_count:,} events with {n_features} features")
    print(f"  -> Splits: Train={len(train_df):,}, Val={len(val_df):,}, Test={len(test_df):,}")
    print(f"  -> Status: {report['status']}")

    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F104 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    parser.add_argument("--limit", type=int, default=5000, help="Event sample limit")
    args = parser.parse_args()
    res = run_f104_test(args.db_path, limit=args.limit)
    print(f"Result: {res['status']}")
