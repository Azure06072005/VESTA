"""src/models/train_priority_tables_curriculum.py

Curriculum Training Pipeline for Untrained Priority Tables (1st -> 4th):
1st: core.market_foreign_flow_daily (Dòng tiền Khối ngoại)
2nd: core.corporate_events (Sự kiện Doanh nghiệp, Cổ tức & Payout Delay)
3rd: core.market_breadth_series (Độ rộng thị trường MHI)
4th: core.company_shareholders (Cơ cấu Cổ đông Lớn & Ban Lãnh đạo)

Enriches F104 dataset via DuckDB ASOF joins without look-ahead bias,
normalizes tabular features, precomputes frozen PhoBERT [CLS] embeddings,
and sequentially trains the Multimodal Cross-Attention Fusion architecture
across all 4 stages.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import pathlib
import sys
import time
from typing import Any, Dict, List, Tuple

import duckdb
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.multimodal_fusion import (
    DEFAULT_FUNDAMENTAL_FEATURES,
    REGIME_TO_ID,
    MultimodalCrossAttentionFusion,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("priority_curriculum_trainer")

DB_SNAPSHOT_PATH = str(REPO_ROOT / "db" / "vesta_snapshot.duckdb")
TRAIN_PARQUET_PATH = str(REPO_ROOT / "data" / "processed" / "f104" / "f104_train.parquet")
VAL_PARQUET_PATH = str(REPO_ROOT / "data" / "processed" / "f104" / "f104_val.parquet")
OUT_DIR = REPO_ROOT / "out" / "models" / "multimodal_fusion"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def enrich_dataset_with_4_tables(
    source_df: pd.DataFrame,
    db_path: str = DB_SNAPSHOT_PATH,
) -> pd.DataFrame:
    """Enriches event DataFrame with trailing data from the 4 priority tables via DuckDB ASOF join."""
    logger.info(f"Connecting to {db_path} to enrich {len(source_df):,} events...")
    con = duckdb.connect(db_path, read_only=True)
    con.register("df_src", source_df)

    query = """
    WITH foreign_flow_summary AS (
        SELECT 
            symbol,
            date,
            net_value,
            SUM(net_value) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as foreign_net_val_5d,
            SUM(net_value) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as foreign_net_val_20d,
            foreign_room
        FROM core.market_foreign_flow_daily
    ),
    corp_events_summary AS (
        SELECT 
            symbol,
            event_date,
            COALESCE(payout_delay_days, 0) as payout_delay_days
        FROM core.corporate_events
    ),
    breadth_summary AS (
        SELECT 
            exchange,
            trade_date,
            above_ma20_pct,
            above_ma50_pct
        FROM core.market_breadth_series
    ),
    shareholder_summary AS (
        SELECT 
            symbol,
            SUM(ownership_percentage) as major_ownership_pct,
            COUNT(*) as num_major_shareholders
        FROM core.company_shareholders
        GROUP BY symbol
    )
    SELECT 
        src.*,
        -- 1st Priority: Foreign Flow
        COALESCE(f.foreign_net_val_5d, 0.0) as foreign_net_val_5d,
        COALESCE(f.foreign_net_val_20d, 0.0) as foreign_net_val_20d,
        COALESCE(f.foreign_room, 0.0) as foreign_room,
        -- 2nd Priority: Corporate Events
        COALESCE(e.payout_delay_days, 0) as payout_delay_days,
        -- 3rd Priority: Market Breadth
        COALESCE(b.above_ma20_pct, 0.5) as breadth_above_ma20_pct,
        COALESCE(b.above_ma50_pct, 0.5) as breadth_above_ma50_pct,
        -- 4th Priority: Shareholders
        COALESCE(s.major_ownership_pct, 0.0) as major_ownership_pct,
        COALESCE(s.num_major_shareholders, 0) as num_major_shareholders
    FROM df_src src
    ASOF LEFT JOIN foreign_flow_summary f
        ON src.symbol = f.symbol AND src.event_date >= f.date
    ASOF LEFT JOIN corp_events_summary e
        ON src.symbol = e.symbol AND src.event_date >= e.event_date
    ASOF LEFT JOIN breadth_summary b
        ON src.exchange = b.exchange AND src.event_date >= b.trade_date
    LEFT JOIN shareholder_summary s
        ON src.symbol = s.symbol
    """
    enriched_df = con.execute(query).df()
    con.close()

    # Normalize new features using robust scaling / tanh
    logger.info("Normalizing newly added priority features...")
    # 1. Foreign flow values in Billions VND
    for col in ["foreign_net_val_5d", "foreign_net_val_20d"]:
        enriched_df[col] = np.tanh(enriched_df[col] / 1e10)
    enriched_df["foreign_room"] = np.clip(enriched_df["foreign_room"] / 1e7, -5.0, 5.0)

    # 2. Payout delay
    enriched_df["payout_delay_days"] = np.clip(enriched_df["payout_delay_days"] / 30.0, 0.0, 5.0)

    # 3. Breadth
    enriched_df["breadth_above_ma20_pct"] = (enriched_df["breadth_above_ma20_pct"] - 0.5) * 4.0
    enriched_df["breadth_above_ma50_pct"] = (enriched_df["breadth_above_ma50_pct"] - 0.5) * 4.0

    # 4. Shareholders
    enriched_df["major_ownership_pct"] = (enriched_df["major_ownership_pct"] / 100.0 - 0.5) * 4.0
    enriched_df["num_major_shareholders"] = np.clip(enriched_df["num_major_shareholders"] / 5.0, 0.0, 5.0)

    logger.info(f"Enrichment complete. Total columns: {len(enriched_df.columns)}.")
    return enriched_df


def precompute_text_cls_embeddings(
    texts: List[str],
    tokenizer: Any,
    phobert_model_name: str = "vinai/phobert-base-v2",
    batch_size: int = 128,
    max_seq_length: int = 128,
    device: torch.device | None = None,
) -> torch.Tensor:
    """Precomputes [CLS] text representations once using frozen PhoBERT backbone."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    logger.info(f"Precomputing PhoBERT text embeddings for {len(texts):,} samples on {device}...")
    encoder = AutoModel.from_pretrained(phobert_model_name, local_files_only=True)
    encoder.to(device)
    encoder.eval()

    all_cls = []
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            enc = tokenizer(
                batch_texts,
                max_length=max_seq_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            input_ids = enc["input_ids"].to(device)
            attention_mask = enc["attention_mask"].to(device)
            out = encoder(input_ids=input_ids, attention_mask=attention_mask)
            cls_repr = out.last_hidden_state[:, 0, :].cpu()  # [B, 768]
            all_cls.append(cls_repr)

    all_tensor = torch.cat(all_cls, dim=0)
    duration = time.time() - t0
    logger.info(f"Precomputed {len(all_tensor):,} text embeddings in {duration:.2f}s ({len(all_tensor)/max(duration, 0.001):.0f} texts/s)")
    return all_tensor


class CachedMultimodalDataset(Dataset):
    """Fast Dataset loading precomputed text CLS embeddings and dynamic feature columns."""

    def __init__(
        self,
        df: pd.DataFrame,
        feature_columns: List[str],
        text_cls_embeddings: torch.Tensor,
    ) -> None:
        self.length = len(df)
        self.feature_columns = feature_columns
        self.text_cls = text_cls_embeddings

        # Tabular features tensor
        vals = df[feature_columns].copy().fillna(0.0).to_numpy(dtype=np.float32)
        self.fundamentals = torch.tensor(np.clip(vals, -5.0, 5.0), dtype=torch.float32)

        # Regime IDs
        regime_series = df["market_regime"].fillna("SIDEWAYS").astype(str)
        regime_ids = [REGIME_TO_ID.get(r, REGIME_TO_ID["SIDEWAYS"]) for r in regime_series]
        self.regime_ids = torch.tensor(regime_ids, dtype=torch.long)

        # Labels
        self.sentiment_labels = torch.tensor(df["sentiment_label"].fillna(1).astype(int).to_numpy(), dtype=torch.long)
        raw_dirs = df["target_dir_t5"].fillna(0).astype(int).to_numpy()
        self.direction_labels = torch.tensor(np.clip(raw_dirs + 1, 0, 2), dtype=torch.long)
        ret_vals = np.clip(df["ret_t5_pct"].fillna(0.0).astype(float).to_numpy(dtype=np.float32), -1.0, 1.0)
        self.return_targets = torch.tensor(ret_vals, dtype=torch.float32)

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        return {
            "text_cls": self.text_cls[idx],
            "fundamentals": self.fundamentals[idx],
            "regime_ids": self.regime_ids[idx],
            "sentiment_label": self.sentiment_labels[idx],
            "direction_label": self.direction_labels[idx],
            "return_target": self.return_targets[idx],
        }


def evaluate_stage(
    model: MultimodalCrossAttentionFusion,
    val_loader: DataLoader,
    device: torch.device,
) -> Dict[str, float]:
    """Evaluates multimodal performance on validation loader."""
    model.eval()
    total_loss = 0.0
    dir_correct = 0
    total_samples = 0

    with torch.no_grad():
        for batch in val_loader:
            text_cls = batch["text_cls"].to(device)
            fundamentals = batch["fundamentals"].to(device)
            regime_ids = batch["regime_ids"].to(device)
            sentiment_label = batch["sentiment_label"].to(device)
            direction_label = batch["direction_label"].to(device)
            return_target = batch["return_target"].to(device)

            out = model(
                text_cls=text_cls,
                fundamentals=fundamentals,
                regime_ids=regime_ids,
                sentiment_labels=sentiment_label,
                direction_labels=direction_label,
                return_targets=return_target,
            )
            total_loss += float(out.loss.item()) * len(text_cls)
            preds = torch.argmax(out.direction_logits, dim=-1)
            dir_correct += int((preds == direction_label).sum().item())
            total_samples += len(text_cls)

    acc = dir_correct / max(total_samples, 1)
    mean_loss = total_loss / max(total_samples, 1)
    return {
        "val_loss": round(mean_loss, 4),
        "val_direction_accuracy": round(acc, 4),
        "total_val_samples": total_samples,
    }


def train_single_stage(
    stage_name: str,
    feature_columns: List[str],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    train_text_cls: torch.Tensor,
    val_text_cls: torch.Tensor,
    epochs: int = 3,
    batch_size: int = 64,
    lr: float = 5e-4,
    device: torch.device | None = None,
) -> Tuple[MultimodalCrossAttentionFusion, Dict[str, Any]]:
    """Trains a single curriculum stage with specified feature subset."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    num_features = len(feature_columns)
    logger.info("=" * 80)
    logger.info(f"STARTING CURRICULUM STAGE: {stage_name}")
    logger.info(f"Number of Tabular Features: {num_features} (Base 24 + {num_features - 24} new)")
    logger.info(f"Device: {device} | Epochs: {epochs} | Batch Size: {batch_size}")
    logger.info("=" * 80)

    train_ds = CachedMultimodalDataset(train_df, feature_columns, train_text_cls)
    val_ds = CachedMultimodalDataset(val_df, feature_columns, val_text_cls)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    model = MultimodalCrossAttentionFusion(
        phobert_model_name="vinai/phobert-base-v2",
        phobert_checkpoint=None,
        freeze_phobert_layers=12,
        num_fundamental_features=num_features,
        hidden_dim=128,
        num_heads=4,
        num_fusion_layers=2,
        use_macro_gating=True,
    )
    # Freeze PhoBERT encoder completely
    for param in model.text_encoder.parameters():
        param.requires_grad = False

    model.to(device)

    trainable_params = [p for p in model.parameters() if p.requires_grad]
    logger.info(f"Trainable parameters in Fusion Head: {sum(p.numel() for p in trainable_params):,}")

    optimizer = AdamW(trainable_params, lr=lr, weight_decay=1e-4)

    eval_init = evaluate_stage(model, val_loader, device)
    logger.info(f"Initial Zero-Shot Val Direction Accuracy: {eval_init['val_direction_accuracy']:.4f}")

    stage_history = []
    t_start = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        n_train = 0

        for batch in train_loader:
            optimizer.zero_grad()
            text_cls = batch["text_cls"].to(device)
            fundamentals = batch["fundamentals"].to(device)
            regime_ids = batch["regime_ids"].to(device)
            sentiment_label = batch["sentiment_label"].to(device)
            direction_label = batch["direction_label"].to(device)
            return_target = batch["return_target"].to(device)

            out = model(
                text_cls=text_cls,
                fundamentals=fundamentals,
                regime_ids=regime_ids,
                sentiment_labels=sentiment_label,
                direction_labels=direction_label,
                return_targets=return_target,
            )
            loss = out.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable_params, 1.0)
            optimizer.step()

            train_loss += float(loss.item()) * len(text_cls)
            n_train += len(text_cls)

        epoch_loss = train_loss / max(n_train, 1)
        val_metrics = evaluate_stage(model, val_loader, device)
        logger.info(
            f"Epoch {epoch}/{epochs} | Train Loss: {epoch_loss:.4f} | "
            f"Val Loss: {val_metrics['val_loss']:.4f} | "
            f"Val Direction Acc: {val_metrics['val_direction_accuracy']:.4f}"
        )
        stage_history.append({
            "epoch": epoch,
            "train_loss": round(epoch_loss, 4),
            "val_loss": val_metrics["val_loss"],
            "val_direction_accuracy": val_metrics["val_direction_accuracy"],
        })

    duration = time.time() - t_start
    final_metrics = evaluate_stage(model, val_loader, device)
    final_metrics["duration_seconds"] = round(duration, 2)
    final_metrics["num_features"] = num_features
    final_metrics["feature_columns"] = feature_columns
    final_metrics["history"] = stage_history

    return model, final_metrics


def run_full_curriculum(
    train_sample_limit: int = 15000,
    val_sample_limit: int = 3000,
) -> Dict[str, Any]:
    """Runs the 4-stage sequential curriculum training."""
    logger.info("=" * 80)
    logger.info(" VESTA MULTIMODAL CURRICULUM TRAINING: PRIORITY TABLES 1st -> 4th")
    logger.info("=" * 80)

    # 1. Load source datasets
    logger.info(f"Loading train Parquet ({TRAIN_PARQUET_PATH})...")
    raw_train = pd.read_parquet(TRAIN_PARQUET_PATH).head(train_sample_limit)
    logger.info(f"Loading val Parquet ({VAL_PARQUET_PATH})...")
    raw_val = pd.read_parquet(VAL_PARQUET_PATH).head(val_sample_limit)

    # 2. Enrich datasets with all 4 tables
    enriched_train = enrich_dataset_with_4_tables(raw_train)
    enriched_val = enrich_dataset_with_4_tables(raw_val)

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2", local_files_only=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 3. Precompute text CLS representations ONCE
    train_texts = enriched_train["context_text"].astype(str).tolist()
    val_texts = enriched_val["context_text"].astype(str).tolist()

    train_cls = precompute_text_cls_embeddings(train_texts, tokenizer, device=device)
    val_cls = precompute_text_cls_embeddings(val_texts, tokenizer, device=device)

    # Define feature sets
    base_features = list(DEFAULT_FUNDAMENTAL_FEATURES)  # 24
    stage1_features = base_features + ["foreign_net_val_5d", "foreign_net_val_20d", "foreign_room"]  # 27
    stage2_features = stage1_features + ["payout_delay_days"]  # 28
    stage3_features = stage2_features + ["breadth_above_ma20_pct", "breadth_above_ma50_pct"]  # 30
    stage4_features = stage3_features + ["major_ownership_pct", "num_major_shareholders"]  # 32

    curriculum_stages = [
        ("Baseline_24_Features", base_features, "checkpoint_stage0_baseline.pt"),
        ("1st_Priority_Market_Foreign_Flow", stage1_features, "checkpoint_stage1_foreign_flow.pt"),
        ("2nd_Priority_Corporate_Events", stage2_features, "checkpoint_stage2_corporate_events.pt"),
        ("3rd_Priority_Market_Breadth_MHI", stage3_features, "checkpoint_stage3_market_breadth.pt"),
        ("4th_Priority_Company_Shareholders_Final", stage4_features, "checkpoint_stage4_shareholders_final.pt"),
    ]

    all_stage_reports = {}

    for stage_name, cols, ckpt_name in curriculum_stages:
        model, metrics = train_single_stage(
            stage_name=stage_name,
            feature_columns=cols,
            train_df=enriched_train,
            val_df=enriched_val,
            train_text_cls=train_cls,
            val_text_cls=val_cls,
            epochs=3,
            batch_size=64,
            lr=5e-4,
            device=device,
        )

        ckpt_path = OUT_DIR / ckpt_name
        torch.save(
            {
                "stage": stage_name,
                "model_state_dict": model.state_dict(),
                "feature_columns": cols,
                "num_fundamental_features": len(cols),
                "metrics": metrics,
                "saved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            ckpt_path,
        )
        logger.info(f"Saved {stage_name} checkpoint to {ckpt_path.name} ({ckpt_path.stat().st_size / 1e6:.1f} MB)")
        all_stage_reports[stage_name] = metrics

    # Save summary report
    report_path = OUT_DIR / "curriculum_training_report.json"
    summary_data = {
        "executed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "train_samples": len(enriched_train),
        "val_samples": len(enriched_val),
        "stages": all_stage_reports,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    logger.info("=" * 80)
    logger.info("CURRICULUM TRAINING COMPLETE ACROSS ALL 4 PRIORITY TABLES!")
    logger.info(f"Report written to: {report_path}")
    logger.info("=" * 80)
    return summary_data


if __name__ == "__main__":
    run_full_curriculum()
