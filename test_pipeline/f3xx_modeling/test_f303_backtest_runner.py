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
import duckdb
from pipeline.backtest_meanreversion import run, run_backtest, write_report


def run_f303_test(
    report_path: str = "out/meanreversion_report_multimodal.json",
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
    dataset_path: str | None = None,
    sample_limit: int | None = None,
) -> dict[str, object]:
    effective_ds = dataset_path or "data/processed/f104_embargo_5d/f104_val.parquet"
    print("=" * 80)
    print(" [F303] MULTIMODAL MEAN-REVERSION STATISTICAL BACKTEST RUNNER")
    print(f" Report Path  : {report_path}")
    print(f" Model Path   : {model_path}")
    print(f" Dataset Path : {effective_ds} (limit={sample_limit or 'ALL'})")
    print("=" * 80)

    if sample_limit and pathlib.Path(effective_ds).exists():
        con = duckdb.connect()
        df_sub = con.execute(f"SELECT * FROM '{effective_ds}' LIMIT {int(sample_limit)}").df()
        con.close()
        report = run_backtest(
            df_sub,
            sentiment_source="multimodal",
            model_path=model_path,
        )
        write_report(report, pathlib.Path(report_path))
    else:
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

    # Display Dynamic Kelly Criterion Sizing Results
    kelly_res = report.get("dynamic_kelly_metrics", {})
    if kelly_res and kelly_res.get("status") == "ok":
        eq = kelly_res.get("equal_weight_portfolio", {})
        kw = kelly_res.get("dynamic_kelly_portfolio", {})
        print("\n [DYNAMIC KELLY CRITERION SIZING TELEMETRY]")
        print(f"  • Base Win-Rate (p)    : {kelly_res.get('base_win_rate_pct', 0.0):.2f}% | Payoff Ratio (b): {kelly_res.get('empirical_payoff_ratio_b', 0.0):.3f}")
        print(f"  • Mean Kelly Weight    : {kelly_res.get('mean_kelly_weight_pct', 0.0):.2f}% (Cap: {kelly_res.get('max_position_cap_pct', 15.0):.1f}%, Half-Kelly: {kelly_res.get('half_kelly_applied')})")
        print(f"  • Equal-Weight Port    : Return = {eq.get('mean_trade_return_pct', 0.0):+.3f}% | Sharpe = {eq.get('annualized_sharpe', 0.0):.4f} | Max DD = {eq.get('max_drawdown_pct', 0.0):.2f}%")
        print(f"  • Dynamic Kelly Port   : Return = {kw.get('mean_trade_return_pct', 0.0):+.3f}% | Sharpe = {kw.get('annualized_sharpe', 0.0):.4f} | Max DD = {kw.get('max_drawdown_pct', 0.0):.2f}%")
        print(f"  • Sharpe Boost Ratio   : {kelly_res.get('sharpe_improvement_ratio', 1.0):.3f}x ({kelly_res.get('sharpe_improvement_pct', 0.0):+.2f}%)")
        tiers = kelly_res.get("conviction_tiers", {})
        if tiers:
            print("  • Conviction Tiers     :")
            for tier_name, t_data in tiers.items():
                print(f"    - {tier_name:24s}: n={t_data.get('n', 0):>5d} | Avg Weight={t_data.get('mean_weight_pct', 0.0):>5.2f}% | WinRate={t_data.get('win_rate_pct', 0.0):>5.2f}% | Ret={t_data.get('mean_return_pct', 0.0):>+6.3f}%")

    status = "PASS" if beats_baseline and observed_d > baseline_d else "FAIL"
    print(f"\n  -> Execution Status    : {status}")
    print("=" * 80)
    return {"status": status, "report": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F303 multimodal backtest runner")
    parser.add_argument("--report", default="out/meanreversion_report_multimodal.json")
    parser.add_argument("--model-path", default="out/models/multimodal_fusion/best_model.pt")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Sample limit for fast validation")
    args = parser.parse_args()

    run_f303_test(args.report, args.model_path, args.dataset, sample_limit=args.limit)
