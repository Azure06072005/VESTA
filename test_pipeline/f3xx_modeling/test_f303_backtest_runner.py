"""test_pipeline/f3xx_modeling/test_f303_backtest_runner.py

Runner for F303: Multimodal Mean-Reversion Backtest Benchmark.
Executes paired t-test on multimodal forward returns, checks Cohen's d against F201 baseline (0.0557).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from pipeline.backtest_meanreversion import run


def run_f303_test(
    report_path: str = "out/meanreversion_report_multimodal.json",
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
    dataset_path: str | None = None,
) -> dict[str, object]:
    print("=" * 80)
    print(" [F303] MULTIMODAL MEAN-REVERSION STATISTICAL BACKTEST RUNNER")
    print(f" Report Path  : {report_path}")
    print(f" Model Path   : {model_path}")
    print(f" Dataset Path : {dataset_path or 'data/processed/f104/f104_val.parquet'}")
    print("=" * 80)

    report = run(
        report_path=report_path,
        sentiment_source="multimodal",
        model_path=model_path,
        dataset_path=dataset_path,
    )

    baseline_d = report.get("baseline_f201_cohens_d", 0.0557)
    observed_d = report.get("cohens_d", 0.0)
    beats_baseline = report.get("beats_baseline", False)
    total_events = report.get("total_events_loaded", 0)
    neg_stats = report.get("overall", {}).get("negative_sentiment_group", {})

    print(f"  -> Total Events Scored : {total_events:,}")
    print(f"  -> Negative Sample (n) : {neg_stats.get('n', 0):,}")
    print(f"  -> Mean T+5 Return     : {neg_stats.get('mean_return_t5', 0.0):+.4f}")
    print(f"  -> Mean T+30 Return    : {neg_stats.get('mean_return_t30', 0.0):+.4f}")
    print(f"  -> Paired t-statistic  : {neg_stats.get('t_statistic', 0.0):.4f}")
    print(f"  -> p-value             : {neg_stats.get('p_value', 1.0):.2e}")
    print(f"  -> Observed Cohen's d  : {observed_d:.4f} (Baseline: {baseline_d:.4f})")
    print(f"  -> Beats Baseline?     : {beats_baseline} ({report.get('effect_size_improvement_ratio', 0.0):.2f}x)")

    status = "PASS" if beats_baseline and observed_d > baseline_d else "FAIL"
    print(f"  -> Execution Status    : {status}")
    print("=" * 80)
    return {"status": status, "report": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F303 multimodal backtest runner")
    parser.add_argument("--report", default="out/meanreversion_report_multimodal.json")
    parser.add_argument("--model-path", default="out/models/multimodal_fusion/best_model.pt")
    parser.add_argument("--dataset", default=None)
    args = parser.parse_args()

    run_f303_test(args.report, args.model_path, args.dataset)
