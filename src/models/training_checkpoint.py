"""src/models/training_checkpoint.py

Universal Crash-Resilient Checkpointing, Interrupt Handling, and Resumability
for VESTA Deep Learning Models (F301 PhoBERT, F302 Multimodal Fusion, etc.).

Features:
1. Signal Handling: Catches SIGINT (Ctrl+C) and SIGTERM (OS shutdown/task kill) gracefully.
2. Atomic Checkpointing: Writes to .tmp files before renaming with os.replace to prevent
   file corruption if power is abruptly lost mid-write.
3. Dual State Saving:
   - best_model.pt: Best model weights & metric metadata.
   - last_checkpoint.pt: Full training state (model, optimizer, scheduler, amp scaler,
     epoch, step, RNG states) for seamless training resumption.
   - emergency_checkpoint.pt: Automatically triggered on unhandled exceptions or interrupts.
4. Auto-Resume: Automatically restores all states to continue training from where it stopped.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import random
import signal
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch

logger = logging.getLogger("training_checkpoint")


class GracefulInterruptHandler:
    """Catches OS interrupt signals (SIGINT, SIGTERM) and sets an interrupted flag."""

    def __init__(self) -> None:
        self.interrupted = False
        self.signal_received: Optional[int] = None
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            # In some multi-threaded or sub-process environments, signal handler cannot be set
            pass

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self.interrupted = True
        self.signal_received = signum
        sig_name = "SIGINT (Ctrl+C)" if signum == signal.SIGINT else f"SIGTERM ({signum})"
        print(f"\n[INTERRUPT DETECTED] Received {sig_name}. Initiating graceful checkpointing & clean shutdown...")

    def reset(self) -> None:
        self.interrupted = False
        self.signal_received = None

    def close(self) -> None:
        """Restore original signal handlers."""
        try:
            signal.signal(signal.SIGINT, self._original_sigint)
            signal.signal(signal.SIGTERM, self._original_sigterm)
        except (ValueError, AttributeError):
            pass


class AtomicCheckpointSaver:
    """Safely saves training checkpoints using atomic filesystem operations."""

    def __init__(self, output_dir: str | pathlib.Path) -> None:
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_torch_save(self, state_dict: Dict[str, Any], target_path: pathlib.Path) -> None:
        """Writes to a temporary file first, then atomically replaces target."""
        tmp_path = target_path.with_suffix(".tmp")
        try:
            torch.save(state_dict, tmp_path)
            # os.replace is atomic across POSIX and modern Windows NTFS
            os.replace(tmp_path, target_path)
        except Exception as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise IOError(f"Failed atomic checkpoint write to {target_path}: {e}") from e

    def get_rng_states(self) -> Dict[str, Any]:
        """Captures complete random number generator states across libraries."""
        rng: Dict[str, Any] = {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch": torch.get_rng_state(),
        }
        if torch.cuda.is_available():
            rng["torch_cuda"] = torch.cuda.get_rng_state_all()
        return rng

    def set_rng_states(self, rng_dict: Dict[str, Any]) -> None:
        """Restores random number generator states."""
        if "python" in rng_dict:
            random.setstate(rng_dict["python"])
        if "numpy" in rng_dict:
            np.random.set_state(rng_dict["numpy"])
        if "torch" in rng_dict:
            torch.set_rng_state(rng_dict["torch"])
        if "torch_cuda" in rng_dict and torch.cuda.is_available():
            try:
                torch.cuda.set_rng_state_all(rng_dict["torch_cuda"])
            except Exception:
                pass

    def save_checkpoint(
        self,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: Optional[Any],
        scaler: Optional[Any],
        epoch: int,
        global_step: int,
        best_metric: float,
        training_history: list[dict[str, Any]],
        config: Optional[dict[str, Any]] = None,
        filename: str = "last_checkpoint.pt",
        extra_meta: Optional[dict[str, Any]] = None,
    ) -> pathlib.Path:
        """Saves a complete resumable state dictionary."""
        checkpoint_data: Dict[str, Any] = {
            "epoch": epoch,
            "global_step": global_step,
            "best_metric": best_metric,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler is not None else None,
            "scaler_state_dict": scaler.state_dict() if scaler is not None else None,
            "training_history": training_history,
            "rng_states": self.get_rng_states(),
            "saved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "config": config,
            "extra_meta": extra_meta or {},
        }
        target_path = self.output_dir / filename
        self._atomic_torch_save(checkpoint_data, target_path)
        return target_path

    def save_best_model(
        self,
        model: torch.nn.Module,
        epoch: int,
        metric_value: float,
        metric_name: str = "val_f1_macro",
        filename: str = "best_model.pt",
    ) -> pathlib.Path:
        """Saves clean model weights with minimal overhead for deployment/inference."""
        target_path = self.output_dir / filename
        # We save state_dict directly for standard HuggingFace/PyTorch inference compatibility
        self._atomic_torch_save(model.state_dict(), target_path)

        # Also write small JSON sidecar metadata
        meta_path = self.output_dir / "best_model_meta.json"
        meta_content = {
            "saved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "epoch": epoch,
            "metric_name": metric_name,
            "metric_value": metric_value,
        }
        meta_path.write_text(json.dumps(meta_content, indent=2), encoding="utf-8")
        return target_path

    def save_emergency_checkpoint(
        self,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: Optional[Any],
        scaler: Optional[Any],
        epoch: int,
        global_step: int,
        best_metric: float,
        training_history: list[dict[str, Any]],
        reason: str = "interrupt_or_crash",
    ) -> pathlib.Path:
        """Saves emergency checkpoint when an interrupt or unhandled exception occurs."""
        print(f" -> [EMERGENCY BACKUP] Saving emergency checkpoint (Reason: {reason})...")
        path = self.save_checkpoint(
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            epoch=epoch,
            global_step=global_step,
            best_metric=best_metric,
            training_history=training_history,
            filename="emergency_checkpoint.pt",
            extra_meta={"emergency_reason": reason},
        )
        print(f" -> Successfully preserved emergency state to {path.resolve()}")
        return path


def load_resumable_checkpoint(
    checkpoint_path: str | pathlib.Path,
    model: torch.nn.Module,
    optimizer: Optional[torch.optim.Optimizer] = None,
    scheduler: Optional[Any] = None,
    scaler: Optional[Any] = None,
    device: Optional[torch.device] = None,
) -> Tuple[int, int, float, list[dict[str, Any]]]:
    """Loads state from a resumable checkpoint.

    Returns:
        (start_epoch, global_step, best_metric, training_history)
    """
    ckpt_file = pathlib.Path(checkpoint_path)
    if not ckpt_file.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {ckpt_file}")

    map_location = device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f" -> Loading resumable checkpoint from {ckpt_file.resolve()} (map_location={map_location})...")
    try:
        ckpt = torch.load(ckpt_file, map_location=map_location, weights_only=False)
    except TypeError:
        ckpt = torch.load(ckpt_file, map_location=map_location)

    # 1. Restore Model weights
    if "model_state_dict" in ckpt:
        model.load_state_dict(ckpt["model_state_dict"])
    else:
        # Backward compatibility if it was saved as raw state_dict
        model.load_state_dict(ckpt)

    # 2. Restore Optimizer state
    if optimizer is not None and ckpt.get("optimizer_state_dict") is not None:
        try:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        except Exception as e:
            print(f" [WARNING] Could not restore optimizer state: {e}")

    # 3. Restore Scheduler state
    if scheduler is not None and ckpt.get("scheduler_state_dict") is not None:
        try:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        except Exception as e:
            print(f" [WARNING] Could not restore scheduler state: {e}")

    # 4. Restore GradScaler state
    if scaler is not None and ckpt.get("scaler_state_dict") is not None:
        try:
            scaler.load_state_dict(ckpt["scaler_state_dict"])
        except Exception as e:
            print(f" [WARNING] Could not restore scaler state: {e}")

    start_epoch = ckpt.get("epoch", 1)
    global_step = ckpt.get("global_step", 0)
    best_metric = ckpt.get("best_metric", -1.0)
    history = ckpt.get("training_history", [])

    print(f" -> Checkpoint loaded successfully: Resuming from Epoch {start_epoch}, Step {global_step} (Best Metric: {best_metric:.4f})")
    return start_epoch, global_step, best_metric, history
