"""src/models/train_multimodal_fusion.py

F302 Training Pipeline: Trains Multimodal Cross-Attention Fusion Model on GPU.
Combines PhoBERT-base text representations with 24 RankGauss accounting/technical
features and Macro Regime embeddings to predict real market forward direction (T+5)
and financial sentiment.

Includes full crash resilience, atomic checkpointing, interrupt handling, and resume capability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import numpy as np
import pandas as pd
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, get_cosine_schedule_with_warmup
import yaml  # type: ignore[import-untyped]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from src.models.multimodal_fusion import (
    DEFAULT_FUNDAMENTAL_FEATURES,
    REGIME_TO_ID,
    MultimodalCrossAttentionFusion,
)
from src.models.training_checkpoint import (
    AtomicCheckpointSaver,
    GracefulInterruptHandler,
    load_resumable_checkpoint,
)


class MultimodalFinancialDataset(Dataset):
    """PyTorch Dataset loading multimodal text, fundamental ratios, and regime states."""

    def __init__(
        self,
        df: pd.DataFrame,
        tokenizer: Any,
        feature_columns: List[str] = DEFAULT_FUNDAMENTAL_FEATURES,
        max_seq_length: int = 128,
        text_column: str = "context_text",
        sentiment_column: str = "sentiment_label",
        direction_column: str = "target_dir_t5",
        return_column: str = "ret_t5_pct",
        regime_column: str = "market_regime",
        pre_tokenize: bool = True,
        chunk_size: int = 50000,
    ) -> None:
        self.length = len(df)
        self.feature_columns = feature_columns
        self.max_seq_length = max_seq_length

        # 1. Tabular Fundamentals: Extract and convert to Float32 Tensor
        fund_vals = df[feature_columns].copy().fillna(0.0).to_numpy(dtype=np.float32)
        # Cap extreme values to [-5.0, 5.0] for stable gradient flow
        fund_vals = np.clip(fund_vals, -5.0, 5.0)
        self.fundamentals = torch.tensor(fund_vals, dtype=torch.float32)

        # 2. Market Regime IDs
        regime_series = df[regime_column].fillna("SIDEWAYS").astype(str)
        regime_ids = [REGIME_TO_ID.get(r, REGIME_TO_ID["SIDEWAYS"]) for r in regime_series]
        self.regime_ids = torch.tensor(regime_ids, dtype=torch.long)

        # 3. Target Labels
        # Sentiment label (0, 1, 2)
        self.sentiment_labels = torch.tensor(
            df[sentiment_column].fillna(1).astype(int).to_numpy(), dtype=torch.long
        )

        # Direction label: map {-1: 0, 0: 1, 1: 2}
        raw_dirs = df[direction_column].fillna(0).astype(int).to_numpy()
        dir_labels = raw_dirs + 1  # [-1, 0, 1] -> [0, 1, 2]
        dir_labels = np.clip(dir_labels, 0, 2)
        self.direction_labels = torch.tensor(dir_labels, dtype=torch.long)

        # Continuous return target
        ret_vals = df[return_column].fillna(0.0).astype(float).to_numpy(dtype=np.float32)
        ret_vals = np.clip(ret_vals, -1.0, 1.0)
        self.return_targets = torch.tensor(ret_vals, dtype=torch.float32)

        # 4. Text Tokenization
        self.pre_tokenize = pre_tokenize
        texts = df[text_column].astype(str).tolist()

        if pre_tokenize and self.length > 0:
            print(f" -> Pre-tokenizing {self.length:,} multimodal texts into RAM (max_len={max_seq_length})...")
            self.input_ids = torch.empty((self.length, max_seq_length), dtype=torch.int32)
            self.attention_mask = torch.empty((self.length, max_seq_length), dtype=torch.int8)

            t0 = time.time()
            for i in range(0, self.length, chunk_size):
                end_i = min(i + chunk_size, self.length)
                sub_texts = texts[i:end_i]
                enc = tokenizer(
                    sub_texts,
                    max_length=max_seq_length,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )
                self.input_ids[i:end_i] = enc["input_ids"].to(torch.int32)
                self.attention_mask[i:end_i] = enc["attention_mask"].to(torch.int8)

            duration = time.time() - t0
            print(f" -> Tokenized {self.length:,} texts in {duration:.2f}s ({self.length / max(duration, 0.001):.0f} texts/s)")
        else:
            self.texts = texts
            self.tokenizer = tokenizer

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        if self.pre_tokenize:
            return {
                "input_ids": self.input_ids[idx].long(),
                "attention_mask": self.attention_mask[idx].long(),
                "fundamentals": self.fundamentals[idx],
                "regime_id": self.regime_ids[idx],
                "sentiment_label": self.sentiment_labels[idx],
                "direction_label": self.direction_labels[idx],
                "return_target": self.return_targets[idx],
            }

        enc = self.tokenizer(
            self.texts[idx],
            max_length=self.max_seq_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "fundamentals": self.fundamentals[idx],
            "regime_id": self.regime_ids[idx],
            "sentiment_label": self.sentiment_labels[idx],
            "direction_label": self.direction_labels[idx],
            "return_target": self.return_targets[idx],
        }


def evaluate_multimodal(
    model: MultimodalCrossAttentionFusion,
    dataloader: DataLoader,
    device: torch.device,
    max_samples: Optional[int] = None,
) -> Dict[str, float]:
    """Evaluates Multimodal Cross-Attention Fusion across sentiment and direction heads.

    Args:
        model: Multimodal model
        dataloader: Evaluation DataLoader
        device: Active device
        max_samples: Optional maximum number of samples to evaluate (for fast intermediate validation).
    """
    model.eval()
    total_loss = 0.0
    sentiment_correct = 0
    direction_correct = 0
    total_samples = 0

    all_dir_preds: List[int] = []
    all_dir_targets: List[int] = []
    all_sent_preds: List[int] = []
    all_sent_targets: List[int] = []

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            fundamentals = batch["fundamentals"].to(device)
            regime_ids = batch["regime_id"].to(device)
            sent_labels = batch["sentiment_label"].to(device)
            dir_labels = batch["direction_label"].to(device)
            ret_targets = batch["return_target"].to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                fundamentals=fundamentals,
                regime_ids=regime_ids,
                sentiment_labels=sent_labels,
                direction_labels=dir_labels,
                return_targets=ret_targets,
            )

            if outputs.loss is not None:
                total_loss += outputs.loss.item() * len(input_ids)

            # Sentiment accuracy
            if outputs.sentiment_logits is not None:
                sent_preds = outputs.sentiment_logits.argmax(dim=-1)
                sentiment_correct += (sent_preds == sent_labels).sum().item()
                all_sent_preds.extend(sent_preds.cpu().tolist())
                all_sent_targets.extend(sent_labels.cpu().tolist())

            # Direction accuracy
            if outputs.direction_logits is not None:
                dir_preds = outputs.direction_logits.argmax(dim=-1)
                direction_correct += (dir_preds == dir_labels).sum().item()
                all_dir_preds.extend(dir_preds.cpu().tolist())
                all_dir_targets.extend(dir_labels.cpu().tolist())

            total_samples += len(input_ids)
            if max_samples is not None and total_samples >= max_samples:
                break

    avg_loss = total_loss / max(total_samples, 1)
    sent_acc = sentiment_correct / max(total_samples, 1)
    dir_acc = direction_correct / max(total_samples, 1)

    # Compute Macro F1 for direction and sentiment
    from sklearn.metrics import f1_score

    dir_f1_macro = float(f1_score(all_dir_targets, all_dir_preds, average="macro", zero_division=0))
    sent_f1_macro = float(f1_score(all_sent_targets, all_sent_preds, average="macro", zero_division=0))

    return {
        "loss": round(avg_loss, 4),
        "samples": total_samples,
        "sentiment_accuracy": round(sent_acc, 4),
        "sentiment_f1_macro": round(sent_f1_macro, 4),
        "direction_accuracy": round(dir_acc, 4),
        "direction_f1_macro": round(dir_f1_macro, 4),
    }


def train_multimodal_fusion(
    config_path: str = "configs/multimodal_fusion.yaml",
    max_train_samples: Optional[int] = None,
    max_val_samples: Optional[int] = None,
    epochs_override: Optional[int] = None,
    resume: bool = False,
    resume_path: Optional[str] = None,
    init_weights: Optional[str] = None,
) -> Dict[str, Any]:
    """Main training routine for F302 Multimodal Cross-Attention Fusion."""
    start_time = time.time()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 1. Hardware Setup & Safeguards
    device_name = cfg.get("hardware", {}).get("device", "cuda")
    if device_name == "cuda" and not torch.cuda.is_available():
        print("[WARNING] CUDA requested but not available. Falling back to CPU.")
        device = torch.device("cpu")
    else:
        device = torch.device(device_name if torch.cuda.is_available() else "cpu")

    max_vram_gb = cfg.get("hardware", {}).get("max_vram_gb", 5.2)

    print("=" * 85)
    print(" F302: MULTIMODAL CROSS-ATTENTION FUSION TRAINING")
    print(f" Config File    : {config_path}")
    print(f" Active Device  : {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")
    print(f" Max VRAM Guard : <= {max_vram_gb} GB")
    print("=" * 85)

    # 2. Tokenizer & Dataset Loading
    phobert_backbone = cfg["model"].get("phobert_backbone", "vinai/phobert-base-v2")
    max_seq_len = cfg["model"].get("max_seq_length", 128)
    tokenizer = AutoTokenizer.from_pretrained(phobert_backbone)

    train_path = cfg["data"]["train_path"]
    val_path = cfg["data"]["val_path"]

    print(f"\n[1/5] Loading Parquet datasets from '{train_path}'...")
    con = duckdb.connect()
    df_train = con.execute(f"SELECT * FROM '{train_path}'").df()
    df_val = con.execute(f"SELECT * FROM '{val_path}'").df()
    con.close()

    if max_train_samples and len(df_train) > max_train_samples:
        df_train = df_train.sample(n=max_train_samples, random_state=42).reset_index(drop=True)
        print(f" -> Subsampled Train set to {len(df_train):,} events")

    if max_val_samples and len(df_val) > max_val_samples:
        df_val = df_val.sample(n=max_val_samples, random_state=42).reset_index(drop=True)
        print(f" -> Subsampled Val set to {len(df_val):,} events")

    feature_cols = cfg["data"].get("fundamental_features", DEFAULT_FUNDAMENTAL_FEATURES)

    train_ds = MultimodalFinancialDataset(
        df=df_train,
        tokenizer=tokenizer,
        feature_columns=feature_cols,
        max_seq_length=max_seq_len,
        pre_tokenize=True,
    )
    val_ds = MultimodalFinancialDataset(
        df=df_val,
        tokenizer=tokenizer,
        feature_columns=feature_cols,
        max_seq_length=max_seq_len,
        pre_tokenize=True,
    )

    batch_size = cfg["training"].get("per_device_train_batch_size", 64)
    eval_batch_size = cfg["training"].get("per_device_eval_batch_size", 128)
    grad_accum_steps = cfg["training"].get("gradient_accumulation_steps", 1)
    pin_mem = device.type == "cuda"

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, pin_memory=pin_mem)
    val_loader = DataLoader(val_ds, batch_size=eval_batch_size, shuffle=False, pin_memory=pin_mem)

    # 3. Model Architecture Instantiation
    print("\n[2/5] Instantiating MultimodalCrossAttentionFusion...")
    ckpt_path = cfg["model"].get("phobert_checkpoint", "out/models/phobert_base_findpo/best_model.pt")
    if not os.path.exists(ckpt_path):
        ckpt_path = None

    model = MultimodalCrossAttentionFusion(
        phobert_model_name=phobert_backbone,
        phobert_checkpoint=ckpt_path,
        freeze_phobert_layers=cfg["model"].get("freeze_phobert_layers", 8),
        num_fundamental_features=len(feature_cols),
        hidden_dim=cfg["model"].get("hidden_dim", 128),
        num_heads=cfg["model"].get("num_heads", 4),
        num_fusion_layers=cfg["model"].get("num_fusion_layers", 2),
        dropout_prob=cfg["model"].get("dropout_prob", 0.15),
        weight_sentiment=cfg["model"]["loss_weights"].get("sentiment", 0.35),
        weight_direction=cfg["model"]["loss_weights"].get("direction", 0.45),
        weight_return=cfg["model"]["loss_weights"].get("return", 0.20),
    )
    model.to(device)

    # 4. Optimization, Scheduler & Checkpoint Setup
    num_epochs = epochs_override or cfg["training"].get("num_train_epochs", 3)
    lr = float(cfg["training"].get("learning_rate", 3.0e-5))
    weight_decay = float(cfg["training"].get("weight_decay", 0.01))

    # Separate trainable parameters
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = AdamW(trainable_params, lr=lr, weight_decay=weight_decay)

    total_steps = (len(train_loader) // grad_accum_steps) * num_epochs
    warmup_steps = int(total_steps * cfg["training"].get("warmup_ratio", 0.1))
    scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

    use_fp16 = cfg["training"].get("fp16", True) and (device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_fp16) if device.type == "cuda" else torch.amp.GradScaler("cpu", enabled=False)

    output_dir = pathlib.Path(cfg["training"].get("output_dir", "out/models/multimodal_fusion"))
    output_dir.mkdir(parents=True, exist_ok=True)

    saver = AtomicCheckpointSaver(output_dir)
    interrupt_handler = GracefulInterruptHandler()

    start_epoch = 1
    global_step = 0
    best_dir_acc = -1.0
    training_history: List[Dict[str, Any]] = []

    # Restore previous benchmark if best_model_meta.json exists
    meta_path = output_dir / "best_model_meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                mdata = json.load(f)
                prev_best = float(mdata.get("metric_value", -1.0))
                if prev_best > best_dir_acc:
                    best_dir_acc = prev_best
                    print(f" -> Preserved existing benchmark best direction accuracy: {best_dir_acc * 100:.2f}%")
        except Exception:
            pass

    # Optional pre-trained weights initialization (e.g. out/models/multimodal_fusion/best_model.pt)
    weights_candidate = init_weights or cfg.get("training", {}).get("init_weights") or cfg["model"].get("fusion_checkpoint")
    if weights_candidate and pathlib.Path(weights_candidate).exists():
        print(f"\n -> Loading initial weights from existing checkpoint '{weights_candidate}'...")
        try:
            state = torch.load(weights_candidate, map_location=device, weights_only=False)
        except TypeError:
            state = torch.load(weights_candidate, map_location=device)
        if "model_state_dict" in state:
            model.load_state_dict(state["model_state_dict"])
        else:
            model.load_state_dict(state)
        print(f" -> Pre-trained multimodal weights loaded successfully from '{weights_candidate}'!")

    # Handle Checkpoint Resuming
    target_resume = resume_path or (str(output_dir / "last_checkpoint.pt") if resume else None)
    if target_resume and pathlib.Path(target_resume).exists():
        start_epoch, global_step, best_dir_acc, training_history = load_resumable_checkpoint(
            checkpoint_path=target_resume,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            device=device,
        )
        print(f" -> Resuming training from Epoch {start_epoch} (Global step: {global_step}, Best Direction Acc: {best_dir_acc:.4f})")
    elif resume:
        print(f" -> [NOTICE] Resume requested but no existing checkpoint found at '{target_resume}'. Starting fresh.")

    eval_steps = cfg["training"].get("eval_steps", 1000)
    eval_subset_samples = cfg["training"].get("eval_subset_samples", 4000)
    checkpoint_steps = cfg["training"].get("checkpoint_steps", eval_steps)

    print(f"\n[3/5] Starting Multimodal Training: Epochs {start_epoch}->{num_epochs} | Total Steps: {total_steps} | FP16: {use_fp16}")
    print(f" -> Batch Size: {batch_size} (Grad Accum: {grad_accum_steps}) | Eval Batch Size: {eval_batch_size}")
    print(f" -> Step Evaluation: Every {eval_steps} steps on {eval_subset_samples:,} samples | Checkpoint: Every {checkpoint_steps} steps")
    current_epoch = start_epoch

    try:
        for epoch in range(start_epoch, num_epochs + 1):
            current_epoch = epoch
            if interrupt_handler.interrupted:
                saver.save_emergency_checkpoint(
                    model=model,
                    optimizer=optimizer,
                    scheduler=scheduler,
                    scaler=scaler,
                    epoch=epoch,
                    global_step=global_step,
                    best_metric=best_dir_acc,
                    training_history=training_history,
                    reason="User interrupt before epoch start",
                )
                break

            model.train()
            running_loss = 0.0
            epoch_start = time.time()
            optimizer.zero_grad()

            for step, batch in enumerate(train_loader, start=1):
                if interrupt_handler.interrupted:
                    print(f"\n[INTERRUPT DETECTED at Step {step}] Saving emergency checkpoint and halting gracefully...")
                    saver.save_emergency_checkpoint(
                        model=model,
                        optimizer=optimizer,
                        scheduler=scheduler,
                        scaler=scaler,
                        epoch=epoch,
                        global_step=global_step,
                        best_metric=best_dir_acc,
                        training_history=training_history,
                        reason=f"User interrupt at Epoch {epoch}, Step {step}",
                    )
                    break

                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                fundamentals = batch["fundamentals"].to(device)
                regime_ids = batch["regime_id"].to(device)
                sent_labels = batch["sentiment_label"].to(device)
                dir_labels = batch["direction_label"].to(device)
                ret_targets = batch["return_target"].to(device)

                with torch.amp.autocast(device_type=device.type, enabled=use_fp16):
                    outputs = model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        fundamentals=fundamentals,
                        regime_ids=regime_ids,
                        sentiment_labels=sent_labels,
                        direction_labels=dir_labels,
                        return_targets=ret_targets,
                    )
                    loss = outputs.loss / grad_accum_steps

                scaler.scale(loss).backward()
                running_loss += outputs.loss.item()

                if step % grad_accum_steps == 0 or step == len(train_loader):
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad()
                    scheduler.step()
                    global_step += 1

                    if global_step % 50 == 0:
                        vram_mb = (torch.cuda.max_memory_allocated() / (1024 * 1024)) if device.type == "cuda" else 0.0
                        lr_curr = scheduler.get_last_lr()[0]
                        print(
                            f"  [Epoch {epoch}/{num_epochs}] Step {global_step}/{total_steps} | "
                            f"Loss: {running_loss / step:.4f} | LR: {lr_curr:.2e} | VRAM: {vram_mb:.0f} MB"
                        )

                # Periodic fast evaluation
                if global_step > 0 and global_step % eval_steps == 0:
                    t_eval_0 = time.time()
                    val_metrics = evaluate_multimodal(model, val_loader, device, max_samples=eval_subset_samples)
                    eval_dur = time.time() - t_eval_0
                    print(
                        f"\n--- [Fast Evaluation at Step {global_step} ({val_metrics['samples']:,} samples in {eval_dur:.1f}s)] --- "
                        f"Val Loss: {val_metrics['loss']} | Dir Acc: {val_metrics['direction_accuracy'] * 100:.2f}% | "
                        f"Dir F1: {val_metrics['direction_f1_macro']:.4f} | Sent Acc: {val_metrics['sentiment_accuracy'] * 100:.2f}%"
                    )

                    if val_metrics["direction_accuracy"] > best_dir_acc:
                        best_dir_acc = val_metrics["direction_accuracy"]
                        saver.save_best_model(model, epoch, best_dir_acc, metric_name="direction_accuracy")
                        print(f"  >>> [NEW BEST MODEL] Saved best_model.pt (Dir Acc: {best_dir_acc * 100:.2f}%)")

                    model.train()

                # Periodic atomic checkpointing (safeguard against sudden power loss or interrupts)
                if global_step > 0 and global_step % checkpoint_steps == 0:
                    saver.save_checkpoint(
                        model=model,
                        optimizer=optimizer,
                        scheduler=scheduler,
                        scaler=scaler,
                        epoch=epoch,
                        global_step=global_step,
                        best_metric=best_dir_acc,
                        training_history=training_history,
                        config=cfg,
                        filename="last_checkpoint.pt",
                    )

            if interrupt_handler.interrupted:
                break

            # Epoch end full evaluation
            epoch_time = time.time() - epoch_start
            t_val_start = time.time()
            print(f"\n -> Running Full Validation on all {len(val_ds):,} samples...")
            val_metrics = evaluate_multimodal(model, val_loader, device, max_samples=None)
            val_dur = time.time() - t_val_start
            vram_peak_gb = (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0

            print(
                f"\n=== Completed Epoch {epoch}/{num_epochs} in {epoch_time:.2f}s (Full Val: {val_dur:.1f}s) ===\n"
                f"  Val Loss       : {val_metrics['loss']}\n"
                f"  Direction Acc  : {val_metrics['direction_accuracy'] * 100:.2f}% (Macro F1: {val_metrics['direction_f1_macro']:.4f})\n"
                f"  Sentiment Acc  : {val_metrics['sentiment_accuracy'] * 100:.2f}% (Macro F1: {val_metrics['sentiment_f1_macro']:.4f})\n"
                f"  Peak VRAM      : {vram_peak_gb:.2f} GB (Safe <= {max_vram_gb} GB: {vram_peak_gb <= max_vram_gb})"
            )

            if val_metrics["direction_accuracy"] > best_dir_acc:
                best_dir_acc = val_metrics["direction_accuracy"]
                saver.save_best_model(model, epoch, best_dir_acc, metric_name="direction_accuracy")
                print("  >>> [NEW BEST MODEL] Saved best_model.pt")

            training_history.append({
                "epoch": epoch,
                "train_loss": running_loss / max(len(train_loader), 1),
                "val_loss": val_metrics["loss"],
                "direction_accuracy": val_metrics["direction_accuracy"],
                "direction_f1_macro": val_metrics["direction_f1_macro"],
                "sentiment_accuracy": val_metrics["sentiment_accuracy"],
                "sentiment_f1_macro": val_metrics["sentiment_f1_macro"],
                "peak_vram_gb": vram_peak_gb,
                "epoch_duration_sec": epoch_time,
            })

            # Save atomic checkpoint at epoch boundary for safe resumption
            saver.save_checkpoint(
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                epoch=epoch + 1,
                global_step=global_step,
                best_metric=best_dir_acc,
                training_history=training_history,
                config=cfg,
                filename="last_checkpoint.pt",
            )
            print(f"  -> Saved atomic last_checkpoint.pt (Ready for resume at Epoch {epoch + 1})")

            if device.type == "cuda":
                torch.cuda.empty_cache()

    except Exception as err:
        print(f"\n[UNEXPECTED CRASH / EXCEPTION] {err}")
        saver.save_emergency_checkpoint(
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            epoch=current_epoch,
            global_step=global_step,
            best_metric=best_dir_acc,
            training_history=training_history,
            reason=f"Crash exception: {err}",
        )
        interrupt_handler.close()
        raise
    finally:
        interrupt_handler.close()

    # 5. Export Final Summary
    print("\n[5/5] Saving final multimodal training summary...")
    summary = {
        "model_name": cfg["model"]["name"],
        "trained_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_duration_sec": time.time() - start_time,
        "best_val_direction_accuracy": best_dir_acc,
        "peak_vram_gb": (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0,
        "vram_budget_safe": (torch.cuda.max_memory_allocated() / 1e9 <= max_vram_gb) if device.type == "cuda" else True,
        "history": training_history,
    }
    metrics_file = output_dir / "training_metrics.json"
    metrics_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f" -> Wrote multimodal metrics to {metrics_file.resolve()}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train F302 Multimodal Cross-Attention Fusion")
    parser.add_argument("--config", default="configs/multimodal_fusion.yaml", help="Path to config")
    parser.add_argument("--max-train-samples", type=int, default=None, help="Cap training samples")
    parser.add_argument("--max-val-samples", type=int, default=None, help="Cap validation samples")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs")
    parser.add_argument("--resume", action="store_true", help="Resume from last_checkpoint.pt")
    parser.add_argument("--resume-path", default=None, help="Explicit path to resume checkpoint")
    parser.add_argument("--init-weights", default=None, help="Path to initial model weights")
    args = parser.parse_args()

    train_multimodal_fusion(
        config_path=args.config,
        max_train_samples=args.max_train_samples,
        max_val_samples=args.max_val_samples,
        epochs_override=args.epochs,
        resume=args.resume,
        resume_path=args.resume_path,
        init_weights=args.init_weights,
    )
