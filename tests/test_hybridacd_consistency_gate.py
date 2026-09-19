"""tests/test_hybridacd_consistency_gate.py

Unit tests for F304: HybridACD Token-Constrained Decoding Consistency Gate.
Tests mathematical guarantees, V-FAN latency, Brier calibration, and noise filtering.
"""
from __future__ import annotations

import time
import numpy as np
import pytest

from pipeline.f3xx_modeling.hybridacd_gate import (
    HybridACDConsistencyGate,
    VietnameseFinancialFastAdversarialNegator,
    FINANCIAL_ANTONYM_PAIRS,
)


def test_vfan_antonym_negation():
    """Verify that V-FAN accurately performs domain financial antonym swaps."""
    negator = VietnameseFinancialFastAdversarialNegator()

    # Test Case 1: Lỗ kỷ lục -> Lãi kỷ lục
    h1 = "Doanh nghiệp báo lỗ kỷ lục trong quý 3"
    n1 = negator.negate(h1)
    assert "lãi kỷ lục" in n1.lower()

    # Test Case 2: Tăng trưởng âm -> Tăng trưởng bứt phá
    h2 = "Ngành bất động sản ghi nhận tăng trưởng âm năm 2022"
    n2 = negator.negate(h2)
    assert "tăng trưởng bứt phá" in n2.lower()

    # Test Case 3: Bán ròng -> Mua ròng
    h3 = "Khối ngoại bán ròng hơn 1000 tỷ đồng"
    n3 = negator.negate(h3)
    assert "mua ròng" in n3.lower()

    # Test Case 4: Nợ xấu gia tăng -> Nợ xấu giảm mạnh
    h4 = "Nhiều ngân hàng lo ngại nợ xấu gia tăng"
    n4 = negator.negate(h4)
    assert "nợ xấu giảm mạnh" in n4.lower()


def test_vfan_latency_budget():
    """Verify that V-FAN operates in micro-latency (< 0.5ms per headline)."""
    negator = VietnameseFinancialFastAdversarialNegator()
    sample_headlines = [
        "Lợi nhuận sau thuế giảm sâu do chi phí tài chính tăng vọt",
        "Khối ngoại xả hàng quyết liệt trên sàn HOSE",
        "Ngân hàng Nhà nước hạ trần lãi suất huy động",
        "Thanh khoản thị trường tuột dốc không phanh",
        "Cổ phiếu VND bị bán tháo sau tin đồn thất thiệt",
    ] * 200  # 1,000 headlines

    t0 = time.perf_counter()
    for h in sample_headlines:
        _ = negator.negate(h)
    duration = time.perf_counter() - t0
    avg_latency_ms = (duration / len(sample_headlines)) * 1000.0

    print(f"\n -> V-FAN Average Latency: {avg_latency_ms:.4f} ms/headline")
    assert avg_latency_ms < 0.5, f"V-FAN latency exceeded 0.5ms: {avg_latency_ms:.4f}ms"


def test_simplex_tcd_mathematical_guarantee():
    """Verify Kolmogorov axiomatic equality:
    p*_pos(T) == q*_neg(~T), p*_neg(T) == q*_pos(~T), and sum(p*) == 1.0.
    """
    gate = HybridACDConsistencyGate(noise_threshold=0.40)

    # Synthetic arbitrary input distributions
    rng = np.random.default_rng(seed=42)
    for _ in range(50):
        # Raw unnormalized random vectors
        p_raw = rng.uniform(0.1, 0.9, size=3)
        q_raw = rng.uniform(0.1, 0.9, size=3)

        p_star, q_star, violation = gate.project_simplex_pair(p_raw, q_raw)

        # 1. Axiomatic equality check
        # Index 0: Neg, 1: Neu, 2: Pos
        assert p_star[2] == pytest.approx(q_star[0], abs=1e-6), "p*_pos must equal q*_neg"
        assert p_star[0] == pytest.approx(q_star[2], abs=1e-6), "p*_neg must equal q*_pos"
        assert p_star[1] == pytest.approx(q_star[1], abs=1e-6), "p*_neu must equal q*_neu"

        # 2. Probability simplex normalization
        assert np.sum(p_star) == pytest.approx(1.0, abs=1e-6), "Sum of p_star must be 1.0"
        assert np.sum(q_star) == pytest.approx(1.0, abs=1e-6), "Sum of q_star must be 1.0"

        # 3. Non-negativity
        assert np.all(p_star >= 0.0), "Probabilities must be non-negative"
        assert np.all(q_star >= 0.0), "Probabilities must be non-negative"


def test_noise_threshold_and_confidence_penalty():
    """Verify that severely inconsistent / hallucinatory predictions are penalized."""
    gate = HybridACDConsistencyGate(noise_threshold=0.35, discard_inconsistent=True)

    headline = "Cổ phiếu HPX bị đình chỉ giao dịch"
    # Perfectly consistent pair:
    # Orig: Neg=0.85, Neu=0.10, Pos=0.05
    # Negated: Neg=0.05, Neu=0.10, Pos=0.85
    p_good = np.array([0.85, 0.10, 0.05])
    q_good = np.array([0.05, 0.10, 0.85])
    res_good = gate.evaluate_event(headline, p_good, q_good)

    assert res_good.is_consistent is True
    assert res_good.violation_score < 0.10
    assert res_good.confidence_weight > 0.80

    # Highly inconsistent hallucination:
    # Model hallucinated high Pos for BOTH headline and negated headline
    p_bad = np.array([0.10, 0.10, 0.80])
    q_bad = np.array([0.10, 0.10, 0.80])
    res_bad = gate.evaluate_event(headline, p_bad, q_bad)

    assert res_bad.is_consistent is False
    assert res_bad.violation_score > 0.35
    assert res_bad.confidence_weight == 0.0  # Discarded


def test_brier_calibration_improvement():
    """Verify that Simplex-TCD projection reduces Brier calibration error on noisy models."""
    gate = HybridACDConsistencyGate()

    # Ground truth: 100 binary events (0: Negative / Down, 1: Positive / Up)
    rng = np.random.default_rng(seed=123)
    y_true = rng.choice([0, 1], size=200)

    # Simulated imperfect model predictions with random linguistic noise
    raw_preds_orig = []
    raw_preds_neg = []
    projected_preds = []

    for y in y_true:
        # Base true probability with noise
        base_p = 0.80 if y == 1 else 0.20
        noise_orig = rng.normal(0, 0.15)
        noise_neg = rng.normal(0, 0.15)

        p_pos = np.clip(base_p + noise_orig, 0.05, 0.95)
        p_neg = 1.0 - p_pos
        p_raw = np.array([p_neg, 0.0, p_pos])

        q_neg = np.clip(base_p + noise_neg, 0.05, 0.95)
        q_pos = 1.0 - q_neg
        q_raw = np.array([q_neg, 0.0, q_pos])

        p_star, _, _ = gate.project_simplex_pair(p_raw, q_raw)

        raw_preds_orig.append(p_pos)
        raw_preds_neg.append(1.0 - q_neg)
        projected_preds.append(p_star[2])  # p*_pos

    # Compute Brier Score: MSE(p_pos, y_true)
    brier_raw = np.mean((np.array(raw_preds_orig) - y_true) ** 2)
    brier_projected = np.mean((np.array(projected_preds) - y_true) ** 2)

    print(f"\n -> Raw Model Brier Score      : {brier_raw:.4f}")
    print(f" -> Projected Model Brier Score: {brier_projected:.4f}")
    assert brier_projected <= brier_raw, (
        f"Simplex projection should not degrade Brier score: {brier_projected} vs {brier_raw}"
    )
