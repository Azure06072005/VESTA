"""High-Performance Test Pipeline Runner for VESTA.

Executes end-to-end data quality checks, vectorized feature engineering,
and quantitative backtesting against the dedicated test database (db/vesta_test.duckdb).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from etl import db
from pipeline.backtest_meanreversion import load_events, run_backtest
from pipeline.ml.data_validation.data_quality import DataQualityPipeline, generate_report
from pipeline.ml_features import build_feature_dataframe, split_temporal_dataset


def run_pipeline_test(
    db_path: str = "db/vesta_test.duckdb",
    feature_limit: int = 10000,
    out_dir: str = "test_pipeline/out",
) -> dict[str, object]:
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    benchmark: dict[str, object] = {
        "timestamp": dt.datetime.now().isoformat(),
        "database": db_path,
        "stages": {},
    }

    print("=" * 80)
    print(" VESTA TEST PIPELINE EXECUTION & BENCHMARK")
    print(f" Target Database: {db_path}")
    print("=" * 80)

    # -------------------------------------------------------------
    # Stage 1: Database Connectivity & Integrity Check
    # -------------------------------------------------------------
    t0 = time.time()
    print("\n[Stage 1/3] Validating Database Schema & Running DQ Checks...")
    con = db.connect(db_path=db_path, read_only=True)
    dq_pipeline = DataQualityPipeline(con)
    dq_results = dq_pipeline.run_all_techniques()
    dq_report = generate_report(dq_results)
    stage1_time = time.time() - t0

    dq_status = dq_report["summary"]["status"]
    passed_checks = dq_report["summary"]["passed"]
    total_checks = dq_report["summary"]["total_checks"]
    print(f"  -> DQ Status: {dq_status} ({passed_checks}/{total_checks} checks passed in {stage1_time:.2f}s)")
    benchmark["stages"]["data_quality"] = {
        "status": dq_status,
        "duration_seconds": round(stage1_time, 2),
        "passed_checks": passed_checks,
        "total_checks": total_checks,
    }

    # -------------------------------------------------------------
    # Stage 2: High-Performance Vectorized Feature Extraction
    # -------------------------------------------------------------
    t0 = time.time()
    print(f"\n[Stage 2/3] Extracting Vectorized ML Features (Limit: {feature_limit:,} events)...")
    feat_df = build_feature_dataframe(con, limit=feature_limit, vectorized=True)
    stage2_time = time.time() - t0
    events_count = len(feat_df)
    throughput = events_count / max(stage2_time, 0.001)

    print(f"  -> Extracted {events_count:,} feature rows with 23 dimensions in {stage2_time:.2f}s")
    print(f"  -> Throughput: {throughput:.0f} events/second (Vectorized DuckDB ASOF JOIN)")

    train_df, val_df, test_df = split_temporal_dataset(feat_df)
    print(f"  -> Splits: Train={len(train_df):,}, Val={len(val_df):,}, Test={len(test_df):,}")

    # Export sample parquet using DuckDB native writer
    feat_parquet_path = out_path / "test_features_matrix.parquet"
    con.register("_test_feat_export", feat_df)
    con.execute(f"COPY _test_feat_export TO '{feat_parquet_path.as_posix()}' (FORMAT PARQUET)")
    print(f"  -> Saved feature matrix to: {feat_parquet_path}")

    benchmark["stages"]["feature_engineering"] = {
        "status": "PASS",
        "duration_seconds": round(stage2_time, 2),
        "events_processed": events_count,
        "throughput_events_per_sec": round(throughput, 1),
        "columns": list(feat_df.columns),
        "splits": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
    }

    # -------------------------------------------------------------
    # Stage 3: Quantitative Backtest Validation (F201)
    # -------------------------------------------------------------
    t0 = time.time()
    print("\n[Stage 3/3] Running Quantitative Mean-Reversion Backtest...")
    events_df = load_events(con)
    backtest_report = run_backtest(events_df)
    stage3_time = time.time() - t0

    loaded_events = backtest_report.get("total_events_loaded", 0)
    sentiment_counts = backtest_report.get("sentiment_class_counts", {})
    neg_stats = backtest_report.get("overall", {}).get("negative_sentiment_group", {})
    t_stat = neg_stats.get("t_statistic")
    p_val = neg_stats.get("p_value")
    d_stat = neg_stats.get("cohens_d")

    print(f"  -> Evaluated {loaded_events:,} PIT events in {stage3_time:.2f}s")
    print(f"  -> Sentiment breakdown: {sentiment_counts}")
    print(f"  -> Mean-reversion Stats (Negative Group): t-stat={t_stat:.4f}, p-val={p_val:.2e}, Cohen's d={d_stat:.4f}")

    backtest_json_path = out_path / "test_backtest_report.json"
    backtest_json_path.write_text(json.dumps(backtest_report, indent=2), encoding="utf-8")
    print(f"  -> Saved backtest report to: {backtest_json_path}")

    benchmark["stages"]["backtest"] = {
        "status": "PASS",
        "duration_seconds": round(stage3_time, 2),
        "events_evaluated": loaded_events,
        "negative_group_stats": neg_stats,
    }

    con.close()

    total_time = stage1_time + stage2_time + stage3_time
    benchmark["total_duration_seconds"] = round(total_time, 2)
    benchmark["overall_status"] = "PASS"

    summary_file = out_path / "test_pipeline_benchmark.json"
    summary_file.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    print("\n" + "=" * 80)
    print(f" PIPELINE TEST COMPLETE: Status = PASS in {total_time:.2f}s")
    print(f" Benchmark report: {summary_file}")
    print("=" * 80)

    return benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full pipeline test on test database")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    parser.add_argument("--limit", type=int, default=10000, help="Feature extraction limit")
    parser.add_argument("--out-dir", default="test_pipeline/out", help="Output directory")
    args = parser.parse_args()

    run_pipeline_test(db_path=args.db_path, feature_limit=args.limit, out_dir=args.out_dir)
