"""src/pipeline/f3xx_modeling/self_supervised_adversarial.py

Feature F304+: Self-Supervised Adversarial Learning Framework for VESTA.
Applies self-supervised adversarial consistency optimization (Tran Anh, HybridACD 2026)
to align PhoBERT (F301) and Multimodal Cross-Attention (F302) representations without
relying on human labels or future price signals.

Mathematical Formulation:
Minimizes Kolmogorov axiomatic violation loss over self-supervised counterfactual tuples:
  L_self_sup = lambda_neg * L_neg + lambda_para * L_para + lambda_simplex * L_simplex
where:
  L_neg     = E_{x} [ || p_pos(x) - q_neg(~x) ||^2 + || p_neg(x) - q_pos(~x) ||^2 ]
  L_para    = E_{x} [ || p(x) - p(Paraphrase(x)) ||_2^2 ]
  L_simplex = E_{x} [ (sum_k p_k(x) - 1.0)^2 ]
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from pipeline.f3xx_modeling.hybridacd_gate import VietnameseFinancialFastAdversarialNegator
from pipeline.f3xx_modeling.hybridacd_multi_checkers import (
    FinancialMultiTupleGenerator,
    FINANCIAL_SYNONYM_PAIRS,
)


@dataclasses.dataclass
class AdversarialBatch:
    """Container for paired adversarial text samples for self-supervised training."""
    original_texts: List[str]
    negated_texts: List[str]
    paraphrased_texts: List[str]
    concessive_texts: List[str]


@dataclasses.dataclass
class SelfSupervisedTelemetry:
    """Metrics container tracking self-supervised consistency convergence."""
    mean_negation_violation: float
    mean_paraphrase_distance: float
    kolmogorov_compliance_pct: float
    total_samples_evaluated: int
    adaptation_loss: float
    inconsistency_reduction_pct: float


# =============================================================================
# 1. ADVERSARIAL PERTURBATION GENERATOR
# =============================================================================

class AdversarialPerturbationEngine:
    """Generates continuous linguistic and counterfactual perturbations for self-supervision."""

    def __init__(
        self,
        negator: Optional[VietnameseFinancialFastAdversarialNegator] = None,
        tuple_gen: Optional[FinancialMultiTupleGenerator] = None,
    ) -> None:
        self.negator = negator or VietnameseFinancialFastAdversarialNegator()
        self.tuple_gen = tuple_gen or FinancialMultiTupleGenerator(self.negator)

    def generate_adversarial_batch(self, headlines: List[str]) -> AdversarialBatch:
        """Transforms a batch of raw financial headlines into self-supervised counterfactual tuples."""
        orig = []
        neg = []
        para = []
        but = []

        for h in headlines:
            clean = str(h).strip()
            if not clean:
                clean = "Thị trường chứng khoán biến động đi ngang"
            orig.append(clean)
            neg.append(self.tuple_gen.generate_negation(clean))
            para.append(self.tuple_gen.generate_paraphrase(clean))
            but.append(self.tuple_gen.generate_concessive_but(clean))

        return AdversarialBatch(
            original_texts=orig,
            negated_texts=neg,
            paraphrased_texts=para,
            concessive_texts=but,
        )


# =============================================================================
# 2. SELF-SUPERVISED KOLMOGOROV CONSISTENCY LOSS (PYTORCH)
# =============================================================================

class SelfSupervisedKolmogorovLoss(nn.Module):
    """PyTorch loss module enforcing Kolmogorov probability axioms and semantic invariance."""

    def __init__(
        self,
        lambda_neg: float = 1.0,
        lambda_para: float = 0.8,
        lambda_simplex: float = 0.5,
        temperature: float = 1.0,
    ) -> None:
        super().__init__()
        self.lambda_neg = lambda_neg
        self.lambda_para = lambda_para
        self.lambda_simplex = lambda_simplex
        self.temperature = temperature

    def forward(
        self,
        logits_orig: torch.Tensor,
        logits_neg: torch.Tensor,
        logits_para: torch.Tensor,
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """Computes self-supervised adversarial loss across paired forward passes.

        Classes (Indices): 0: Negative, 1: Neutral, 2: Positive.

        Args:
            logits_orig: [B, 3] raw logits for original headlines.
            logits_neg:  [B, 3] raw logits for negated counterfactuals.
            logits_para: [B, 3] raw logits for semantic paraphrases.

        Returns:
            total_loss: Scalar torch.Tensor with gradients.
            metrics_dict: Dictionary with detached float metrics for logging.
        """
        p_orig = F.softmax(logits_orig / self.temperature, dim=-1)
        q_neg = F.softmax(logits_neg / self.temperature, dim=-1)
        p_para = F.softmax(logits_para / self.temperature, dim=-1)

        # 1. Negation Complementarity Loss (Kolmogorov Invariant)
        # Axiom: P_pos(x) == Q_neg(~x) and P_neg(x) == Q_pos(~x)
        p_pos = p_orig[:, 2]
        p_neg = p_orig[:, 0]
        p_neu = p_orig[:, 1]

        q_pos = q_neg[:, 2]
        q_neg_val = q_neg[:, 0]
        q_neu = q_neg[:, 1]

        loss_neg_pos = F.mse_loss(p_pos, q_neg_val)
        loss_neg_neg = F.mse_loss(p_neg, q_pos)
        loss_neg_neu = 0.5 * F.mse_loss(p_neu, q_neu)
        loss_neg = loss_neg_pos + loss_neg_neg + loss_neg_neu

        # 2. Semantic Paraphrase Invariance Loss (Consistency under synonym substitution)
        loss_para = F.mse_loss(p_orig, p_para)

        # 3. Simplex Normalization Guarantee (Sum to 1.0)
        simplex_sum_orig = p_orig.sum(dim=-1)
        loss_simplex = F.mse_loss(simplex_sum_orig, torch.ones_like(simplex_sum_orig))

        # Total Composite Loss
        total_loss = (
            self.lambda_neg * loss_neg
            + self.lambda_para * loss_para
            + self.lambda_simplex * loss_simplex
        )

        metrics = {
            "loss_total": float(total_loss.item()),
            "loss_negation": float(loss_neg.item()),
            "loss_paraphrase": float(loss_para.item()),
            "loss_simplex": float(loss_simplex.item()),
            "mean_pos_neg_violation": float(torch.abs(p_pos - q_neg_val).mean().item()),
            "mean_neg_pos_violation": float(torch.abs(p_neg - q_pos).mean().item()),
        }
        return total_loss, metrics


# =============================================================================
# 3. SELF-SUPERVISED ADAPTATION TRAINER & BENCHMARKER
# =============================================================================

class SelfSupervisedAdversarialTrainer:
    """Orchestrates self-supervised adaptation rounds on financial encoders."""

    def __init__(
        self,
        loss_fn: Optional[SelfSupervisedKolmogorovLoss] = None,
        perturbation_engine: Optional[AdversarialPerturbationEngine] = None,
    ) -> None:
        self.loss_fn = loss_fn or SelfSupervisedKolmogorovLoss()
        self.perturbation_engine = perturbation_engine or AdversarialPerturbationEngine()

    def evaluate_model_coherence(
        self,
        headlines: List[str],
        predict_probs_fn: Callable[[List[str]], np.ndarray],
    ) -> SelfSupervisedTelemetry:
        """Evaluates model consistency metrics on an arbitrary sample of headlines.

        Args:
            headlines: List of text headlines.
            predict_probs_fn: Function mapping List[str] -> np.ndarray [B, 3] (neg, neu, pos).
        """
        if not headlines:
            return SelfSupervisedTelemetry(0.0, 0.0, 100.0, 0, 0.0, 0.0)

        batch = self.perturbation_engine.generate_adversarial_batch(headlines)

        p_orig = predict_probs_fn(batch.original_texts)
        q_neg = predict_probs_fn(batch.negated_texts)
        p_para = predict_probs_fn(batch.paraphrased_texts)

        # 1. Negation violation: |p_pos - q_neg| + |p_neg - q_pos| + 0.5*|p_neu - q_neu|
        neg_viols = np.abs(p_orig[:, 2] - q_neg[:, 0]) + np.abs(p_orig[:, 0] - q_neg[:, 2]) + 0.5 * np.abs(p_orig[:, 1] - q_neg[:, 1])
        mean_neg_viol = float(np.mean(neg_viols))

        # 2. Paraphrase distance: L1 distance
        para_dists = np.sum(np.abs(p_orig - p_para), axis=-1)
        mean_para_dist = float(np.mean(para_dists))

        # Compliance threshold: violation <= 0.35
        compliant_count = int(np.sum(neg_viols <= 0.35))
        compliance_pct = (compliant_count / len(headlines)) * 100.0

        return SelfSupervisedTelemetry(
            mean_negation_violation=round(mean_neg_viol, 4),
            mean_paraphrase_distance=round(mean_para_dist, 4),
            kolmogorov_compliance_pct=round(compliance_pct, 2),
            total_samples_evaluated=len(headlines),
            adaptation_loss=round(float(mean_neg_viol + 0.8 * mean_para_dist), 4),
            inconsistency_reduction_pct=round(max(0.0, 100.0 - (mean_neg_viol * 100.0)), 2),
        )

    def run_synthetic_adaptation_step(
        self,
        classifier_head: nn.Module,
        features_orig: torch.Tensor,
        features_neg: torch.Tensor,
        features_para: torch.Tensor,
        optimizer: torch.optim.Optimizer,
    ) -> Dict[str, float]:
        """Executes a single gradient update step using SelfSupervisedKolmogorovLoss."""
        classifier_head.train()
        optimizer.zero_grad()

        logits_orig = classifier_head(features_orig)
        logits_neg = classifier_head(features_neg)
        logits_para = classifier_head(features_para)

        loss, metrics = self.loss_fn(logits_orig, logits_neg, logits_para)
        loss.backward()
        optimizer.step()

        return metrics
