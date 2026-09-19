"""src/pipeline/f3xx_modeling/hybridacd_gate.py

Feature F304: HybridACD Token-Constrained Decoding (TCD) Consistency Gate for VESTA.
Adapts the Token-Constrained Decoding principle of HybridACD (Tran Anh Kiet, 2026)
to the softmax probability simplex of PhoBERT (F301) and Multimodal Fusion (F302).

Components:
1. VietnameseFinancialFastAdversarialNegator (V-FAN):
   Micro-latency (< 0.5ms) rule-and-lexicon counterfactual / adversarial generator
   for Vietnamese equity headlines, replacing heavy autoregressive LLMs.
2. HybridACDConsistencyGate:
   Enforces axiomatic Kolmogorov consistency:
     P(Positive | T) = P(Negative | ~T)
     P(Negative | T) = P(Positive | ~T)
     P(Neutral | T)  = P(Neutral | ~T)
   via closed-form Simplex-TCD projection, and acts as an uninformative noise filter.
"""
from __future__ import annotations

import dataclasses
import re
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np


# =============================================================================
# 1. VIETNAMESE FINANCIAL FAST ADVERSARIAL NEGATOR (V-FAN)
# =============================================================================

# Domain-specific financial antonym map for HOSE/HNX/UPCOM context
FINANCIAL_ANTONYM_PAIRS: List[Tuple[str, str]] = [
    (r"\blỗ kỷ lục\b", "lãi kỷ lục"),
    (r"\blãi kỷ lục\b", "lỗ kỷ lục"),
    (r"\blỗ ròng\b", "lãi ròng"),
    (r"\blãi ròng\b", "lỗ ròng"),
    (r"\blỗ đậm\b", "lãi đậm"),
    (r"\blãi đậm\b", "lỗ đậm"),
    (r"\btăng trưởng âm\b", "tăng trưởng bứt phá"),
    (r"\btăng trưởng bứt phá\b", "tăng trưởng âm"),
    (r"\bsuy giảm nghiêm trọng\b", "tăng trưởng mạnh mẽ"),
    (r"\btăng trưởng mạnh mẽ\b", "suy giảm nghiêm trọng"),
    (r"\bbán ròng\b", "mua ròng"),
    (r"\bmua ròng\b", "bán ròng"),
    (r"\bhạ trần lãi suất\b", "nâng trần lãi suất"),
    (r"\bnâng trần lãi suất\b", "hạ trần lãi suất"),
    (r"\bhút ròng\b", "bơm ròng"),
    (r"\bbơm ròng\b", "hút ròng"),
    (r"\bnợ xấu gia tăng\b", "nợ xấu giảm mạnh"),
    (r"\bnợ xấu tăng vọt\b", "thu hồi nợ xấu tích cực"),
    (r"\bbị xử phạt\b", "được chấp thuận"),
    (r"\bbị đình chỉ\b", "được cấp phép"),
    (r"\bhủy niêm yết\b", "duy trì niêm yết"),
    (r"\bvỡ nợ\b", "tái cấu trúc thành công"),
    (r"\bphá sản\b", "phục hồi kinh doanh"),
    (r"\bkhó khăn dòng tiền\b", "dồi dào thanh khoản"),
    (r"\bbị phong tỏa\b", "được giải tỏa"),
    (r"\bgiảm sâu\b", "tăng mạnh"),
    (r"\btăng mạnh\b", "giảm sâu"),
    (r"\blaodốc\b", "bứt phá"),
    (r"\bbứt phá\b", "lao dốc"),
    (r"\btuột dốc\b", "tăng vọt"),
    (r"\btăng vọt\b", "tuột dốc"),
    (r"\btiêu cực\b", "tích cực"),
    (r"\btích cực\b", "tiêu cực"),
    (r"\bkém sắc\b", "khởi sắc"),
    (r"\bkhởi sắc\b", "kém sắc"),
    (r"\bảm đạm\b", "sôi động"),
    (r"\bsôi động\b", "ảm đạm"),
    # Tiếng lóng diễn đàn và cơ chế khớp lệnh HOSE/HNX
    (r"\búp bô\b", "kéo trần bứt phá"),
    (r"\búp sọt\b", "kéo trần bứt phá"),
    (r"\bmúa bên trăng\b", "trắng bên bán"),
    (r"\btrắng bên mua\b", "trắng bên bán"),
    (r"\bcháy tài khoản\b", "về bờ thành công"),
    (r"\bđu đỉnh\b", "bắt đúng đáy"),
    (r"\bkẹp hàng\b", "chốt lời thành công"),
    (r"\bgiải chấp\b", "nới lỏng margin"),
    (r"\bbán tháo\b", "gom hàng quyết liệt"),
    (r"\bchậm trả gốc lãi\b", "thanh toán đầy đủ nợ trái phiếu"),
    (r"\bkiểm toán ngoại trừ\b", "kiểm toán chấp nhận toàn phần"),
    (r"\bdiện kiểm soát\b", "ra khỏi diện cảnh báo"),
    (r"\bhủy niêm yết bắt buộc\b", "được cấp phép niêm yết"),
    (r"\bvỡ nợ trái phiếu\b", "mua lại trái phiếu trước hạn"),
    (r"\bbộ đội về làng\b", "bán tháo xả hàng"),
    (r"\bchim lợn\b", "bìm bịp"),
    (r"\bbìm bịp\b", "chim lợn"),
    (r"\bthủng đáy\b", "vượt đỉnh lịch sử"),
    (r"\bvượt đỉnh\b", "thủng đáy"),
]

# Prefixes representing authoritative clarifications or factual debunking
DENIAL_PREFIXES: List[str] = [
    "Bác bỏ thông tin: ",
    "Lãnh đạo doanh nghiệp khẳng định không có việc ",
    "Cơ quan quản lý bác bỏ tin đồn ",
    "Doanh nghiệp đính chính thông tin ",
]


class VietnameseFinancialFastAdversarialNegator:
    """Sub-millisecond adversarial negation generator for Vietnamese financial text."""

    def __init__(self) -> None:
        self.compiled_antonyms = [
            (re.compile(pattern, re.IGNORECASE), repl)
            for pattern, repl in FINANCIAL_ANTONYM_PAIRS
        ]

    def negate(self, headline: str) -> str:
        """Generates a counterfactual / negated adversarial headline in < 0.5ms."""
        if not headline or not isinstance(headline, str):
            return "Không có thông tin"

        clean_text = headline.strip()

        # Strategy 1: Lexical financial antonym swap (highest semantic quality)
        for regex, replacement in self.compiled_antonyms:
            if regex.search(clean_text):
                # Apply substitution to the first match
                return regex.sub(replacement, clean_text, count=1)

        # Strategy 2: Insertion of syntactic negation before key verbs
        verb_match = re.search(r"\b(sẽ|đã|đang|vừa|chuẩn bị|quyết định)\b", clean_text, re.IGNORECASE)
        if verb_match:
            idx = verb_match.start()
            return clean_text[:idx] + "không " + clean_text[idx:]

        # Strategy 3: Authority denial prefix fallback
        prefix = DENIAL_PREFIXES[hash(clean_text) % len(DENIAL_PREFIXES)]
        # Lowercase the first char of clean_text if prefix doesn't end with colon
        if prefix.endswith(" "):
            first_char = clean_text[0].lower() if len(clean_text) > 0 else ""
            return prefix + first_char + clean_text[1:]
        return prefix + clean_text


# =============================================================================
# 2. SIMPLEX-TCD CONSISTENCY GATE
# =============================================================================

@dataclasses.dataclass
class GateResult:
    """Output container for HybridACD Consistency Gating."""
    is_consistent: bool
    violation_score: float  # Delta in [0, 2]
    original_probs: np.ndarray  # [p_neg, p_neu, p_pos]
    negated_probs: np.ndarray   # [q_neg, q_neu, q_pos]
    projected_probs: np.ndarray # [p*_neg, p*_neu, p*_pos]
    confidence_weight: float    # Weight in [0, 1] based on consistency
    consistent_alpha_score: float  # S in [0, 100]
    negated_headline: str
    latency_ms: float


class HybridACDConsistencyGate:
    """Token-Constrained Decoding adapted for Probability Simplex of PhoBERT/Multimodal.
    
    Enforces Kolmogorov axiomatic coherence:
      p*_pos(T) == q*_neg(~T)
      p*_neg(T) == q*_pos(~T)
      p*_neu(T) == q*_neu(~T)
      sum(p*)   == 1.0
    
    Acts as a high-conviction noise filter eliminating uninformative headlines
    where the model hallucinates confidence without genuine semantic justification.
    """

    def __init__(
        self,
        noise_threshold: float = 0.40,
        discard_inconsistent: bool = True,
        negator: Optional[VietnameseFinancialFastAdversarialNegator] = None,
    ) -> None:
        """
        Args:
            noise_threshold: Maximum allowable Delta violation before penalizing/discarding.
            discard_inconsistent: If True, sets confidence_weight = 0.0 for inconsistent events.
            negator: V-FAN instance.
        """
        self.noise_threshold = noise_threshold
        self.discard_inconsistent = discard_inconsistent
        self.negator = negator or VietnameseFinancialFastAdversarialNegator()

    def generate_negated_headline(self, headline: str) -> str:
        """Exposes V-FAN transformation directly."""
        return self.negator.negate(headline)

    def project_simplex_pair(
        self,
        p_raw: np.ndarray,
        q_raw: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Closed-form projection of paired distributions (p_orig, q_neg) onto consistent simplex.
        
        Indices: 0: Negative, 1: Neutral, 2: Positive.
        
        Axioms:
          p*_pos = q*_neg = (p_pos + q_neg) / 2
          p*_neg = q*_pos = (p_neg + q_pos) / 2
          p*_neu = q*_neu = (p_neu + q_neu) / 2
        """
        p = np.asarray(p_raw, dtype=float)
        q = np.asarray(q_raw, dtype=float)

        # Ensure valid probability distribution input
        p = p / (np.sum(p) + 1e-12)
        q = q / (np.sum(q) + 1e-12)

        # 1. Measure raw violation Delta
        p_neg, p_neu, p_pos = p[0], p[1], p[2]
        q_neg, q_neu, q_pos = q[0], q[1], q[2]

        violation = float(abs(p_pos - q_neg) + abs(p_neg - q_pos) + abs(p_neu - q_neu) / 2.0)

        # 2. Closed-form projection
        hat_pos = (p_pos + q_neg) / 2.0
        hat_neg = (p_neg + q_pos) / 2.0
        hat_neu = (p_neu + q_neu) / 2.0

        total = hat_pos + hat_neg + hat_neu
        if total <= 0:
            p_star = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
            q_star = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
        else:
            p_star = np.array([hat_neg / total, hat_neu / total, hat_pos / total])
            # q*_neg == p*_pos, q*_pos == p*_neg, q*_neu == p*_neu
            q_star = np.array([hat_pos / total, hat_neu / total, hat_neg / total])

        return p_star, q_star, violation

    def evaluate_event(
        self,
        headline: str,
        prob_orig: np.ndarray,
        prob_neg: np.ndarray,
        negated_headline: Optional[str] = None,
    ) -> GateResult:
        """Evaluates and gates a single scored event.
        
        Args:
            headline: Original financial headline.
            prob_orig: 3-class probability array [p_neg, p_neu, p_pos].
            prob_neg: 3-class probability array [q_neg, q_neu, q_pos] from scored negated headline.
            negated_headline: Optional text of negated headline.
        """
        t0 = time.perf_counter()

        if negated_headline is None:
            negated_headline = self.negator.negate(headline)

        p_star, _, violation = self.project_simplex_pair(prob_orig, prob_neg)

        is_consistent = violation <= self.noise_threshold

        if is_consistent:
            confidence_weight = 1.0 - (violation / (2.0 * self.noise_threshold))
        else:
            confidence_weight = 0.0 if self.discard_inconsistent else max(0.0, 1.0 - violation)

        # Compute Continuous Alpha Score S in [0, 100]
        # S < 45 indicates strong mean-reversion negative sentiment buy signal
        # S = 50 + 50 * (p*_pos - p*_neg)
        alpha_score = 50.0 + 50.0 * float(p_star[2] - p_star[0])

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return GateResult(
            is_consistent=is_consistent,
            violation_score=round(violation, 6),
            original_probs=np.round(prob_orig, 6),
            negated_probs=np.round(prob_neg, 6),
            projected_probs=np.round(p_star, 6),
            confidence_weight=round(confidence_weight, 4),
            consistent_alpha_score=round(alpha_score, 4),
            negated_headline=negated_headline,
            latency_ms=round(latency_ms, 3),
        )

    def evaluate_batch(
        self,
        headlines: List[str],
        probs_orig: np.ndarray,
        probs_neg: np.ndarray,
    ) -> List[GateResult]:
        """Vectorized / batch evaluation for offline backtest pipelines."""
        assert len(headlines) == len(probs_orig) == len(probs_neg), "Array size mismatch"
        results = []
        for h, p, q in zip(headlines, probs_orig, probs_neg):
            results.append(self.evaluate_event(h, p, q))
        return results
