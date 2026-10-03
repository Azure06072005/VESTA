"""tests/test_hybridacd_10_checkers.py

Unit tests for F304+: Full 10-Checker Kolmogorov Consistency Framework.
Tests all 10 mathematical checkers, multi-relational tuple generator, and
the unified FullKolmogorovFinancialEngine.
"""
from __future__ import annotations

import pathlib
import sys
import numpy as np
import pytest

root_src = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(root_src) not in sys.path:
    sys.path.insert(0, str(root_src))

from pipeline.f3xx_modeling.hybridacd_multi_checkers import (

    FinancialNegChecker,
    FinancialAndChecker,
    FinancialOrChecker,
    FinancialAndOrChecker,
    FinancialButChecker,
    FinancialCondChecker,
    FinancialCondCondChecker,
    FinancialConsequenceChecker,
    FinancialExpectedEvidenceChecker,
    FinancialParaphraseChecker,
    FinancialMultiTupleGenerator,
    FullKolmogorovFinancialEngine,
)
from pipeline.f3xx_modeling.hybridacd_gate import HybridACDConsistencyGate


def test_10_checkers_mathematical_bounds():
    """Verify core boundary conditions and mathematical behavior for each of the 10 checkers."""
    # 1. NegChecker: p*_pos == q*_neg
    p = np.array([0.70, 0.10, 0.20])
    q_consistent = np.array([0.20, 0.10, 0.70])
    q_inconsistent = np.array([0.80, 0.10, 0.10])
    assert FinancialNegChecker.evaluate(p, q_consistent) == pytest.approx(0.0, abs=1e-5)
    assert FinancialNegChecker.evaluate(p, q_inconsistent) > 0.50

    # 2. AndChecker: Fréchet conjunction bounds max(0, Pa+Pb-1) <= P_and <= min(Pa, Pb)
    p_a, p_b = 0.60, 0.70  # lower=0.30, upper=0.60
    assert FinancialAndChecker.evaluate(p_a, p_b, 0.45) == 0.0
    assert FinancialAndChecker.evaluate(p_a, p_b, 0.10) > 0.0  # below lower bound
    assert FinancialAndChecker.evaluate(p_a, p_b, 0.80) > 0.0  # above upper bound

    # 3. OrChecker: Fréchet disjunction bounds max(Pa, Pb) <= P_or <= min(1, Pa+Pb)
    # max=0.70, min=1.0
    assert FinancialOrChecker.evaluate(p_a, p_b, 0.85) == 0.0
    assert FinancialOrChecker.evaluate(p_a, p_b, 0.50) > 0.0  # below lower bound

    # 4. AndOrChecker: P(A and B) + P(A or B) == P(A) + P(B)
    assert FinancialAndOrChecker.evaluate(0.40, 0.50, 0.20, 0.70) == pytest.approx(0.0, abs=1e-5)
    assert FinancialAndOrChecker.evaluate(0.40, 0.50, 0.10, 0.70) > 0.05

    # 5. ButChecker: P(Neg | A but B) >= P(Neg | A)
    assert FinancialButChecker.evaluate(0.30, 0.45) == 0.0
    assert FinancialButChecker.evaluate(0.50, 0.20) > 0.20

    # 6. CondChecker: P(A | B) * P(B) == P(A and B)
    assert FinancialCondChecker.evaluate(0.50, 0.60, 0.30) == pytest.approx(0.0, abs=1e-5)
    assert FinancialCondChecker.evaluate(0.50, 0.60, 0.10) > 0.10

    # 7. CondCondChecker: Total probability across macro regimes
    # P(A|C) = P(A|B,C)*P(B|C) + P(A|~B,C)*(1 - P(B|C))
    # 0.45 = 0.60 * 0.50 + 0.30 * 0.50 = 0.30 + 0.15 = 0.45
    assert FinancialCondCondChecker.evaluate(0.45, 0.60, 0.50, 0.30) == pytest.approx(0.0, abs=1e-5)
    assert FinancialCondCondChecker.evaluate(0.80, 0.60, 0.50, 0.30) > 0.20

    # 8. ConsequenceChecker: A => B implies P(A) <= P(B)
    assert FinancialConsequenceChecker.evaluate(0.30, 0.60) == 0.0
    assert FinancialConsequenceChecker.evaluate(0.70, 0.40) == pytest.approx(0.30, abs=1e-5)

    # 9. ExpectedEvidenceChecker: E_E[P(A|E)] == P(A)
    # 0.50 = 0.70 * 0.5 + 0.30 * 0.5 = 0.50
    assert FinancialExpectedEvidenceChecker.evaluate(0.50, 0.70, 0.50, 0.30, 0.50) == pytest.approx(0.0, abs=1e-5)

    # 10. ParaphraseChecker: || p_orig - p_para ||_1
    p1 = np.array([0.20, 0.10, 0.70])
    p2 = np.array([0.21, 0.09, 0.70])
    assert FinancialParaphraseChecker.evaluate(p1, p2) < 0.05


def test_financial_multi_tuple_generator():
    """Verify that multi-relational tuple generator correctly produces financial phrases."""
    tuple_gen = FinancialMultiTupleGenerator()

    headline = "Khối ngoại bán ròng hơn 1000 tỷ đồng"
    # Negation
    neg = tuple_gen.generate_negation(headline)
    assert "mua ròng" in neg.lower()

    # Paraphrase
    para = tuple_gen.generate_paraphrase(headline)
    assert "nhà đầu tư nước ngoài xả hàng" in para.lower()

    # Concessive But
    but = tuple_gen.generate_concessive_but(headline)
    assert "nhưng" in but.lower()

    # Consequence
    cause, effect = tuple_gen.generate_consequence("Doanh nghiệp bị đình chỉ giao dịch vì vi phạm công bố thông tin")
    assert "nguy cơ bán tháo" in effect.lower()


def test_full_kolmogorov_engine_audit():
    """Verify FullKolmogorovFinancialEngine produces valid MultiCheckerReport and KCI."""
    engine = FullKolmogorovFinancialEngine(tolerance=0.20)

    # Simulated perfectly consistent prediction function
    def dummy_consistent_predict(texts: list[str]) -> np.ndarray:
        results = []
        for t in texts:
            t_low = t.lower()
            if "mua ròng" in t_low or "lãi" in t_low or "bứt phá" in t_low:
                results.append([0.05, 0.15, 0.80])  # Positive
            elif "bán ròng" in t_low or "lỗ" in t_low or "đình chỉ" in t_low:
                results.append([0.80, 0.15, 0.05])  # Negative
            else:
                results.append([0.20, 0.60, 0.20])  # Neutral
        return np.array(results)

    headline = "Doanh nghiệp báo lỗ kỷ lục trong quý 3"
    report, kci = engine.evaluate_headline_coherence(headline, dummy_consistent_predict)

    assert report.total_checks_evaluated == 10
    assert 0.0 <= kci <= 1.0
    assert report.mean_violation_score >= 0.0
    assert isinstance(report.checker_violations, dict)
    assert len(report.checker_violations) == 10


def test_hybridacd_gate_multi_checker_mode():
    """Verify HybridACDConsistencyGate multi_checker_mode integration."""
    gate = HybridACDConsistencyGate(multi_checker_mode=True, noise_threshold=0.45)

    def dummy_predict(texts: list[str]) -> np.ndarray:
        # Returns consistent probabilities
        res = []
        for t in texts:
            if "không" in t.lower() or "mua ròng" in t.lower():
                res.append([0.05, 0.10, 0.85])
            else:
                res.append([0.85, 0.10, 0.05])
        return np.array(res)

    res = gate.evaluate_event_multi("Khối ngoại bán ròng kỷ lục trên sàn HOSE", dummy_predict)

    assert res.kolmogorov_coherence_index is not None
    assert 0.0 <= res.kolmogorov_coherence_index <= 1.0
    assert res.multi_checker_report is not None
    assert res.multi_checker_report.total_checks_evaluated == 10
    assert res.consistent_alpha_score < 45.0  # Strong negative mean-reversion score
