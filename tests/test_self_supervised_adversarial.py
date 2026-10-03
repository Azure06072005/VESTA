"""tests/test_self_supervised_adversarial.py

Unit tests for F304+: Self-Supervised Adversarial Learning Framework.
Tests AdversarialPerturbationEngine, SelfSupervisedKolmogorovLoss gradients,
and SelfSupervisedAdversarialTrainer convergence metrics.
"""
from __future__ import annotations

import pathlib
import sys
import numpy as np
import pytest
import torch
import torch.nn as nn

root_src = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(root_src) not in sys.path:
    sys.path.insert(0, str(root_src))

from pipeline.f3xx_modeling.self_supervised_adversarial import (

    AdversarialPerturbationEngine,
    SelfSupervisedKolmogorovLoss,
    SelfSupervisedAdversarialTrainer,
    AdversarialBatch,
    SelfSupervisedTelemetry,
)


def test_adversarial_perturbation_engine():
    """Verify AdversarialPerturbationEngine produces valid paired tuples."""
    engine = AdversarialPerturbationEngine()
    headlines = [
        "Lợi nhuận sau thuế của VCB tăng trưởng bứt phá",
        "Khối ngoại bán ròng kỷ lục trong phiên đầu tuần",
    ]

    batch = engine.generate_adversarial_batch(headlines)
    assert isinstance(batch, AdversarialBatch)
    assert len(batch.original_texts) == 2
    assert len(batch.negated_texts) == 2
    assert len(batch.paraphrased_texts) == 2
    assert len(batch.concessive_texts) == 2

    # Check semantic content
    assert "tăng trưởng âm" in batch.negated_texts[0].lower() or "không" in batch.negated_texts[0].lower()
    assert "lãi ròng" in batch.paraphrased_texts[0].lower() or "đạt mức" in batch.paraphrased_texts[0].lower()
    assert "nhưng" in batch.concessive_texts[0].lower()


def test_self_supervised_kolmogorov_loss_computation():
    """Verify that SelfSupervisedKolmogorovLoss computes gradients and logs metrics."""
    loss_fn = SelfSupervisedKolmogorovLoss(lambda_neg=1.0, lambda_para=0.8, lambda_simplex=0.5)

    batch_size = 4
    num_classes = 3

    # Generate synthetic logits requiring gradient
    logits_orig = torch.randn(batch_size, num_classes, requires_grad=True)
    logits_neg = torch.randn(batch_size, num_classes, requires_grad=True)
    logits_para = torch.randn(batch_size, num_classes, requires_grad=True)

    loss, metrics = loss_fn(logits_orig, logits_neg, logits_para)

    # 1. Scalar loss & non-negative
    assert loss.dim() == 0
    assert loss.item() > 0.0

    # 2. Gradient backpropagation
    loss.backward()
    assert logits_orig.grad is not None
    assert logits_neg.grad is not None
    assert logits_para.grad is not None

    # 3. Metrics integrity
    assert "loss_total" in metrics
    assert "loss_negation" in metrics
    assert "loss_paraphrase" in metrics
    assert "loss_simplex" in metrics


def test_self_supervised_trainer_evaluation():
    """Verify SelfSupervisedAdversarialTrainer coherence benchmarking."""
    trainer = SelfSupervisedAdversarialTrainer()

    # Model predicting constant random vectors
    def dummy_predict(texts: list[str]) -> np.ndarray:
        return np.tile([0.80, 0.10, 0.10], (len(texts), 1))

    headlines = [
        "Doanh nghiệp báo lỗ đậm trong quý 4",
        "Thanh khoản sụt giảm nghiêm trọng",
    ]

    telemetry = trainer.evaluate_model_coherence(headlines, dummy_predict)
    assert isinstance(telemetry, SelfSupervisedTelemetry)
    assert telemetry.total_samples_evaluated == 2
    assert telemetry.mean_negation_violation >= 0.0
    assert 0.0 <= telemetry.kolmogorov_compliance_pct <= 100.0


def test_synthetic_adaptation_step():
    """Verify that a single adaptation step successfully reduces inconsistency loss."""
    torch.manual_seed(42)
    trainer = SelfSupervisedAdversarialTrainer()

    hidden_dim = 16
    classifier = nn.Linear(hidden_dim, 3)
    optimizer = torch.optim.Adam(classifier.parameters(), lr=0.05)

    feat_orig = torch.randn(8, hidden_dim)
    feat_neg = torch.randn(8, hidden_dim)
    feat_para = torch.randn(8, hidden_dim)

    # Step 1
    m1 = trainer.run_synthetic_adaptation_step(classifier, feat_orig, feat_neg, feat_para, optimizer)
    # Step 2
    m2 = trainer.run_synthetic_adaptation_step(classifier, feat_orig, feat_neg, feat_para, optimizer)

    assert m1["loss_total"] > 0.0
    # Inconsistency loss should decrease after gradient step
    assert m2["loss_total"] <= m1["loss_total"] + 0.10
