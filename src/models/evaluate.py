"""src/models/evaluate.py

Evaluation Module for PhoBERT-base with FinDPO Market Alignment.
Calculates:
1. Macro F1, Weighted F1, and Precision/Recall for 3-class sentiment.
2. FinDPO Preference Accuracy: % of cases where s(chosen) > s(rejected).
3. Confusion matrix across Negative, Neutral, and Positive.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, f1_score
from torch.utils.data import DataLoader

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def evaluate_dataset(
    model: torch.nn.Module,
    dataloader: DataLoader,
    device: torch.device,
) -> Dict[str, Any]:
    """Runs evaluation over a DataLoader and computes comprehensive metrics."""
    model.eval()
    all_preds: List[int] = []
    all_labels: List[int] = []
    preference_correct = 0
    total_preference_pairs = 0

    total_loss = 0.0
    total_batches = 0

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch.get("labels")
            if labels is not None:
                labels = labels.to(device)

            chosen_ids = batch.get("chosen_input_ids")
            chosen_mask = batch.get("chosen_attention_mask")
            rejected_ids = batch.get("rejected_input_ids")
            rejected_mask = batch.get("rejected_attention_mask")

            if chosen_ids is not None:
                chosen_ids = chosen_ids.to(device)
                chosen_mask = chosen_mask.to(device)
                rejected_ids = rejected_ids.to(device)
                rejected_mask = rejected_mask.to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
                chosen_input_ids=chosen_ids,
                chosen_attention_mask=chosen_mask,
                rejected_input_ids=rejected_ids,
                rejected_attention_mask=rejected_mask,
            )

            if outputs.loss is not None:
                total_loss += outputs.loss.item()
                total_batches += 1

            if outputs.sentiment_logits is not None and labels is not None:
                preds = torch.argmax(outputs.sentiment_logits, dim=-1).cpu().numpy()
                all_preds.extend(preds.tolist())
                all_labels.extend(labels.cpu().numpy().tolist())

            if outputs.chosen_scores is not None and outputs.rejected_scores is not None:
                wins = (outputs.chosen_scores > outputs.rejected_scores).sum().item()
                preference_correct += wins
                total_preference_pairs += outputs.chosen_scores.size(0)

    avg_loss = total_loss / max(total_batches, 1)

    f1_macro = float(f1_score(all_labels, all_preds, average="macro")) if all_labels else 0.0
    f1_weighted = float(f1_score(all_labels, all_preds, average="weighted")) if all_labels else 0.0
    acc = float(np.mean(np.array(all_preds) == np.array(all_labels))) if all_labels else 0.0

    pref_acc = (preference_correct / total_preference_pairs) if total_preference_pairs > 0 else 0.0
    conf_mat = confusion_matrix(all_labels, all_preds).tolist() if all_labels else []

    return {
        "loss": float(avg_loss),
        "accuracy": float(acc),
        "f1_macro": float(f1_macro),
        "f1_weighted": float(f1_weighted),
        "findpo_preference_accuracy": float(pref_acc),
        "total_preference_pairs_evaluated": total_preference_pairs,
        "confusion_matrix": conf_mat,
        "sample_count": len(all_labels),
    }


if __name__ == "__main__":
    import argparse
    import os
    import duckdb
    from transformers import AutoTokenizer
    from src.models.phobert_findpo import PhoBertFinDPO
    from src.models.train_sentiment import FinancialSentimentDataset

    parser = argparse.ArgumentParser(description="Evaluate PhoBertFinDPO checkpoint on dataset")
    parser.add_argument("--checkpoint", default="out/models/phobert_base_findpo/best_model.pt", help="Path to checkpoint")
    parser.add_argument("--dataset", default="data/processed/f104/f104_val.parquet", help="Path to Parquet dataset")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--max-samples", type=int, default=None, help="Max evaluation samples")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Evaluate] Loading dataset: {args.dataset}")
    con = duckdb.connect()
    limit_sql = f"LIMIT {args.max_samples}" if args.max_samples else ""
    df = con.execute(f"SELECT * FROM '{args.dataset}' {limit_sql}").df()
    con.close()
    print(f"[Evaluate] Loaded {len(df):,} events. Device: {device}")

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    ds = FinancialSentimentDataset(df, tokenizer=tokenizer, max_seq_length=128)
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False)

    model = PhoBertFinDPO(model_name="vinai/phobert-base-v2")
    if os.path.exists(args.checkpoint):
        print(f"[Evaluate] Loading weights from {args.checkpoint}")
        model.load_state_dict(torch.load(args.checkpoint, map_location=device), strict=False)
    model.to(device)

    metrics = evaluate_dataset(model, loader, device)
    print("\n" + "=" * 60)
    print(" EVALUATION RESULTS:")
    print(f"  Loss             : {metrics['loss']:.4f}")
    print(f"  Accuracy         : {metrics['accuracy'] * 100:.2f}%")
    print(f"  F1 Macro         : {metrics['f1_macro']:.4f}")
    print(f"  F1 Weighted      : {metrics['f1_weighted']:.4f}")
    print(f"  FinDPO Win Rate  : {metrics['findpo_preference_accuracy'] * 100:.2f}%")
    print(f"  Confusion Matrix : {metrics['confusion_matrix']}")
    print("=" * 60)

