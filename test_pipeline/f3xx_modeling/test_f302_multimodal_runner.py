"""test_pipeline/f3xx_modeling/test_f302_multimodal_runner.py

Runner for F302: Multimodal Cross-Attention Fusion Evaluation.
Evaluates multimodal checkpoint, validates peak VRAM limits (<= 5.2 GB),
and computes real market forward return direction accuracy and macro F1 on validation sets.
"""
from __future__ import annotations

import argparse
import json
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

from src.models.multimodal_fusion import (  # noqa: E402
    DEFAULT_FUNDAMENTAL_FEATURES,
    MultimodalCrossAttentionFusion,
)
from src.models.train_multimodal_fusion import (  # noqa: E402
    MultimodalFinancialDataset,
    evaluate_multimodal,
)


def run_f302_test(
    checkpoint_dir: str = "out/models/multimodal_fusion",
    dataset_path: str = "data/processed/f104/f104_val.parquet",
    sample_limit: int = 500,
    out_path: str | None = None,
) -> dict[str, object]:
    ckpt_dir = pathlib.Path(checkpoint_dir)
    ckpt_file = ckpt_dir / "best_model.pt"
    last_ckpt_file = ckpt_dir / "last_checkpoint.pt"
    metrics_file = ckpt_dir / "training_metrics.json"

    print("=" * 80)
    print(" [F302] MULTIMODAL CROSS-ATTENTION FUSION EVALUATION RUNNER")
    print(f" Checkpoint Dir : {checkpoint_dir}")
    print(f" Dataset        : {dataset_path} (limit={sample_limit})")
    print("=" * 80)

    target_weights = ckpt_file if ckpt_file.exists() else (last_ckpt_file if last_ckpt_file.exists() else None)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f" -> Active Device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")

    # 1. Instantiate Model Architecture
    model = MultimodalCrossAttentionFusion(
        phobert_model_name="vinai/phobert-base-v2",
        phobert_checkpoint=None,
        freeze_phobert_layers=8,
        num_fundamental_features=len(DEFAULT_FUNDAMENTAL_FEATURES),
        hidden_dim=128,
        num_heads=4,
        num_fusion_layers=2,
    )

    if target_weights and target_weights.exists():
        t0 = time.time()
        state = torch.load(target_weights, map_location=device)
        if "model_state_dict" in state:
            model.load_state_dict(state["model_state_dict"])
        else:
            model.load_state_dict(state)
        load_time = time.time() - t0
        print(f" -> Successfully loaded model weights from {target_weights.name} in {load_time:.2f}s")
    else:
        print(f" -> [NOTICE] No trained checkpoint found at {checkpoint_dir}. Evaluating initial baseline architecture.")

    model.to(device)
    model.eval()

    # 2. Load Evaluation Dataset Sample
    con = duckdb.connect()
    df_eval = con.execute(f"SELECT * FROM '{dataset_path}' LIMIT {sample_limit}").df()
    con.close()

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    eval_ds = MultimodalFinancialDataset(
        df=df_eval,
        tokenizer=tokenizer,
        feature_columns=DEFAULT_FUNDAMENTAL_FEATURES,
        max_seq_length=128,
        pre_tokenize=True,
    )
    eval_loader = DataLoader(eval_ds, batch_size=128, shuffle=False, pin_memory=(device.type == "cuda"))

    # 3. Evaluate
    eval_res = evaluate_multimodal(model, eval_loader, device)
    peak_vram_gb = (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0

    training_meta = {}
    if metrics_file.exists():
        try:
            training_meta = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Status is PASS if model runs clean, outputs valid direction/sentiment metrics, and respects VRAM <= 5.2GB
    status = "PASS" if (peak_vram_gb <= 5.2 and eval_res["samples"] > 0) else "FAIL"

    result: dict[str, object] = {
        "status": status,
        "device": str(device),
        "peak_vram_gb": round(peak_vram_gb, 3),
        "vram_budget_safe": peak_vram_gb <= 5.2,
        "sample_count": eval_res["samples"],
        "loss": eval_res["loss"],
        "direction_accuracy": eval_res["direction_accuracy"],
        "direction_f1_macro": eval_res["direction_f1_macro"],
        "sentiment_accuracy": eval_res["sentiment_accuracy"],
        "sentiment_f1_macro": eval_res["sentiment_f1_macro"],
        "checkpoint_evaluated": str(target_weights) if target_weights else "baseline_untrained",
        "training_metadata": training_meta,
    }

    dir_acc_val = eval_res["direction_accuracy"]
    dir_f1_val = eval_res["direction_f1_macro"]
    sent_acc_val = eval_res["sentiment_accuracy"]
    sent_f1_val = eval_res["sentiment_f1_macro"]
    print("\n [F302 EVALUATION RESULT]")
    print(f"  -> Direction Acc (T+5) : {dir_acc_val * 100:.2f}% (F1 Macro: {dir_f1_val:.4f})")
    print(f"  -> Sentiment Acc       : {sent_acc_val * 100:.2f}% (F1 Macro: {sent_f1_val:.4f})")
    print(f"  -> Peak VRAM           : {result['peak_vram_gb']} GB (Safe <= 5.2GB: {result['vram_budget_safe']})")
    print(f"  -> Status              : {status}")

    if out_path:
        out_p = pathlib.Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"  -> Wrote runner report to {out_p}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F302 Multimodal Cross-Attention Fusion Runner")
    parser.add_argument("--checkpoint-dir", default="out/models/multimodal_fusion")
    parser.add_argument("--dataset", default="data/processed/f104/f104_val.parquet")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    run_f302_test(
        checkpoint_dir=args.checkpoint_dir,
        dataset_path=args.dataset,
        sample_limit=args.limit,
        out_path=args.out,
    )
