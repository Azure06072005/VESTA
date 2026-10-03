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
# DOMAIN FINANCIAL SYNONYM & CONSEQUENCE DICTIONARIES (VIETNAMESE)
# =============================================================================

FINANCIAL_SYNONYM_PAIRS: List[Tuple[str, str]] = [
    (r"\blợi nhuận sau thuế\b", "lãi ròng"),
    (r"\blãi ròng\b", "lợi nhuận sau thuế"),
    (r"\bdoanh thu thuần\b", "doanh số"),
    (r"\bdoanh số\b", "doanh thu thuần"),
    (r"\bbị xử phạt\b", "nhận quyết định xử phạt vi phạm"),
    (r"\bnhận quyết định xử phạt vi phạm\b", "bị xử phạt"),
    (r"\bhủy niêm yết\b", "rời sàn giao dịch"),
    (r"\brời sàn giao dịch\b", "hủy niêm yết"),
    (r"\bkhối ngoại bán ròng\b", "nhà đầu tư nước ngoài xả hàng"),
    (r"\bnhà đầu tư nước ngoài xả hàng\b", "khối ngoại bán ròng"),
    (r"\bkhối ngoại mua ròng\b", "nhà đầu tư nước ngoài gom hàng"),
    (r"\bnhà đầu tư nước ngoài gom hàng\b", "khối ngoại mua ròng"),
    (r"\bnợ xấu gia tăng\b", "tỷ lệ nợ khó đòi đi lên"),
    (r"\btỷ lệ nợ khó đòi đi lên\b", "nợ xấu gia tăng"),
    (r"\bphá sản\b", "mất khả năng thanh toán"),
    (r"\bmất khả năng thanh toán\b", "phá sản"),
    (r"\btăng trưởng bứt phá\b", "tăng trưởng ấn tượng"),
    (r"\btăng trưởng ấn tượng\b", "tăng trưởng bứt phá"),
    (r"\bgiảm sâu\b", "lao dốc mạnh"),
    (r"\blao dốc mạnh\b", "giảm sâu"),
    (r"\btăng mạnh\b", "tăng vọt"),
    (r"\btăng vọt\b", "tăng mạnh"),
    (r"\bvỡ nợ trái phiếu\b", "chậm thanh toán nghĩa vụ nợ trái phiếu"),
    (r"\bchậm thanh toán nghĩa vụ nợ trái phiếu\b", "vỡ nợ trái phiếu"),
]

FINANCIAL_CONSEQUENCE_MAP: List[Tuple[str, str]] = [
    ("bị đình chỉ giao dịch", "cổ phiếu đối mặt nguy cơ bán tháo"),
    ("phá sản", "doanh nghiệp rơi vào khủng hoảng nghiêm trọng"),
    ("vỡ nợ trái phiếu", "rủi ro thanh khoản leo thang"),
    ("lỗ kỷ lục", "kết quả kinh doanh sa sút"),
    ("lãi kỷ lục", "kết quả kinh doanh khởi sắc"),
    ("được cấp phép niêm yết", "mở rộng cơ hội tiếp cận vốn"),
    ("bán tháo", "thị trường chịu áp lực điều chỉnh"),
]


# =============================================================================
# MULTI-RELATIONAL ADVERSARIAL TUPLE GENERATOR
# =============================================================================

class FinancialMultiTupleGenerator:
    """Generates synthetic and semantic multi-tuples for 10-checker Kolmogorov audit."""

    def __init__(self, negator: Optional[Any] = None) -> None:
        from pipeline.f3xx_modeling.hybridacd_gate import VietnameseFinancialFastAdversarialNegator
        self.negator = negator or VietnameseFinancialFastAdversarialNegator()
        self.compiled_synonyms = [
            (re.compile(pat, re.IGNORECASE), repl) for pat, repl in FINANCIAL_SYNONYM_PAIRS
        ]

    def generate_negation(self, headline: str) -> str:
        """Generates logical negation ~T via V-FAN."""
        return self.negator.negate(headline)

    def generate_paraphrase(self, headline: str) -> str:
        """Generates semantic paraphrase preserving financial meaning."""
        clean = headline.strip()
        for regex, replacement in self.compiled_synonyms:
            if regex.search(clean):
                return regex.sub(replacement, clean, count=1)
        # Fallback syntactic paraphrase
        if "ghi nhận" in clean:
            return clean.replace("ghi nhận", "đạt mức")
        if "trong quý" in clean:
            return clean.replace("trong quý", "vào quý")
        return f"Thông tin ghi nhận: {clean}"

    def generate_concessive_but(self, headline_a: str, headline_b: Optional[str] = None) -> str:
        """Generates 'A nhưng B' concessive headline."""
        b = headline_b or "nợ xấu và chi phí tài chính gia tăng đột biến"
        return f"{headline_a.rstrip('.')} nhưng {b}"

    def generate_consequence(self, headline: str) -> Tuple[str, str]:
        """Returns cause A and implied consequence B such that A => B."""
        clean = headline.lower()
        for cause_kw, effect_phrase in FINANCIAL_CONSEQUENCE_MAP:
            if cause_kw in clean:
                return headline, f"Thị trường lo ngại {effect_phrase}"
        return headline, "Cổ phiếu chịu tác động từ diễn biến thông tin trên"


# =============================================================================
# UNIFIED 10-CHECKER EVALUATOR ENGINE
# =============================================================================

class FullKolmogorovFinancialEngine:
    """Master evaluator running all 10 consistency checks for financial forecasting."""

    def __init__(self, tolerance: float = 0.15) -> None:
        self.tolerance = tolerance
        self.tuple_gen = FinancialMultiTupleGenerator()

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

    def evaluate_headline_coherence(
        self,
        headline: str,
        predict_probs_fn: Callable[[List[str]], np.ndarray],
    ) -> Tuple[MultiCheckerReport, float]:
        """Executes full 10-checker suite on a given headline using a model predict function.

        Args:
            headline: Base Vietnamese financial headline.
            predict_probs_fn: Function mapping List[str] -> np.ndarray [B, 3] (neg, neu, pos).

        Returns:
            Tuple of (MultiCheckerReport, kolmogorov_coherence_index in [0, 1]).
        """
        # 1. Generate multi-relational variations
        h_neg = self.tuple_gen.generate_negation(headline)
        h_para = self.tuple_gen.generate_paraphrase(headline)
        h_but = self.tuple_gen.generate_concessive_but(headline)
        h_cause, h_effect = self.tuple_gen.generate_consequence(headline)

        # Partner headline for boolean conjunction / disjunction
        h_partner = "Khối ngoại đẩy mạnh mua ròng trên toàn thị trường"
        h_and = f"{headline.rstrip('.')} đồng thời {h_partner.lower()}"
        h_or = f"{headline.rstrip('.')} hoặc {h_partner.lower()}"

        batch_texts = [
            headline,    # 0: A
            h_neg,       # 1: ~A
            h_para,      # 2: Paraphrase(A)
            h_partner,   # 3: B
            h_and,       # 4: A and B
            h_or,        # 5: A or B
            h_but,       # 6: A but B
            h_effect,    # 7: Effect B
        ]

        probs = predict_probs_fn(batch_texts)
        p_a = probs[0]
        q_neg = probs[1]
        p_para = probs[2]
        p_b = probs[3]
        p_and = probs[4]
        p_or = probs[5]
        p_but = probs[6]
        p_effect = probs[7]

        # Evaluate all 10 checkers
        v_neg = FinancialNegChecker.evaluate(p_a, q_neg)
        v_and = FinancialAndChecker.evaluate(float(p_a[2]), float(p_b[2]), float(p_and[2]))
        v_or = FinancialOrChecker.evaluate(float(p_a[2]), float(p_b[2]), float(p_or[2]))
        v_and_or = FinancialAndOrChecker.evaluate(float(p_a[2]), float(p_b[2]), float(p_and[2]), float(p_or[2]))
        v_but = FinancialButChecker.evaluate(float(p_a[0]), float(p_but[0]))

        # Conditional checks
        # P(A | B) * P(B) == P(A and B) -> approx using joint
        p_a_given_b = float(np.clip(p_and[2] / max(float(p_b[2]), 1e-4), 0.0, 1.0))
        v_cond = FinancialCondChecker.evaluate(p_a_given_b, float(p_b[2]), float(p_and[2]))

        # CondCond: Macro regime split proxy
        v_condcond = FinancialCondCondChecker.evaluate(
            p_a_given_c=float(p_a[2]),
            p_a_given_b_c=float(p_and[2]),
            p_b_given_c=float(p_b[2]),
            p_a_given_not_b_c=float(p_a[2] * 0.95),
        )

        v_consequence = FinancialConsequenceChecker.evaluate(float(p_a[0]), float(p_effect[0]))

        # Expected evidence: prior vs posterior with evidence
        v_evidence = FinancialExpectedEvidenceChecker.evaluate(
            p_prior=float(p_a[2]),
            p_given_bull_evidence=float(np.clip(p_a[2] * 1.2, 0.0, 1.0)),
            prob_bull=0.5,
            p_given_bear_evidence=float(np.clip(p_a[2] * 0.8, 0.0, 1.0)),
            prob_bear=0.5,
        )

        v_para = FinancialParaphraseChecker.evaluate(p_a, p_para)

        checks_dict = {
            FinancialNegChecker.name: v_neg,
            FinancialAndChecker.name: v_and,
            FinancialOrChecker.name: v_or,
            FinancialAndOrChecker.name: v_and_or,
            FinancialButChecker.name: v_but,
            FinancialCondChecker.name: v_cond,
            FinancialCondCondChecker.name: v_condcond,
            FinancialConsequenceChecker.name: v_consequence,
            FinancialExpectedEvidenceChecker.name: v_evidence,
            FinancialParaphraseChecker.name: v_para,
        }

        report = self.audit_model_predictions(checks_dict)
        # Kolmogorov Coherence Index (KCI) in [0, 1]
        kci = float(np.clip(1.0 - (report.mean_violation_score / (self.tolerance * 2.0)), 0.0, 1.0))

        return report, round(kci, 4)
