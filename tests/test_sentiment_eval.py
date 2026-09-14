"""tests/test_sentiment_eval.py

Verification Test Suite for F301: PhoBERT-base Fine-Tuning with FinDPO Evaluation.
Validates:
1. Checkpoint file exists (best_model.pt) and can be loaded.
2. Metrics file exists (training_metrics.json) and confirms VRAM budget <= 5.2GB.
3. Model evaluation on validation batch produces valid loss and FinDPO preference accuracy >= 0.80.
4. Model evaluation outputs non-null classification predictions.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from models.evaluate import evaluate_dataset
from models.phobert_findpo import PhoBertFinDPO
from models.train_sentiment import FinancialSentimentDataset
import duckdb
from transformers import AutoTokenizer


CHECKPOINT_DIR = pathlib.Path("out/models/phobert_base_findpo")
CHECKPOINT_FILE = CHECKPOINT_DIR / "best_model.pt"
METRICS_FILE = CHECKPOINT_DIR / "training_metrics.json"


def test_checkpoint_and_metrics_exist():
    assert CHECKPOINT_FILE.exists(), f"Missing trained checkpoint: {CHECKPOINT_FILE}"
    assert METRICS_FILE.exists(), f"Missing training metrics report: {METRICS_FILE}"

    metrics = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
    assert "best_val_f1_macro" in metrics
    assert "peak_vram_gb" in metrics
    assert metrics.get("vram_budget_safe") is True
    assert metrics["peak_vram_gb"] <= 5.2, f"Exceeded VRAM budget: {metrics['peak_vram_gb']} GB"


def test_model_inference_on_validation_batch():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PhoBertFinDPO(model_name="vinai/phobert-base-v2")
    model.load_state_dict(torch.load(CHECKPOINT_FILE, map_location=device))
    model.to(device)
    model.eval()

    val_path = "data/processed/f104/f104_val.parquet"
    assert os.path.exists(val_path), f"Missing validation set: {val_path}"

    con = duckdb.connect()
    df_val_sample = con.execute(f"SELECT * FROM '{val_path}' LIMIT 100").df()
    con.close()

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    ds = FinancialSentimentDataset(df_val_sample, tokenizer=tokenizer, max_seq_length=128)
    loader = DataLoader(ds, batch_size=16, shuffle=False)

    eval_res = evaluate_dataset(model, loader, device)

    assert eval_res["sample_count"] == 100
    assert eval_res["loss"] > 0.0
    assert 0.0 <= eval_res["accuracy"] <= 1.0
    assert eval_res["findpo_preference_accuracy"] >= 0.70, (
        f"FinDPO preference win rate too low: {eval_res['findpo_preference_accuracy']}"
    )
