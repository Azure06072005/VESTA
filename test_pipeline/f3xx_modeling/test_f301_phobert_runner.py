"""test_pipeline/f3xx_modeling/test_f301_phobert_runner.py

Runner for F301: PhoBERT-base Fine-Tuning with FinDPO Market Alignment.
Evaluates model checkpoints, validates VRAM constraints, and calculates
Macro F1 and FinDPO preference win rates.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

import duckdb
import torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from models.evaluate import evaluate_dataset
from models.phobert_findpo import PhoBertFinDPO
from models.train_sentiment import FinancialSentimentDataset


def run_f301_test(
    checkpoint_dir: str = "out/models/phobert_base_findpo",
    dataset_path: str = "data/processed/f104/f104_val.parquet",
    sample_limit: int = 500,
    out_path: str | None = None,
) -> dict[str, object]:
    ckpt_dir = pathlib.Path(checkpoint_dir)
    ckpt_file = ckpt_dir / "best_model.pt"
    metrics_file = ckpt_dir / "training_metrics.json"

    print("=" * 80)
    print(" [F301] PHOBERT-BASE FIN-DPO EVALUATION RUNNER")
    print(f" Checkpoint : {ckpt_file}")
    print(f" Dataset    : {dataset_path} (limit={sample_limit})")
    print("=" * 80)

    if not ckpt_file.exists():
        return {
            "status": "FAIL",
            "error": f"Checkpoint {ckpt_file} not found. Model must be trained first.",
        }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f" -> Active Device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")

    # 1. Load model checkpoint
    t0 = time.time()
    model = PhoBertFinDPO(model_name="vinai/phobert-base-v2")
    state_dict = torch.load(ckpt_file, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    load_time = time.time() - t0
    print(f" -> Successfully loaded model weights in {load_time:.2f}s")

    # 2. Load dataset sample
    con = duckdb.connect()
    df_eval = con.execute(f"SELECT * FROM '{dataset_path}' LIMIT {sample_limit}").df()
    con.close()

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    ds = FinancialSentimentDataset(df_eval, tokenizer=tokenizer, max_seq_length=128)
    loader = DataLoader(ds, batch_size=32, shuffle=False, pin_memory=(device.type == "cuda"))

    # 3. Evaluate
    eval_res = evaluate_dataset(model, loader, device)
    peak_vram_gb = (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0

    training_meta = {}
    if metrics_file.exists():
        try:
            training_meta = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    status = "PASS" if (eval_res["findpo_preference_accuracy"] >= 0.70 and peak_vram_gb <= 5.2) else "FAIL"

    result: dict[str, object] = {
        "status": status,
        "device": str(device),
        "peak_vram_gb": round(peak_vram_gb, 3),
        "vram_budget_safe": peak_vram_gb <= 5.2,
        "sample_count": eval_res["sample_count"],
        "loss": round(eval_res["loss"], 4),
        "accuracy": round(eval_res["accuracy"], 4),
        "f1_macro": round(eval_res["f1_macro"], 4),
        "f1_weighted": round(eval_res["f1_weighted"], 4),
        "findpo_preference_accuracy": round(eval_res["findpo_preference_accuracy"], 4),
        "training_metadata": training_meta,
    }

    print(f"\n [F301 EVALUATION RESULT]")
    print(f"  -> Accuracy           : {result['accuracy'] * 100:.2f}%")
    print(f"  -> F1 Macro           : {result['f1_macro']:.4f}")
    print(f"  -> FinDPO Win Rate    : {result['findpo_preference_accuracy'] * 100:.2f}%")
    print(f"  -> Peak VRAM          : {result['peak_vram_gb']} GB (Safe <= 5.2GB: {result['vram_budget_safe']})")
    print(f"  -> Status             : {status}")

    if out_path:
        out_p = pathlib.Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"  -> Wrote runner report to {out_p}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F301 PhoBERT-base FinDPO Test Runner")
    parser.add_argument("--checkpoint-dir", default="out/models/phobert_base_findpo")
    parser.add_argument("--dataset", default="data/processed/f104/f104_val.parquet")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    run_f301_test(
        checkpoint_dir=args.checkpoint_dir,
        dataset_path=args.dataset,
        sample_limit=args.limit,
        out_path=args.out,
    )
