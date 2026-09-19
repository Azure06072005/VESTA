"""tests/test_multimodal_fusion.py

Unit Test Suite for F302: Multimodal Cross-Attention Fusion.
Validates:
1. Tensor shape invariants across Text, Fundamentals, and Regime modalities.
2. Cross-Attention fusion bottleneck producing 128-dim Multi-Modal Sentiment-Alpha vector.
3. Multi-task loss computation (Sentiment + Direction + Return).
4. Atomic checkpoint saving, emergency backup, and resume restoration.
"""
from __future__ import annotations

import pathlib
import tempfile
from typing import Any
import numpy as np
import pandas as pd
import torch

from src.models.multimodal_fusion import (
    DEFAULT_FUNDAMENTAL_FEATURES,
    MultimodalCrossAttentionFusion,
)
from src.models.train_multimodal_fusion import MultimodalFinancialDataset
from src.models.training_checkpoint import (
    AtomicCheckpointSaver,
    load_resumable_checkpoint,
)


class MockTokenizer:
    """Lightweight mock tokenizer for fast unit tests without downloading weights."""

    def __call__(
        self,
        texts: str | list[str],
        max_length: int = 32,
        padding: str = "max_length",
        truncation: bool = True,
        return_tensors: str = "pt",
    ):
        if isinstance(texts, str):
            texts = [texts]
        n = len(texts)
        return {
            "input_ids": torch.ones((n, max_length), dtype=torch.long),
            "attention_mask": torch.ones((n, max_length), dtype=torch.long),
        }


def _create_sample_dataframe(n: int = 16) -> pd.DataFrame:
    """Generates synthetic DataFrame mimicking f104 dataset."""
    data: dict[str, Any] = {
        "symbol": ["FPT", "VNM", "HPG", "VIC"] * (n // 4),
        "context_text": [f"[FPT | HOSE | BULL] Tin tuc kiem thu so {i}" for i in range(n)],
        "sentiment_label": np.random.choice([0, 1, 2], size=n),
        "target_dir_t5": np.random.choice([-1, 0, 1], size=n),
        "ret_t5_pct": np.random.normal(0.01, 0.03, size=n),
        "market_regime": np.random.choice(["BULL", "BEAR", "CRISIS_HIGH_VOL", "SIDEWAYS"], size=n),
    }
    for col in DEFAULT_FUNDAMENTAL_FEATURES:
        data[col] = np.random.normal(0.0, 1.0, size=n)
        # Introduce a few NaNs to verify robust handling
        data[col][0] = np.nan

    return pd.DataFrame(data)


def test_multimodal_dataset_construction():
    df = _create_sample_dataframe(16)
    tok = MockTokenizer()
    ds = MultimodalFinancialDataset(
        df=df,
        tokenizer=tok,
        max_seq_length=32,
        pre_tokenize=False,
    )

    assert len(ds) == 16
    sample = ds[0]
    assert "input_ids" in sample
    assert "fundamentals" in sample
    assert "regime_id" in sample
    assert "sentiment_label" in sample
    assert "direction_label" in sample
    assert "return_target" in sample

    assert sample["fundamentals"].shape == (len(DEFAULT_FUNDAMENTAL_FEATURES),)
    # Check direction mapping: [-1, 0, 1] + 1 -> [0, 1, 2]
    assert sample["direction_label"].item() in [0, 1, 2]
    # Check no NaNs in fundamentals
    assert not torch.isnan(sample["fundamentals"]).any()


def test_multimodal_model_forward_and_shapes():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MultimodalCrossAttentionFusion(
        phobert_model_name="vinai/phobert-base-v2",
        phobert_checkpoint=None,
        freeze_phobert_layers=10,
        num_fundamental_features=len(DEFAULT_FUNDAMENTAL_FEATURES),
        hidden_dim=64,  # Use small hidden dim for test speed
        num_heads=2,
        num_fusion_layers=1,
    )
    model.to(device)
    model.eval()

    batch_size = 4
    seq_len = 16
    input_ids = torch.ones((batch_size, seq_len), dtype=torch.long, device=device)
    attention_mask = torch.ones((batch_size, seq_len), dtype=torch.long, device=device)
    fundamentals = torch.randn((batch_size, len(DEFAULT_FUNDAMENTAL_FEATURES)), device=device)
    regime_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long, device=device)

    sent_labels = torch.tensor([0, 1, 2, 1], dtype=torch.long, device=device)
    dir_labels = torch.tensor([0, 1, 2, 0], dtype=torch.long, device=device)
    ret_targets = torch.tensor([0.01, -0.02, 0.05, 0.00], dtype=torch.float32, device=device)

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            fundamentals=fundamentals,
            regime_ids=regime_ids,
            sentiment_labels=sent_labels,
            direction_labels=dir_labels,
            return_targets=ret_targets,
        )

    assert out.alpha_vector.shape == (batch_size, 64)
    assert out.sentiment_logits.shape == (batch_size, 3)
    assert out.direction_logits.shape == (batch_size, 3)
    assert out.return_preds.shape == (batch_size,)
    assert out.loss is not None
    assert out.loss.item() > 0.0


def test_multimodal_backward_pass():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MultimodalCrossAttentionFusion(
        phobert_model_name="vinai/phobert-base-v2",
        phobert_checkpoint=None,
        freeze_phobert_layers=11,  # Freeze all but top layer for fast test
        num_fundamental_features=len(DEFAULT_FUNDAMENTAL_FEATURES),
        hidden_dim=32,
        num_heads=2,
        num_fusion_layers=1,
    )
    model.to(device)
    model.train()

    input_ids = torch.ones((2, 16), dtype=torch.long, device=device)
    attention_mask = torch.ones((2, 16), dtype=torch.long, device=device)
    fundamentals = torch.randn((2, len(DEFAULT_FUNDAMENTAL_FEATURES)), device=device)
    regime_ids = torch.tensor([0, 1], dtype=torch.long, device=device)
    sent_labels = torch.tensor([0, 2], dtype=torch.long, device=device)
    dir_labels = torch.tensor([1, 2], dtype=torch.long, device=device)
    ret_targets = torch.tensor([0.01, 0.02], dtype=torch.float32, device=device)

    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        fundamentals=fundamentals,
        regime_ids=regime_ids,
        sentiment_labels=sent_labels,
        direction_labels=dir_labels,
        return_targets=ret_targets,
    )
    assert out.loss is not None
    out.loss.backward()

    # Verify gradients computed for fusion layers
    for param in model.alpha_bottleneck.parameters():
        assert param.grad is not None


def test_atomic_checkpointing_and_resumability():
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = pathlib.Path(tmp_dir)
        saver = AtomicCheckpointSaver(output_dir)

        dummy_model = torch.nn.Linear(10, 2)
        optimizer = torch.optim.Adam(dummy_model.parameters(), lr=1e-3)
        history = [{"epoch": 1, "loss": 0.5}]

        # 1. Save standard checkpoint
        saved_path = saver.save_checkpoint(
            model=dummy_model,
            optimizer=optimizer,
            scheduler=None,
            scaler=None,
            epoch=2,
            global_step=100,
            best_metric=0.85,
            training_history=history,
            filename="last_checkpoint.pt",
        )
        assert saved_path.exists()

        # 2. Save best model
        best_path = saver.save_best_model(dummy_model, epoch=2, metric_value=0.85)
        assert best_path.exists()
        assert (output_dir / "best_model_meta.json").exists()

        # 3. Save emergency checkpoint
        emerg_path = saver.save_emergency_checkpoint(
            model=dummy_model,
            optimizer=optimizer,
            scheduler=None,
            scaler=None,
            epoch=2,
            global_step=100,
            best_metric=0.85,
            training_history=history,
            reason="Test emergency",
        )
        assert emerg_path.exists()

        # 4. Resume from checkpoint
        new_model = torch.nn.Linear(10, 2)
        new_opt = torch.optim.Adam(new_model.parameters(), lr=1e-3)
        start_epoch, global_step, best_metric, loaded_hist = load_resumable_checkpoint(
            saved_path,
            model=new_model,
            optimizer=new_opt,
        )

        assert start_epoch == 2
        assert global_step == 100
        assert best_metric == 0.85
        assert len(loaded_hist) == 1
        # Weights should match exactly
        assert torch.allclose(dummy_model.weight, new_model.weight)
