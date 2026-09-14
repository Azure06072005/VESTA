"""src/pipeline/export_f104_dataset.py

F104 Official Dataset Exporter:
Transforms preprocessed quantitative events into official Train/Validation/Test partitions
for PhoBERT-base Fine-Tuning (F301) and Multimodal Cross-Attention Fusion (F302).

Key Invariants:
1. Anti-Leakage Temporal Splitting: Uses strict chronological boundaries with a 45-day
   Purged & Embargo Window to eliminate forward-looking label overlap (T+30).
2. Dual-Target Formulation:
   - Supervised Sentiment Classification: 3 classes (0: Negative, 1: Neutral, 2: Positive).
   - FinDPO Preference Alignment: (prompt, chosen, rejected) pairs conditioned on F203
     market regime dynamics (Contrarian reversal vs Trend continuation).
3. Rich Context Enrichment: Generates context-aware text strings:
   "[SYMBOL | EXCHANGE | REGIME] HEADLINE"
4. Data Provenance: Exports dataset_manifest.json with SHA-256 hashes and class breakdowns.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time

import duckdb
import numpy as np
import pandas as pd

# Configure UTF-8 for console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def resolve_source_db(preferred_path: str = "") -> str:
    """Finds the active preprocessed DuckDB database."""
    candidates = [
        preferred_path,
        "test_pipeline/db/vesta_preprocessed_quant.duckdb",
        "db/vesta.duckdb",
        "test_pipeline/db/vesta_preprocessed.duckdb",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError(f"Could not find a valid preprocessed database among: {candidates}")


def compute_file_sha256(file_path: str | pathlib.Path) -> str:
    """Computes SHA-256 checksum of a file for data provenance."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def assign_sentiment_label(score: float | None, threshold: float = 0.15) -> int:
    """Maps continuous sentiment score into 3 discrete classes:
    0: Negative (score < -threshold)
    1: Neutral  (-threshold <= score <= threshold)
    2: Positive (score > threshold)
    """
    if score is None or np.isnan(score):
        return 1
    if score < -threshold:
        return 0
    if score > threshold:
        return 2
    return 1


def generate_findpo_pair(
    sentiment_label: int,
    regime: str,
    diff_pct: float | None,
) -> tuple[str, str]:
    """Generates FinDPO preference pair (chosen_action, rejected_action)
    conditioned on empirical regime reaction dynamics (F203 findings).

    When sentiment is Negative (label 0):
      - In Bull / Sideways regimes: Dip-buying reversion is historically rewarded (rebound diff > 0).
        -> Chosen: Accumulate on oversold panic.
        -> Rejected: Panic sell at bottom.
      - In Bear / Crisis regimes: Negative momentum accelerates downwards (rebound diff <= 0).
        -> Chosen: Enforce risk circuit breaker / avoid dip-buying.
        -> Rejected: Premature bottom-fishing.
    """
    diff_val = diff_pct if (diff_pct is not None and not np.isnan(diff_pct)) else 0.0

    if sentiment_label == 0:  # Negative Event
        if regime in ["BULL", "SIDEWAYS"]:
            if diff_val > 0:
                return (
                    "OVERSOLD_REVERSAL_CONFIRMED: Accumulate position on capitulation dip",
                    "PANIC_SELL: Liquidate position at the trough of temporary overreaction",
                )
            else:
                return (
                    "TREND_CONTINUATION: Await technical confirmation before entering",
                    "UNCONDITIONAL_BUY: Blindly buy the falling knife without volume support",
                )
        else:  # BEAR or CRISIS_HIGH_VOL
            if diff_val <= 0:
                return (
                    "BEAR_ACCELERATION_CONFIRMED: Halt buying and enforce strict stop-loss",
                    "PREMATURE_BOTTOM_FISHING: Speculate on dip-buying during liquidity contraction",
                )
            else:
                return (
                    "SELECTIVE_RELIEF_BOUNCE: Exploit technical bounce with tight trailing stop",
                    "UNCONDITIONAL_SHORT: Aggressively short sell into historical capitulation volume",
                )
    elif sentiment_label == 2:  # Positive Event
        if regime in ["BEAR", "CRISIS_HIGH_VOL"]:
            return (
                "SKEPTICAL_FADE: Take profit into relief rally during macro downturn",
                "CHASE_MOMENTUM: Buy breakout at resistance during bear regime",
            )
        else:
            return (
                "BULL_MOMENTUM_EXPANSION: Ride upward momentum with institutional flow",
                "CONTRARIAN_FADE: Prematurely short a strong growth catalyst in bull market",
            )
    else:  # Neutral Event
        return (
            "HOLD_OBSERVE: Maintain current position weight and monitor order book",
            "OVERREACT_CHURN: Execute unnecessary portfolio turnover on uninformative news",
        )


def export_f104_partitions(
    db_path: str = "",
    out_dir: str = "data/processed/f104",
    train_end_str: str = "2023-12-31",
    val_end_str: str = "2024-12-31",
    embargo_days: int = 45,
    max_rows: int | None = None,
) -> dict[str, object]:
    start_time = time.time()
    resolved_db = resolve_source_db(db_path)
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    train_end = dt.datetime.strptime(train_end_str, "%Y-%m-%d").date()
    val_end = dt.datetime.strptime(val_end_str, "%Y-%m-%d").date()

    effective_train_end = train_end - dt.timedelta(days=embargo_days)
    effective_val_end = val_end - dt.timedelta(days=embargo_days)

    print("=" * 85)
    print(" F104: OFFICIAL ML FEATURE PIPELINE & DATASET PARTITIONING EXPORTER")
    print(f" Source Database   : {resolved_db}")
    print(f" Target Output Dir : {out_path.resolve()}")
    print(f" Train Window      : START -> {effective_train_end} (Purged {embargo_days}d before {train_end})")
    print(f" Embargo Gap 1     : {effective_train_end + dt.timedelta(days=1)} -> {train_end} [PURGED]")
    print(f" Validation Window : {train_end + dt.timedelta(days=1)} -> {effective_val_end}")
    print(f" Embargo Gap 2     : {effective_val_end + dt.timedelta(days=1)} -> {val_end} [PURGED]")
    print(f" Held-Out Test     : {val_end + dt.timedelta(days=1)} -> END")
    print("=" * 85)

    con = duckdb.connect(resolved_db, read_only=True)

    # Detect table name: either 'events' or 'preprocessed.events'
    tables = con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'events'"
    ).fetchall()
    if not tables:
        raise ValueError(f"Table 'events' not found in database: {resolved_db}")
    schema_name = tables[0][0]
    table_ref = f"{schema_name}.events" if schema_name != "main" else "events"

    limit_sql = f"LIMIT {int(max_rows)}" if max_rows else ""

    print(f"\n[1/5] Loading records from '{table_ref}'...")
    query = f"""
    SELECT 
        symbol,
        exchange,
        event_date,
        published_at,
        is_midnight_ts,
        headline_clean,
        is_duplicate,
        entity_tag,
        sentiment_score,
        rankgauss_sentiment_z,
        p0,
        p5,
        p30,
        ret_t5_pct,
        ret_t30_pct,
        raw_diff_pct,
        winsorized_diff_pct,
        market_regime,
        vni_fracdiff_d020,
        rankgauss_volume_z,
        pe_ratio,
        pb_ratio,
        ps_ratio,
        p_cf_ratio,
        ev_ebitda,
        dividend_yield,
        market_cap,
        roe,
        roa,
        roic,
        gross_margin,
        net_margin,
        current_ratio,
        quick_ratio,
        debt_to_equity,
        financial_leverage,
        bank_nim,
        bank_cir,
        bank_ldr,
        bank_npl,
        bank_car,
        bank_casa
    FROM {table_ref}
    WHERE headline_clean IS NOT NULL AND length(trim(headline_clean)) > 5
    ORDER BY event_date ASC, published_at ASC
    {limit_sql}
    """
    df = con.execute(query).df()
    con.close()
    print(f"Loaded {len(df):,} total valid event records.")

    # -------------------------------------------------------------------------
    # [2/5] Feature Synthesis: Context text, Labels, FinDPO Pairs
    # -------------------------------------------------------------------------
    print("\n[2/5] Synthesizing context strings, 3-class labels & FinDPO pairs...")
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["exchange"] = df["exchange"].fillna("UNKNOWN").astype(str)
    df["market_regime"] = df["market_regime"].fillna("SIDEWAYS").astype(str)

    # 1. Clean headline & context-enriched prompt text
    df["text"] = df["headline_clean"].astype(str).str.strip()
    df["context_text"] = (
        "[" + df["symbol"] + " | " + df["exchange"] + " | " + df["market_regime"] + "] " + df["text"]
    )

    # 2. 3-class sentiment label
    df["sentiment_label"] = df["sentiment_score"].apply(assign_sentiment_label)

    # 3. FinDPO preference pair generation
    findpo_pairs = [
        generate_findpo_pair(label, regime, diff)
        for label, regime, diff in zip(
            df["sentiment_label"], df["market_regime"], df["winsorized_diff_pct"]
        )
    ]
    df["findpo_chosen"] = [p[0] for p in findpo_pairs]
    df["findpo_rejected"] = [p[1] for p in findpo_pairs]

    # 4. Target directional movement for t+5 and t+30
    df["target_dir_t5"] = np.where(df["ret_t5_pct"] > 0.5, 1, np.where(df["ret_t5_pct"] < -0.5, -1, 0))
    df["target_dir_t30"] = np.where(df["ret_t30_pct"] > 1.0, 1, np.where(df["ret_t30_pct"] < -1.0, -1, 0))

    # -------------------------------------------------------------------------
    # [3/5] Temporal Partitioning with Embargo Buffer
    # -------------------------------------------------------------------------
    print("\n[3/5] Partitioning into Train, Validation, and Test sets with Purged Embargo...")
    train_mask = df["event_date"] <= effective_train_end
    embargo1_mask = (df["event_date"] > effective_train_end) & (df["event_date"] <= train_end)
    val_mask = (df["event_date"] > train_end) & (df["event_date"] <= effective_val_end)
    embargo2_mask = (df["event_date"] > effective_val_end) & (df["event_date"] <= val_end)
    test_mask = df["event_date"] > val_end

    df_train = df[train_mask].reset_index(drop=True)
    df_val = df[val_mask].reset_index(drop=True)
    df_test = df[test_mask].reset_index(drop=True)

    purged_count = int(embargo1_mask.sum() + embargo2_mask.sum())
    print(f" -> Train Set      : {len(df_train):,} events ({df_train['event_date'].min()} to {df_train['event_date'].max()})")
    print(f" -> Purged Gap 1   : {int(embargo1_mask.sum()):,} events purged to prevent T+30 bleed into Val")
    print(f" -> Validation Set : {len(df_val):,} events ({df_val['event_date'].min()} to {df_val['event_date'].max()})")
    print(f" -> Purged Gap 2   : {int(embargo2_mask.sum()):,} events purged to prevent T+30 bleed into Test")
    print(f" -> Held-Out Test  : {len(df_test):,} events ({df_test['event_date'].min()} to {df_test['event_date'].max()})")
    print(f" -> Total Purged   : {purged_count:,} events ({purged_count / len(df) * 100:.2f}% of total)")

    # -------------------------------------------------------------------------
    # [4/5] Materialize Parquet Artifacts via DuckDB Native Engine
    # -------------------------------------------------------------------------
    print("\n[4/5] Writing compressed Parquet files (Snappy via DuckDB engine)...")
    train_file = out_path / "f104_train.parquet"
    val_file = out_path / "f104_val.parquet"
    test_file = out_path / "f104_test.parquet"

    con_export = duckdb.connect()
    con_export.register("_df_train", df_train)
    con_export.execute(f"COPY _df_train TO '{train_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'SNAPPY')")
    con_export.register("_df_val", df_val)
    con_export.execute(f"COPY _df_val TO '{val_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'SNAPPY')")
    con_export.register("_df_test", df_test)
    con_export.execute(f"COPY _df_test TO '{test_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'SNAPPY')")
    con_export.close()

    print(f" -> Wrote {train_file.name} ({os.path.getsize(train_file):,} bytes)")
    print(f" -> Wrote {val_file.name} ({os.path.getsize(val_file):,} bytes)")
    print(f" -> Wrote {test_file.name} ({os.path.getsize(test_file):,} bytes)")

    # -------------------------------------------------------------------------
    # [5/5] Manifest & Audit Provenance Generation
    # -------------------------------------------------------------------------
    print("\n[5/5] Generating dataset_manifest.json for Rule B4 Data Provenance...")
    
    def get_set_stats(subset_df: pd.DataFrame, file_path: pathlib.Path) -> dict[str, object]:
        regime_dist = subset_df["market_regime"].value_counts().to_dict()
        label_dist = subset_df["sentiment_label"].value_counts().to_dict()
        return {
            "file_name": file_path.name,
            "row_count": len(subset_df),
            "file_size_bytes": os.path.getsize(file_path),
            "sha256": compute_file_sha256(file_path),
            "min_event_date": str(subset_df["event_date"].min()) if not subset_df.empty else None,
            "max_event_date": str(subset_df["event_date"].max()) if not subset_df.empty else None,
            "sentiment_label_distribution": {
                "negative_0": int(label_dist.get(0, 0)),
                "neutral_1": int(label_dist.get(1, 0)),
                "positive_2": int(label_dist.get(2, 0)),
            },
            "market_regime_distribution": {k: int(v) for k, v in regime_dist.items()},
        }

    manifest = {
        "dataset_name": "VESTA_F104_OFFICIAL_SLM_DATASET",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_database": str(pathlib.Path(resolved_db).resolve()),
        "parameters": {
            "train_end": str(train_end),
            "val_end": str(val_end),
            "embargo_days": embargo_days,
            "effective_train_end": str(effective_train_end),
            "effective_val_end": str(effective_val_end),
        },
        "total_records_processed": len(df),
        "total_records_purged": purged_count,
        "partitions": {
            "train": get_set_stats(df_train, train_file),
            "validation": get_set_stats(df_val, val_file),
            "test": get_set_stats(df_test, test_file),
        },
        "columns_schema": {col: str(df[col].dtype) for col in df.columns},
    }

    manifest_file = out_path / "dataset_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f" -> Wrote {manifest_file.name} ({os.path.getsize(manifest_file):,} bytes)")

    elapsed = time.time() - start_time
    print("\n" + "=" * 85)
    print(f" F104 EXPORT COMPLETED SUCCESSFULLY IN {elapsed:.2f}s!")
    print(f" Total Partitioned: {len(df_train):,} Train | {len(df_val):,} Val | {len(df_test):,} Test")
    print(f" Output Location  : {out_path.resolve()}")
    print("=" * 85)

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export official F104 Train/Val/Test datasets")
    parser.add_argument("--db-path", default="", help="Path to DuckDB database")
    parser.add_argument("--out-dir", default="data/processed/f104", help="Output directory")
    parser.add_argument("--train-end", default="2023-12-31", help="Train cutoff date (YYYY-MM-DD)")
    parser.add_argument("--val-end", default="2024-12-31", help="Validation cutoff date (YYYY-MM-DD)")
    parser.add_argument("--embargo-days", type=int, default=45, help="Purged embargo window in days")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit total rows (for quick dry-run)")
    args = parser.parse_args()

    export_f104_partitions(
        db_path=args.db_path,
        out_dir=args.out_dir,
        train_end_str=args.train_end,
        val_end_str=args.val_end,
        embargo_days=args.embargo_days,
        max_rows=args.max_rows,
    )
