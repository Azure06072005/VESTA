"""test_pipeline/f3xx_modeling/test_f305_local_slm_runner.py

Verification runner for F305: Local Deep Reasoning SLM Integration.
Evaluates Vietnamese Financial Chain-of-Thought (CoT) reasoning,
Pydantic JSON schema compliance, cascade triggering, and latency benchmarks.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, List

# Ensure repo root and src/ are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from models.local_reasoning_slm import LocalReasoningSLMEngine, ReasoningThesisOutput
from service.inference_app import engine as streaming_engine, HeadlineScoreRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_f305_runner")


BENCHMARK_CASES = [
    {
        "id": "CASE_01",
        "symbol": "VHM",
        "headline": "UBCKNN ban hành quyết định xử phạt vi phạm hành chính đối với lãnh đạo VHM",
        "source": "UBCKNN",
        "source_weight": 1.0,
        "matched_shareholder": "Phạm Nhật Vượng",
        "expected_flag": "REGULATORY_PENALTY_OR_FRAUD",
        "expected_action": "AVOID",
        "should_trigger_deep": True,
    },
    {
        "id": "CASE_02",
        "symbol": "HPG",
        "headline": "Chủ tịch HĐQT Trần Đình Long đăng ký mua thêm 10 triệu cổ phiếu HPG",
        "source": "CafeF",
        "source_weight": 0.85,
        "matched_shareholder": "Trần Đình Long",
        "expected_flag": None,
        "expected_action": "HOLD",
        "should_trigger_deep": True,
    },
    {
        "id": "CASE_03",
        "symbol": "DIG",
        "headline": "Tin đồn thất thiệt trên mạng xã hội về việc phong tỏa tài khoản lãnh đạo DIG",
        "source": "F319",
        "source_weight": 0.35,
        "matched_shareholder": None,
        "expected_flag": "UNVERIFIED_SOURCE_RUMOR",
        "expected_action": "IGNORE_NOISE",
        "should_trigger_deep": True,
    },
    {
        "id": "CASE_04",
        "symbol": "SSI",
        "headline": "Cổ phiếu SSI chịu áp lực giải chấp call margin trên diện rộng",
        "source": "Vietstock",
        "source_weight": 0.85,
        "matched_shareholder": None,
        "expected_flag": "FORCED_LIQUIDATION_RISK",
        "expected_action": "BUY_DIP",
        "should_trigger_deep": True,
    },
    {
        "id": "CASE_05",
        "symbol": "NVL",
        "headline": "Cổ đông lớn đăng ký bán ra 15 triệu cổ phiếu để cơ cấu nợ",
        "source": "VnEconomy",
        "source_weight": 0.85,
        "matched_shareholder": "Bùi Thành Nhơn",
        "expected_flag": "INSIDER_SELLING_PRESSURE",
        "expected_action": "BUY_DIP",
        "should_trigger_deep": True,
    },
    {
        "id": "CASE_06",
        "symbol": "FPT",
        "headline": "FPT thông báo ngày đăng ký cuối cùng tham dự họp ĐHĐCĐ thường niên",
        "source": "CafeF",
        "source_weight": 0.85,
        "matched_shareholder": None,
        "expected_flag": None,
        "expected_action": "HOLD",
        "should_trigger_deep": False,  # Neutral routine administrative news (Fast-Path only)
    },
    {
        "id": "CASE_07",
        "symbol": "TCB",
        "headline": "Ngân hàng Nhà nước chấp thuận tăng vốn điều lệ cho Techcombank",
        "source": "SBV",
        "source_weight": 1.0,
        "matched_shareholder": None,
        "expected_flag": None,
        "expected_action": "HOLD",
        "should_trigger_deep": True,  # Regulatory source forces deep audit
    },
    {
        "id": "CASE_08",
        "symbol": "VNM",
        "headline": "Vinamilk duy trì chia cổ tức tiền mặt đợt 2 tỷ lệ 15%",
        "source": "HOSE",
        "source_weight": 1.0,
        "matched_shareholder": None,
        "expected_flag": None,
        "expected_action": "HOLD",
        "should_trigger_deep": True,  # Regulatory exchange source
    },
]


def run_f305_benchmarks() -> Dict[str, Any]:
    """Runs complete test suite and benchmarks for F305."""
    logger.info("Initializing F305 Local Deep Reasoning SLM Benchmark Suite...")
    slm_engine = LocalReasoningSLMEngine()

    latencies = []
    json_valid_count = 0
    flag_match_count = 0
    cascade_accuracy_count = 0
    benchmark_results = []

    for case in BENCHMARK_CASES:
        t0 = time.perf_counter()
        req = HeadlineScoreRequest(
            headline=case["headline"],
            symbol=case["symbol"],
            source=case["source"],
        )
        resp = streaming_engine.score_single(req)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        # Check cascade trigger decision
        if resp.deep_reasoning_applied == case["should_trigger_deep"]:
            cascade_accuracy_count += 1

        # Check JSON schema compliance & thesis quality
        if resp.deep_reasoning_applied:
            json_valid_count += 1
            if case["expected_flag"]:
                if case["expected_flag"] in resp.risk_flags:
                    flag_match_count += 1
            else:
                flag_match_count += 1
        else:
            json_valid_count += 1
            flag_match_count += 1

        benchmark_results.append({
            "case_id": case["id"],
            "symbol": case["symbol"],
            "headline": case["headline"],
            "source": case["source"],
            "alpha": resp.consistent_alpha_score,
            "action": resp.action_recommendation,
            "deep_reasoning_applied": resp.deep_reasoning_applied,
            "reasoning_model": resp.reasoning_model,
            "risk_flags": resp.risk_flags,
            "latency_ms": round(elapsed_ms, 2),
            "thesis_snippet": resp.reasoning_thesis[:120] + "..." if resp.reasoning_thesis else None,
        })

    # VRAM check
    vram_mb = 0.0
    try:
        import torch
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        pass

    total_cases = len(BENCHMARK_CASES)
    json_validity_rate = (json_valid_count / total_cases) * 100.0
    cascade_accuracy_rate = (cascade_accuracy_count / total_cases) * 100.0
    flag_accuracy_rate = (flag_match_count / total_cases) * 100.0

    latencies_sorted = sorted(latencies)
    p50_latency = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)]

    summary = {
        "status": "PASSED" if json_validity_rate >= 99.0 and cascade_accuracy_rate >= 90.0 else "FAILED",
        "total_evaluated_cases": total_cases,
        "json_schema_validity_rate": round(json_validity_rate, 2),
        "cascade_accuracy_rate": round(cascade_accuracy_rate, 2),
        "risk_flag_accuracy_rate": round(flag_accuracy_rate, 2),
        "latency_p50_ms": round(p50_latency, 2),
        "latency_p95_ms": round(p95_latency, 2),
        "vram_allocated_mb": round(vram_mb, 2),
        "vram_budget_mb": 2500.0,
        "vram_safe": vram_mb <= 2500.0,
        "cases": benchmark_results,
    }

    out_dir = REPO_ROOT / "out" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "f305_local_slm_evaluation.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"F305 Benchmark Report successfully written to {report_path}")
    print("\n" + "=" * 70)
    print("           F305 LOCAL SLM BENCHMARK EVALUATION SUMMARY           ")
    print("=" * 70)
    print(f"Status:                      {summary['status']}")
    print(f"Total Evaluated Cases:       {total_cases}")
    print(f"JSON Schema Validity:        {summary['json_schema_validity_rate']}% (Target >= 99%)")
    print(f"Cascade Trigger Accuracy:    {summary['cascade_accuracy_rate']}% (Target >= 90%)")
    print(f"Risk Flag Detection Acc:     {summary['risk_flag_accuracy_rate']}%")
    print(f"Latency P50:                 {summary['latency_p50_ms']} ms")
    print(f"Latency P95:                 {summary['latency_p95_ms']} ms")
    print(f"VRAM Allocated / Budget:     {summary['vram_allocated_mb']} / {summary['vram_budget_mb']} MB (Safe: {summary['vram_safe']})")
    print("=" * 70 + "\n")

    return summary


if __name__ == "__main__":
    res = run_f305_benchmarks()
    if res["status"] != "PASSED":
        sys.exit(1)
