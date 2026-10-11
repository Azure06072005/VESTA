"""src/models/train_sentiment.py

F301 Training Pipeline: Fine-tunes PhoBERT-base with FinDPO Market Alignment on GPU.
Hardware Budget Target: RTX 3060 6GB VRAM (Peak VRAM <= 5.2 GB).

Features:
1. Multi-Task Loss: Cross-Entropy (Sentiment 3-class) + FinDPO Policy Loss (Market Reversion).
2. Hardware Safeguards: Mixed-precision (fp16), gradient accumulation (2x), max_seq_length=128.
3. VRAM Telemetry: Tracks peak allocated VRAM at every evaluation step.
4. Auto-Checkpointing: Saves best model weights based on validation Macro F1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, get_cosine_schedule_with_warmup
import yaml

# Set UTF-8 encoding for console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from src.models.evaluate import evaluate_dataset
from src.models.phobert_findpo import PhoBertFinDPO
from src.models.training_checkpoint import (
    AtomicCheckpointSaver,
    GracefulInterruptHandler,
    load_resumable_checkpoint,
)


class FinancialSentimentDataset(Dataset):
    """PyTorch Dataset for financial text and FinDPO preference pairs."""

    def __init__(
        self,
        df: pd.DataFrame,
        tokenizer: Any,
        max_seq_length: int = 128,
        text_column: str = "context_text",
        label_column: str = "sentiment_label",
        chosen_column: str = "findpo_chosen",
        rejected_column: str = "findpo_rejected",
        pre_tokenize: bool = False,
        chunk_size: int = 50000,
    ) -> None:
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length
        self.text_col = text_column
        self.label_col = label_column
        self.chosen_col = chosen_column
        self.rejected_col = rejected_column
        self.pre_tokenize = pre_tokenize
        self.length = len(df)

        if pre_tokenize and self.length > 0:
            print(f" -> Pre-tokenizing {self.length:,} items into RAM tensors (chunk_size={chunk_size:,})...")
            texts = df[text_column].astype(str).tolist()
            labels = df[label_column].astype(int).tolist()
            self.labels = torch.tensor(labels, dtype=torch.long)

            has_pairs = (chosen_column in df.columns and rejected_column in df.columns)
            self.has_pairs = has_pairs

            chosen_texts = (
                [f"{t} -> {c}" for t, c in zip(texts, df[chosen_column].astype(str))]
                if has_pairs else []
            )
            rejected_texts = (
                [f"{t} -> {r}" for t, r in zip(texts, df[rejected_column].astype(str))]
                if has_pairs else []
            )

            self.input_ids = torch.empty((self.length, max_seq_length), dtype=torch.int32)
            self.attention_mask = torch.empty((self.length, max_seq_length), dtype=torch.int8)
            if has_pairs:
                self.chosen_ids = torch.empty((self.length, max_seq_length), dtype=torch.int32)
                self.chosen_mask = torch.empty((self.length, max_seq_length), dtype=torch.int8)
                self.rejected_ids = torch.empty((self.length, max_seq_length), dtype=torch.int32)
                self.rejected_mask = torch.empty((self.length, max_seq_length), dtype=torch.int8)

            t_tok_start = time.time()
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

                if has_pairs:
                    enc_ch = tokenizer(
                        chosen_texts[i:end_i],
                        max_length=max_seq_length,
                        padding="max_length",
                        truncation=True,
                        return_tensors="pt",
                    )
                    self.chosen_ids[i:end_i] = enc_ch["input_ids"].to(torch.int32)
                    self.chosen_mask[i:end_i] = enc_ch["attention_mask"].to(torch.int8)

                    enc_rej = tokenizer(
                        rejected_texts[i:end_i],
                        max_length=max_seq_length,
                        padding="max_length",
                        truncation=True,
                        return_tensors="pt",
                    )
                    self.rejected_ids[i:end_i] = enc_rej["input_ids"].to(torch.int32)
                    self.rejected_mask[i:end_i] = enc_rej["attention_mask"].to(torch.int8)

            tok_duration = time.time() - t_tok_start
            del texts, chosen_texts, rejected_texts
            import gc
            gc.collect()
            print(f" -> Finished pre-tokenization in {tok_duration:.2f}s ({self.length / max(tok_duration, 0.001):.0f} items/s)")
        else:
            self.df = df.reset_index(drop=True)
            self.texts = df[text_column].astype(str).tolist()
            self.labels = torch.tensor(df[label_column].astype(int).tolist(), dtype=torch.long)
            self.has_pairs = (chosen_column in df.columns and rejected_column in df.columns)
            if self.has_pairs:
                self.chosen_texts = [f"{t} -> {c}" for t, c in zip(self.texts, df[chosen_column].astype(str))]
                self.rejected_texts = [f"{t} -> {r}" for t, r in zip(self.texts, df[rejected_column].astype(str))]

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        if self.pre_tokenize:
            item: Dict[str, torch.Tensor] = {
                "input_ids": self.input_ids[idx].long(),
                "attention_mask": self.attention_mask[idx].long(),
                "labels": self.labels[idx],
            }
            if self.has_pairs:
                item["chosen_input_ids"] = self.chosen_ids[idx].long()
                item["chosen_attention_mask"] = self.chosen_mask[idx].long()
                item["rejected_input_ids"] = self.rejected_ids[idx].long()
                item["rejected_attention_mask"] = self.rejected_mask[idx].long()
            return item

        # On-the-fly tokenization fallback
        text = self.texts[idx]
        label = self.labels[idx]

        enc = self.tokenizer(
            text,
            max_length=self.max_seq_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        item: Dict[str, torch.Tensor] = {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": label,
        }

        if self.has_pairs:
            enc_chosen = self.tokenizer(
                self.chosen_texts[idx],
                max_length=self.max_seq_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            enc_rejected = self.tokenizer(
                self.rejected_texts[idx],
                max_length=self.max_seq_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            item["chosen_input_ids"] = enc_chosen["input_ids"].squeeze(0)
            item["chosen_attention_mask"] = enc_chosen["attention_mask"].squeeze(0)
            item["rejected_input_ids"] = enc_rejected["input_ids"].squeeze(0)
            item["rejected_attention_mask"] = enc_rejected["attention_mask"].squeeze(0)

        return item


def load_config(config_path: str = "configs/phobert_base.yaml") -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def train_phobert_findpo(
    config_path: str = "configs/phobert_base.yaml",
    max_train_samples: Optional[int] = None,
    max_val_samples: Optional[int] = None,
    epochs_override: Optional[int] = None,
    resume: bool = False,
    resume_path: Optional[str] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    cfg = load_config(config_path)

    # 1. Setup Device & VRAM budget
    device_name = cfg.get("hardware", {}).get("device", "cuda")
    if device_name == "cuda" and not torch.cuda.is_available():
        print("[WARNING] CUDA requested but not available. Falling back to CPU.")
        device = torch.device("cpu")
    else:
        device = torch.device(device_name if torch.cuda.is_available() else "cpu")

    max_vram_gb = cfg.get("hardware", {}).get("max_vram_gb", 5.2)

    print("=" * 85)
    print(" F301: PHOBERT-BASE FIN-DPO MARKET ALIGNMENT TRAINING")
    print(f" Config File    : {config_path}")
    print(f" Active Device  : {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")
    print(f" Max VRAM Guard : <= {max_vram_gb} GB")
    print("=" * 85)

    # 2. Tokenizer & Dataset Loading
    model_name = cfg["model"]["name"]
    max_seq_len = cfg["model"].get("max_seq_length", 128)
    print(f"\n[1/5] Loading tokenizer from '{model_name}'...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    train_path = cfg["data"]["train_path"]
    val_path = cfg["data"]["val_path"]

    print(f"\n[2/5] Loading Parquet datasets from '{train_path}'...")
    # Read Parquet using DuckDB for speed
    con_read = duckdb.connect()
    df_train = con_read.execute(f"SELECT * FROM '{train_path}'").df()
    df_val = con_read.execute(f"SELECT * FROM '{val_path}'").df()
    con_read.close()

    if max_train_samples and len(df_train) > max_train_samples:
        df_train = df_train.sample(n=max_train_samples, random_state=42).reset_index(drop=True)
        print(f" -> Subsampled Train set to {len(df_train):,} events (max_train_samples={max_train_samples})")

    if max_val_samples and len(df_val) > max_val_samples:
        df_val = df_val.sample(n=max_val_samples, random_state=42).reset_index(drop=True)
        print(f" -> Subsampled Val set to {len(df_val):,} events (max_val_samples={max_val_samples})")

    pre_tok = cfg["training"].get("pre_tokenize", True)
    train_dataset = FinancialSentimentDataset(
        df=df_train,
        tokenizer=tokenizer,
        max_seq_length=max_seq_len,
        text_column=cfg["data"].get("text_column", "context_text"),
        label_column=cfg["data"].get("label_column", "sentiment_label"),
        chosen_column=cfg["data"].get("findpo_chosen_column", "findpo_chosen"),
        rejected_column=cfg["data"].get("findpo_rejected_column", "findpo_rejected"),
        pre_tokenize=pre_tok,
    )
    val_dataset = FinancialSentimentDataset(
        df=df_val,
        tokenizer=tokenizer,
        max_seq_length=max_seq_len,
        text_column=cfg["data"].get("text_column", "context_text"),
        label_column=cfg["data"].get("label_column", "sentiment_label"),
        chosen_column=cfg["data"].get("findpo_chosen_column", "findpo_chosen"),
        rejected_column=cfg["data"].get("findpo_rejected_column", "findpo_rejected"),
        pre_tokenize=pre_tok,
    )

    batch_size = cfg["training"].get("per_device_train_batch_size", 16)
    eval_batch_size = cfg["training"].get("per_device_eval_batch_size", 32)
    grad_accum_steps = cfg["training"].get("gradient_accumulation_steps", 2)

    pin_mem = device.type == "cuda"
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=pin_mem,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=eval_batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=pin_mem,
    )

    print(f" -> Prepared Train DataLoader: {len(train_dataset):,} samples, {len(train_loader)} batches (batch_size={batch_size})")
    print(f" -> Prepared Val DataLoader  : {len(val_dataset):,} samples, {len(val_loader)} batches")

    # 3. Model Initialization & Class Weights
    print("\n[3/5] Initializing PhoBertFinDPO dual-head architecture...")
    class_weights: Optional[torch.Tensor] = None
    if cfg["training"].get("use_class_weights", True):
        import numpy as np
        labels = df_train[cfg["data"].get("label_column", "sentiment_label")].to_numpy()
        counts = np.bincount(labels, minlength=3)
        total = len(labels)
        weights = np.sqrt(total / (3.0 * np.maximum(counts, 1)))
        weights = weights / weights.mean()
        class_weights = torch.tensor(weights, dtype=torch.float32, device=device)
        print(f" -> Balanced Class Weights (Neg/Neu/Pos): {weights.round(3).tolist()}")

    model = PhoBertFinDPO(
        model_name=model_name,
        num_labels=cfg["model"].get("num_labels", 3),
        dropout_prob=cfg["model"].get("dropout_prob", 0.15),
        beta=cfg["findpo"].get("beta", 0.1),
        preference_weight=cfg["findpo"].get("preference_weight", 0.4),
        class_weights=class_weights,
    )
    model.to(device)

    # 4. Optimization & Mixed Precision
    num_epochs = epochs_override or cfg["training"].get("num_train_epochs", 3)
    lr = float(cfg["training"].get("learning_rate", 2.0e-5))
    weight_decay = float(cfg["training"].get("weight_decay", 0.01))

    total_steps = (len(train_loader) // grad_accum_steps) * num_epochs
    warmup_steps = int(total_steps * cfg["training"].get("warmup_ratio", 0.1))

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

    use_fp16 = cfg["training"].get("fp16", True) and (device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_fp16) if device.type == "cuda" else torch.amp.GradScaler("cpu", enabled=False)

    output_dir = pathlib.Path(cfg["training"].get("output_dir", "out/models/phobert_base_findpo"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup Checkpointing & Interrupt Handlers
    saver = AtomicCheckpointSaver(output_dir)
    interrupt_handler = GracefulInterruptHandler()

    start_epoch = 1
    global_step = 0
    best_f1 = -1.0
    training_history: List[Dict[str, Any]] = []

    # Handle Checkpoint Resuming
    target_resume = resume_path or (str(output_dir / "last_checkpoint.pt") if resume else None)
    if target_resume and pathlib.Path(target_resume).exists():
        start_epoch, global_step, best_f1, training_history = load_resumable_checkpoint(
            checkpoint_path=target_resume,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            device=device,
        )
        print(f" -> Resuming training from Epoch {start_epoch} (Global step: {global_step}, Best F1: {best_f1:.4f})")
    elif resume:
        print(f" -> [NOTICE] Resume requested but no existing checkpoint found at '{target_resume}'. Starting fresh.")

    print(f"\n[4/5] Starting Training: Epochs {start_epoch}->{num_epochs} | Total Steps: {total_steps} | FP16: {use_fp16}")

    eval_steps = cfg["training"].get("eval_steps", 250)
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
                    best_metric=best_f1,
                    training_history=training_history,
                    reason="Early user interrupt before epoch start",
                )
                break

            model.train()
            running_loss = 0.0
            running_ce = 0.0
            running_dpo = 0.0
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
                        best_metric=best_f1,
                        training_history=training_history,
                        reason=f"User interrupt at Epoch {epoch}, Step {step}",
                    )
                    break

                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels = batch["labels"].to(device)

                chosen_ids = batch["chosen_input_ids"].to(device)
                chosen_mask = batch["chosen_attention_mask"].to(device)
                rejected_ids = batch["rejected_input_ids"].to(device)
                rejected_mask = batch["rejected_attention_mask"].to(device)

                with torch.amp.autocast(device_type=device.type, enabled=use_fp16):
                    outputs = model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        labels=labels,
                        chosen_input_ids=chosen_ids,
                        chosen_attention_mask=chosen_mask,
                        rejected_input_ids=rejected_ids,
                        rejected_attention_mask=rejected_mask,
                    )
                    loss = outputs.loss / grad_accum_steps

                scaler.scale(loss).backward()

                running_loss += outputs.loss.item()
                if outputs.loss_ce is not None:
                    running_ce += outputs.loss_ce.item()
                if outputs.loss_dpo is not None:
                    running_dpo += outputs.loss_dpo.item()

                if step % grad_accum_steps == 0 or step == len(train_loader):
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad()
                    scheduler.step()
                    global_step += 1

                    # Progress reporting every 50 global steps
                    if global_step % 50 == 0:
                        current_lr = scheduler.get_last_lr()[0]
                        vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024) if device.type == "cuda" else 0.0
                        print(
                            f"  [Epoch {epoch}/{num_epochs}] Step {global_step}/{total_steps} | "
                            f"Loss: {running_loss / step:.4f} (CE: {running_ce / step:.4f}, DPO: {running_dpo / step:.4f}) | "
                            f"LR: {current_lr:.2e} | VRAM: {vram_mb:.0f} MB"
                        )

                # Evaluation check
                if global_step > 0 and global_step % eval_steps == 0:
                    print(f"\n--- [Evaluation at Step {global_step}] ---")
                    val_metrics = evaluate_dataset(model, val_loader, device)
                    f1_macro = val_metrics["f1_macro"]
                    pref_acc = val_metrics["findpo_preference_accuracy"]
                    print(
                        f"  Val Loss: {val_metrics['loss']:.4f} | Val F1 Macro: {f1_macro:.4f} | "
                        f"Val Acc: {val_metrics['accuracy']:.4f} | FinDPO Win Rate: {pref_acc * 100:.2f}%"
                    )

                    if f1_macro > best_f1:
                        best_f1 = f1_macro
                        saver.save_best_model(model, epoch, best_f1, metric_name="val_f1_macro")
                        print(f"  >>> [NEW BEST MODEL] Saved atomic checkpoint best_model.pt (F1 Macro: {best_f1:.4f})")

                    model.train()

            if interrupt_handler.interrupted:
                break

            # Epoch end cleanup & evaluation
            epoch_time = time.time() - epoch_start
            print(f"\n=== Completed Epoch {epoch}/{num_epochs} in {epoch_time:.2f}s ===")
            val_metrics = evaluate_dataset(model, val_loader, device)
            f1_macro = val_metrics["f1_macro"]
            pref_acc = val_metrics["findpo_preference_accuracy"]

            vram_peak_gb = (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0
            print(
                f"End of Epoch {epoch} Evaluation | Val F1: {f1_macro:.4f} | "
                f"FinDPO Preference: {pref_acc * 100:.2f}% | Peak VRAM: {vram_peak_gb:.2f} GB"
            )

            if f1_macro > best_f1:
                best_f1 = f1_macro
                saver.save_best_model(model, epoch, best_f1, metric_name="val_f1_macro")
                print("  >>> [NEW BEST MODEL] Saved atomic checkpoint best_model.pt")

            training_history.append({
                "epoch": epoch,
                "train_loss": running_loss / max(len(train_loader), 1),
                "val_loss": val_metrics["loss"],
                "val_f1_macro": f1_macro,
                "val_f1_weighted": val_metrics["f1_weighted"],
                "val_accuracy": val_metrics["accuracy"],
                "val_findpo_accuracy": pref_acc,
                "peak_vram_gb": vram_peak_gb,
                "epoch_duration_sec": epoch_time,
            })

            # Save atomic resumable checkpoint at epoch boundary
            saver.save_checkpoint(
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                epoch=epoch + 1,
                global_step=global_step,
                best_metric=best_f1,
                training_history=training_history,
                config=cfg,
                filename="last_checkpoint.pt",
            )
            print(f"  -> Preserved atomic resumable checkpoint to last_checkpoint.pt (Ready for resume at Epoch {epoch + 1})")

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
            best_metric=best_f1,
            training_history=training_history,
            reason=f"Crash exception: {err}",
        )
        interrupt_handler.close()
        raise
    finally:
        interrupt_handler.close()

    # 5. Save Final Report & Summary
    print("\n[5/5] Saving final training summary...")
    summary_report = {
        "model_name": model_name,
        "trained_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_duration_sec": time.time() - start_time,
        "best_val_f1_macro": best_f1,
        "peak_vram_gb": (torch.cuda.max_memory_allocated() / 1e9) if device.type == "cuda" else 0.0,
        "vram_budget_safe": (torch.cuda.max_memory_allocated() / 1e9 <= max_vram_gb) if device.type == "cuda" else True,
        "history": training_history,
    }

    report_path = output_dir / "training_metrics.json"
    report_path.write_text(json.dumps(summary_report, indent=2), encoding="utf-8")
    print(f" -> Wrote training metrics to {report_path.resolve()}")

    return summary_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PhoBERT-base with FinDPO market alignment")
    parser.add_argument("--config", default="configs/phobert_base.yaml", help="Path to config file")
    parser.add_argument("--max-train-samples", type=int, default=None, help="Cap training samples (e.g. 5000 for quick test)")
    parser.add_argument("--max-val-samples", type=int, default=None, help="Cap validation samples")
    parser.add_argument("--epochs", type=int, default=None, help="Override number of epochs")
    parser.add_argument("--resume", action="store_true", help="Resume from last_checkpoint.pt if available")
    parser.add_argument("--resume-path", default=None, help="Explicit path to checkpoint file to resume from")
    args = parser.parse_args()

    train_phobert_findpo(
        config_path=args.config,
        max_train_samples=args.max_train_samples,
        max_val_samples=args.max_val_samples,
        epochs_override=args.epochs,
        resume=args.resume,
        resume_path=args.resume_path,
    )
