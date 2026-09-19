"""src/pipeline/f3xx_modeling/hybridacd_multi_checkers.py

Feature F304+: Full 10-Checker Kolmogorov Consistency Framework for VESTA.
Directly adapts and formalizes the 10 static consistency checkers from HybridACD
(d:\\HybridACD\\consistency-forecasting\\src\\static_checks\\Checker.py) into the
multimodal financial probability simplex and Vietnamese equity market context.

The 10 Financial Consistency Checkers:
1.  FinancialNegChecker: Axiomatic inversion P(Pos | T) == P(Neg | ~T) via V-FAN.
2.  FinancialAndChecker: Fréchet conjunction bounds P(A and B).
3.  FinancialOrChecker: Fréchet disjunction bounds P(A or B).
4.  FinancialAndOrChecker: Probability mass identity P(A and B) + P(A or B) == P(A) + P(B).
5.  FinancialButChecker: Concessive financial clause evaluation ("A nhưng B").
6.  FinancialCondChecker: Bayes theorem consistency P(A | B) * P(B) == P(A and B).
7.  FinancialCondCondChecker: Regime-conditional transitivity across market regimes C.
8.  FinancialConsequenceChecker: Implication monotonicity (A => B entails P(A) <= P(B)).
9.  FinancialExpectedEvidenceChecker: Law of total expectation over disclosures E.
10. FinancialParaphraseChecker: Semantic invariance under financial paraphrasing.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Dict, List, Optional, Tuple, Union
import numpy as np


@dataclasses.dataclass
class MultiCheckerReport:
    """Summary of 10-checker Kolmogorov audit for a financial model / headline."""
    total_checks_evaluated: int
    passed_checks: int
    failed_checks: int
    mean_violation_score: float
    checker_violations: Dict[str, float]
    is_fully_consistent: bool


class FinancialNegChecker:
    """Checker 1: Negation Complementarity: P(Pos|T) == P(Neg|~T)."""
    name = "NegChecker"

    @staticmethod
    def evaluate(p_orig: np.ndarray, q_neg: np.ndarray) -> float:
        """p, q in Delta^2: [p_neg, p_neu, p_pos]. Violation in [0, 2]."""
        p_neg, p_neu, p_pos = p_orig[0], p_orig[1], p_orig[2]
        q_neg_val, q_neu, q_pos = q_neg[0], q_neg[1], q_neg[2]
        violation = abs(p_pos - q_neg_val) + abs(p_neg - q_pos) + 0.5 * abs(p_neu - q_neu)
        return float(violation)


class FinancialAndChecker:
    """Checker 2: Fréchet bounds for Conjunction: max(0, P(A)+P(B)-1) <= P(A and B) <= min(P(A), P(B))."""
    name = "AndChecker"

    @staticmethod
    def evaluate(p_a: float, p_b: float, p_and: float) -> float:
        lower_bound = max(0.0, p_a + p_b - 1.0)
        upper_bound = min(p_a, p_b)
        violation = 0.0
        if p_and < lower_bound:
            violation = lower_bound - p_and
        elif p_and > upper_bound:
            violation = p_and - upper_bound
        return float(violation)


class FinancialOrChecker:
    """Checker 3: Fréchet bounds for Disjunction: max(P(A), P(B)) <= P(A or B) <= min(1, P(A)+P(B))."""
    name = "OrChecker"

    @staticmethod
    def evaluate(p_a: float, p_b: float, p_or: float) -> float:
        lower_bound = max(p_a, p_b)
        upper_bound = min(1.0, p_a + p_b)
        violation = 0.0
        if p_or < lower_bound:
            violation = lower_bound - p_or
        elif p_or > upper_bound:
            violation = p_or - upper_bound
        return float(violation)


class FinancialAndOrChecker:
    """Checker 4: Additivity Identity: P(A and B) + P(A or B) == P(A) + P(B)."""
    name = "AndOrChecker"

    @staticmethod
    def evaluate(p_a: float, p_b: float, p_and: float, p_or: float) -> float:
        lhs = p_and + p_or
        rhs = p_a + p_b
        return float(abs(lhs - rhs))


class FinancialButChecker:
    """Checker 5: Concessive financial clause (e.g. 'Doanh thu tăng mạnh nhưng nợ xấu tăng vọt').
    In finance, the concessive clause 'nhưng B' carries primary decision weight over 'A'.
    Checks if P(Neg | A but B) >= P(Neg | A).
    """
    name = "ButChecker"

    @staticmethod
    def evaluate(p_neg_a: float, p_neg_a_but_b: float) -> float:
        # If B is negative, P(Neg | A but B) should not be strictly lower than P(Neg | A)
        if p_neg_a_but_b < p_neg_a - 0.05:
            return float(p_neg_a - p_neg_a_but_b)
        return 0.0


class FinancialCondChecker:
    """Checker 6: Conditional Multiplication Rule: P(A | B) * P(B) == P(A and B)."""
    name = "CondChecker"

    @staticmethod
    def evaluate(p_a_given_b: float, p_b: float, p_and: float) -> float:
        lhs = p_a_given_b * p_b
        return float(abs(lhs - p_and))


class FinancialCondCondChecker:
    """Checker 7: Bayesian Law of Total Probability conditioning across macro regime C:
    P(A | C) == P(A | B, C) * P(B | C) + P(A | ~B, C) * P(~B | C).
    """
    name = "CondCondChecker"

    @staticmethod
    def evaluate(
        p_a_given_c: float,
        p_a_given_b_c: float,
        p_b_given_c: float,
        p_a_given_not_b_c: float,
    ) -> float:
        p_not_b_given_c = 1.0 - p_b_given_c
        rhs = p_a_given_b_c * p_b_given_c + p_a_given_not_b_c * p_not_b_given_c
        return float(abs(p_a_given_c - rhs))


class FinancialConsequenceChecker:
    """Checker 8: Monotonicity under Implication: If Corporate Fact A implies Market Consequence B,
    then P(A) <= P(B).
    Example: A = 'Doanh nghiệp bị đình chỉ giao dịch', B = 'Cổ phiếu giảm điểm'.
    """
    name = "ConsequenceChecker"

    @staticmethod
    def evaluate(p_cause_a: float, p_effect_b: float) -> float:
        if p_cause_a > p_effect_b:
            return float(p_cause_a - p_effect_b)
        return 0.0


class FinancialExpectedEvidenceChecker:
    """Checker 9: Law of Total Expectation for forthcoming financial disclosure E:
    E_{E}[P(A | E)] == P(A).
    """
    name = "ExpectedEvidenceChecker"

    @staticmethod
    def evaluate(
        p_prior: float,
        p_given_bull_evidence: float,
        prob_bull: float,
        p_given_bear_evidence: float,
        prob_bear: float,
    ) -> float:
        expected_posterior = p_given_bull_evidence * prob_bull + p_given_bear_evidence * prob_bear
        return float(abs(p_prior - expected_posterior))


class FinancialParaphraseChecker:
    """Checker 10: Semantic Invariance: Two syntactically distinct headlines reporting
    the exact same financial truth must have identical probability vectors:
    || p(Headline_1) - p(Headline_2) ||_1 <= tolerance.
    """
    name = "ParaphraseChecker"

    @staticmethod
    def evaluate(p_orig: np.ndarray, p_paraphrased: np.ndarray) -> float:
        return float(np.sum(np.abs(p_orig - p_paraphrased)))


# =============================================================================
# UNIFIED 10-CHECKER EVALUATOR ENGINE
# =============================================================================
class FullKolmogorovFinancialEngine:
    """Master evaluator running all 10 consistency checks for financial forecasting."""

    def __init__(self, tolerance: float = 0.15) -> None:
        self.tolerance = tolerance

    def audit_model_predictions(
        self,
        checks_dict: Dict[str, float],
    ) -> MultiCheckerReport:
        """Audits an ensemble of evaluated checker violations."""
        total = len(checks_dict)
        failed = sum(1 for v in checks_dict.values() if v > self.tolerance)
        passed = total - failed
        mean_v = float(np.mean(list(checks_dict.values()))) if total > 0 else 0.0

        return MultiCheckerReport(
            total_checks_evaluated=total,
            passed_checks=passed,
            failed_checks=failed,
            mean_violation_score=round(mean_v, 5),
            checker_violations={k: round(v, 5) for k, v in checks_dict.items()},
            is_fully_consistent=(failed == 0),
        )
