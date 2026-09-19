"""test_pipeline/f3xx_modeling/test_f304_hybridacd_runner.py

Runner for F304: HybridACD Token-Constrained Decoding Consistency Gate Integration.
Verifies:
1. Mathematical Kolmogorov Axiomatic Guarantees: p*_pos == q*_neg, sum(p*) == 1.0.
2. V-FAN Sub-Millisecond Latency Benchmark (< 0.5ms / headline).
3. Brier Calibration Error Improvement under Simplex-TCD projection.
4. Alpha Preservation & Noise Filtering: Backtest with consistency gate confirms
   Cohen's d >= baseline F201 (0.0557) and filters uninformative headline noise.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import numpy as np

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from pipeline.f3xx_modeling.hybridacd_gate import (
    HybridACDConsistencyGate,
    VietnameseFinancialFastAdversarialNegator,
)
from pipeline.backtest_meanreversion import run


def run_f304_verification(
    report_path: str = "out/f304_hybridacd_gate_report.json",
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
    dataset_path: str | None = None,
    noise_threshold: float = 0.40,
) -> dict[str, object]:
    print("=" * 80)
    print(" [F304] HYBRIDACD CONSISTENCY GATE & MULTIMODAL INTEGRATION RUNNER")
    print(f" Report Path      : {report_path}")
    print(f" Model Path       : {model_path}")
    print(f" Dataset Path     : {dataset_path or 'data/processed/f104/f104_val.parquet'}")
    print(f" Noise Threshold  : {noise_threshold}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Mathematical Guarantee Check
    # -------------------------------------------------------------------------
    print("\n[Phase 1/4] Checking Mathematical Kolmogorov Axiomatic Guarantees...")
    gate = HybridACDConsistencyGate(noise_threshold=noise_threshold)
    rng = np.random.default_rng(seed=42)
    max_err_pos = 0.0
    max_err_neg = 0.0
    max_err_sum = 0.0

    for _ in range(100):
        p_raw = rng.uniform(0.01, 1.0, size=3)
        q_raw = rng.uniform(0.01, 1.0, size=3)
        p_star, q_star, _ = gate.project_simplex_pair(p_raw, q_raw)

        # p*_pos == q*_neg
        err_pos = abs(p_star[2] - q_star[0])
        # p*_neg == q*_pos
        err_neg = abs(p_star[0] - q_star[2])
        # sum == 1.0
        err_sum = abs(np.sum(p_star) - 1.0)

        max_err_pos = max(max_err_pos, err_pos)
        max_err_neg = max(max_err_neg, err_neg)
        max_err_sum = max(max_err_sum, err_sum)

    math_pass = (max_err_pos < 1e-5) and (max_err_neg < 1e-5) and (max_err_sum < 1e-5)
    print(f"  -> Max |p*_pos - q*_neg| Error : {max_err_pos:.2e} (Pass: {max_err_pos < 1e-5})")
    print(f"  -> Max |p*_neg - q*_pos| Error : {max_err_neg:.2e} (Pass: {max_err_neg < 1e-5})")
    print(f"  -> Max |sum(p*) - 1.0|   Error : {max_err_sum:.2e} (Pass: {max_err_sum < 1e-5})")
    print(f"  -> Axiomatic Guarantee Status   : {'PASS' if math_pass else 'FAIL'}")

    # -------------------------------------------------------------------------
    # 2. V-FAN Micro-Latency Benchmark
    # -------------------------------------------------------------------------
    print("\n[Phase 2/4] Benchmarking V-FAN Counterfactual Negation Latency...")
    negator = gate.negator
    test_headlines = [
        "Lợi nhuận sau thuế của VCB tăng vọt trong quý 2",
        "Khối ngoại xả hàng quyết liệt trên sàn HOSE",
        "Doanh nghiệp báo lỗ kỷ lục trong quý 3 do chi phí tài chính",
        "Ngành bất động sản ghi nhận tăng trưởng âm năm 2022",
        "Cổ phiếu VND bị bán tháo sau tin đồn thất thiệt",
    ] * 200  # 1,000 headlines

    t0 = time.perf_counter()
    for h in test_headlines:
        _ = negator.negate(h)
    vfan_latency_ms = ((time.perf_counter() - t0) / len(test_headlines)) * 1000.0
    vfan_pass = vfan_latency_ms < 0.50
    print(f"  -> Benchmarked Sample Size      : {len(test_headlines):,} headlines")
    print(f"  -> Average V-FAN Latency        : {vfan_latency_ms:.4f} ms (Budget: < 0.5000 ms)")
    print(f"  -> V-FAN Latency Status         : {'PASS' if vfan_pass else 'FAIL'}")

    # -------------------------------------------------------------------------
    # 3. Brier Calibration Score Comparison
    # -------------------------------------------------------------------------
    print("\n[Phase 3/4] Evaluating Brier Score Calibration...")
    y_true = rng.choice([0, 1], size=500)
    raw_p_list = []
    cons_p_list = []

    for y in y_true:
        base_p = 0.85 if y == 1 else 0.15
        p_raw = np.array([1.0 - np.clip(base_p + rng.normal(0, 0.15), 0.05, 0.95), 0.0, np.clip(base_p + rng.normal(0, 0.15), 0.05, 0.95)])
        q_raw = np.array([np.clip(base_p + rng.normal(0, 0.15), 0.05, 0.95), 0.0, 1.0 - np.clip(base_p + rng.normal(0, 0.15), 0.05, 0.95)])
        p_star, _, _ = gate.project_simplex_pair(p_raw, q_raw)
        raw_p_list.append(p_raw[2])
        cons_p_list.append(p_star[2])

    brier_raw = float(np.mean((np.array(raw_p_list) - y_true) ** 2))
    brier_cons = float(np.mean((np.array(cons_p_list) - y_true) ** 2))
    brier_pass = brier_cons <= brier_raw
    brier_improvement_pct = ((brier_raw - brier_cons) / brier_raw) * 100.0
    print(f"  -> Raw Prediction Brier Score   : {brier_raw:.4f}")
    print(f"  -> Gated Prediction Brier Score : {brier_cons:.4f} ({brier_improvement_pct:+.2f}% improvement)")
    print(f"  -> Calibration Status           : {'PASS' if brier_pass else 'FAIL'}")

    # -------------------------------------------------------------------------
    # 4. Multimodal Backtest Integration with Consistency Gating
    # -------------------------------------------------------------------------
    print("\n[Phase 4/4] Executing Multimodal Mean-Reversion Backtest with Consistency Gate...")
    backtest_report = run(
        report_path="out/meanreversion_report_f304_hybridacd.json",
        sentiment_source="multimodal",
        model_path=model_path,
        dataset_path=dataset_path,
        use_consistency_gate=True,
        noise_threshold=noise_threshold,
    )

    baseline_d = backtest_report.get("baseline_f201_cohens_d", 0.0557)
    observed_d = backtest_report.get("cohens_d", 0.0)
    beats_baseline = backtest_report.get("beats_baseline", False)
    total_events = backtest_report.get("total_events_loaded", 0)
    neg_stats = backtest_report.get("overall", {}).get("negative_sentiment_group", {})
    gate_metrics = backtest_report.get("consistency_gate_metrics", {})

    print(f"  -> Total Events Loaded          : {total_events:,}")
    print(f"  -> Consistent Events Passed     : {gate_metrics.get('consistent_events', 0):,}")
    print(f"  -> Inconsistent Events Filtered : {gate_metrics.get('inconsistent_events_filtered', 0):,}")
    print(f"  -> Mean Consistency Violation   : {gate_metrics.get('mean_violation', 0.0):.4f}")
    print(f"  -> Gated Negative Sample (n)    : {neg_stats.get('n', 0):,}")
    print(f"  -> Mean T+5 Return              : {neg_stats.get('mean_return_t5', 0.0):+.4f}")
    print(f"  -> Mean T+30 Return             : {neg_stats.get('mean_return_t30', 0.0):+.4f}")
    print(f"  -> Paired t-statistic           : {neg_stats.get('t_statistic', 0.0):.4f}")
    print(f"  -> p-value                      : {neg_stats.get('p_value', 1.0):.2e}")
    print(f"  -> Observed Cohen's d           : {observed_d:.4f} (Baseline F201: {baseline_d:.4f})")
    print(f"  -> Beats Baseline?              : {beats_baseline} ({backtest_report.get('effect_size_improvement_ratio', 0.0):.2f}x)")

    backtest_pass = beats_baseline and observed_d > baseline_d
    overall_status = "PASS" if (math_pass and vfan_pass and brier_pass and backtest_pass) else "FAIL"

    summary_result = {
        "status": str(overall_status),
        "math_guarantee_pass": bool(math_pass),
        "vfan_latency_ms": float(round(vfan_latency_ms, 4)),
        "vfan_latency_pass": bool(vfan_pass),
        "brier_raw": float(round(brier_raw, 4)),
        "brier_consistent": float(round(brier_cons, 4)),
        "brier_improvement_pct": float(round(brier_improvement_pct, 2)),
        "brier_pass": bool(brier_pass),
        "cohens_d": float(round(observed_d, 4)),
        "baseline_cohens_d": float(baseline_d),
        "beats_baseline": bool(beats_baseline),
        "effect_size_improvement_ratio": float(backtest_report.get("effect_size_improvement_ratio", 0.0)),
        "total_events_loaded": int(total_events),
        "consistent_events": int(gate_metrics.get("consistent_events", 0)),
        "inconsistent_filtered": int(gate_metrics.get("inconsistent_events_filtered", 0)),
        "mean_violation": float(gate_metrics.get("mean_violation", 0.0)),
        "backtest_report": backtest_report,
    }

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.bool_, bool)):
                return bool(obj)
            if isinstance(obj, (np.integer, int)):
                return int(obj)
            if isinstance(obj, (np.floating, float)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    out_p = pathlib.Path(report_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(summary_result, indent=2, ensure_ascii=False, cls=NumpyEncoder), encoding="utf-8")

    print("\n" + "=" * 80)
    print(f" [F304] OVERALL EXECUTION STATUS : {overall_status}")
    print(f" Report successfully saved to    : {report_path}")
    print("=" * 80)

    return summary_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F304 HybridACD Consistency Gate runner")
    parser.add_argument("--report", default="out/f304_hybridacd_gate_report.json")
    parser.add_argument("--model-path", default="out/models/multimodal_fusion/best_model.pt")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--noise-threshold", type=float, default=0.40)
    args = parser.parse_args()

    run_f304_verification(
        report_path=args.report,
        model_path=args.model_path,
        dataset_path=args.dataset,
        noise_threshold=args.noise_threshold,
    )
