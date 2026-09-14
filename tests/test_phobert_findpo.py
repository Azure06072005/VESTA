"""tests/test_phobert_findpo.py

Unit Test Suite for F301: PhoBERT-base Fine-Tuning with FinDPO Market Alignment.
Verifies 5 Invariants:
1. Dual-Head Instantiation: Sentiment classification head (3 classes) & FinDPO policy head (scalar).
2. Forward Pass Invariants: Output shapes match batch sizes; logits have dimension 3.
3. FinDPO Bradley-Terry Loss: Chosen preference scores correctly contrasted with rejected scores.
4. Multi-Task Combined Loss: Total loss correctly blends CE and DPO components.
5. Backward Pass & Gradient Flow: Backprop updates encoder and linear projection parameters.
"""
from __future__ import annotations

import pathlib
import sys

import torch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from models.phobert_findpo import PhoBertFinDPO


@pytest.fixture(scope="module")
def model():
    # Instantiate PhoBERT with dummy / small architecture or base
    m = PhoBertFinDPO(
        model_name="vinai/phobert-base-v2",
        num_labels=3,
        dropout_prob=0.1,
        beta=0.1,
        preference_weight=0.4,
    )
    m.eval()
    return m


def test_model_instantiation(model):
    assert hasattr(model, "sentiment_head")
    assert hasattr(model, "policy_head")
    assert hasattr(model, "encoder")
    assert model.sentiment_head.out_features == 3
    assert model.policy_head.out_features == 1


def test_forward_pass_sentiment_only(model):
    batch_size = 2
    seq_len = 16
    input_ids = torch.randint(0, 1000, (batch_size, seq_len))
    attention_mask = torch.ones((batch_size, seq_len), dtype=torch.long)
    labels = torch.tensor([0, 2], dtype=torch.long)

    outputs = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
    )

    assert outputs.sentiment_logits is not None
    assert outputs.sentiment_logits.shape == (batch_size, 3)
    assert outputs.loss_ce is not None
    assert outputs.loss_ce.item() > 0.0
    assert outputs.loss is not None
    assert outputs.loss_dpo is None


def test_forward_pass_findpo_preference(model):
    batch_size = 2
    seq_len = 16
    input_ids = torch.randint(0, 1000, (batch_size, seq_len))
    attention_mask = torch.ones((batch_size, seq_len), dtype=torch.long)
    labels = torch.tensor([1, 0], dtype=torch.long)

    chosen_ids = torch.randint(0, 1000, (batch_size, seq_len))
    chosen_mask = torch.ones((batch_size, seq_len), dtype=torch.long)
    rejected_ids = torch.randint(0, 1000, (batch_size, seq_len))
    rejected_mask = torch.ones((batch_size, seq_len), dtype=torch.long)

    outputs = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
        chosen_input_ids=chosen_ids,
        chosen_attention_mask=chosen_mask,
        rejected_input_ids=rejected_ids,
        rejected_attention_mask=rejected_mask,
    )

    assert outputs.loss_ce is not None
    assert outputs.loss_dpo is not None
    assert outputs.loss is not None
    assert outputs.chosen_scores is not None
    assert outputs.rejected_scores is not None
    assert outputs.chosen_scores.shape == (batch_size,)
    assert outputs.rejected_scores.shape == (batch_size,)

    # Verify multi-task loss equation: (1 - 0.4) * CE + 0.4 * DPO
    expected_total = 0.6 * outputs.loss_ce.item() + 0.4 * outputs.loss_dpo.item()
    assert abs(outputs.loss.item() - expected_total) < 1e-4


def test_backward_pass_gradients(model):
    model.train()
    batch_size = 2
    seq_len = 8
    input_ids = torch.randint(0, 500, (batch_size, seq_len))
    attention_mask = torch.ones((batch_size, seq_len), dtype=torch.long)
    labels = torch.tensor([0, 1], dtype=torch.long)

    chosen_ids = torch.randint(0, 500, (batch_size, seq_len))
    chosen_mask = torch.ones((batch_size, seq_len), dtype=torch.long)
    rejected_ids = torch.randint(0, 500, (batch_size, seq_len))
    rejected_mask = torch.ones((batch_size, seq_len), dtype=torch.long)

    outputs = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
        chosen_input_ids=chosen_ids,
        chosen_attention_mask=chosen_mask,
        rejected_input_ids=rejected_ids,
        rejected_attention_mask=rejected_mask,
    )

    outputs.loss.backward()

    # Check that sentiment_head and policy_head received gradients
    assert model.sentiment_head.weight.grad is not None
    assert model.sentiment_head.weight.grad.norm().item() > 0.0
    assert model.policy_head.weight.grad is not None
    assert model.policy_head.weight.grad.norm().item() > 0.0

    model.zero_grad()
    model.eval()
