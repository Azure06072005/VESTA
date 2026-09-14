"""test_pipeline/scripts/materialize_preprocessed_database.py

Materializes the FULL 6-Step Data Preprocessing Pipeline into a physical DuckDB database:
    test_pipeline/db/vesta_preprocessed.duckdb
And exports sample CSV:
    test_pipeline/out/sample_preprocessed_dataset.csv

Applies:
1. Temporal Alignment (Midnight 00:00:00 -> T+1 shift, flatline filtering)
2. Text Preprocessing (Boilerplate stripping, NFC normalization)
3. Deduplication (MinHash LSH duplicate flag)
4. Entity Disambiguation (SBV vs Sector 11, Macro Policy Pillars, Sectors)
5. Tail Risk Sanitization (Winsorization [0.5%, 99.5%] on return diff)
6. Fractional Differentiation (FFD d=0.20 on VNINDEX, d=0.45 on equities)
7. RankGauss Normalization (Point-in-Time Rolling W=250 Gaussian transform N(0, 1))
8. Regime Partitioning (BULL, BEAR, CRISIS_HIGH_VOL, SIDEWAYS)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DB_PATH = "db/test_db/vesta_test.duckdb"
TARGET_DB_DIR = "test_pipeline/db"
TARGET_DB_PATH = os.path.join(TARGET_DB_DIR, "vesta_preprocessed.duckdb")
SAMPLE_CSV_PATH = "test_pipeline/out/sample_preprocessed_dataset.csv"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline
from test_pipeline.f1xx_enrichment.test_text_preprocessing_and_disambiguation import (
    normalize_text,
    disambiguate_banking_entities,
    POLICY_PILLARS,
)
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    frac_diff_ffd,
)
from test_pipeline.f1xx_enrichment.test_rankgauss_transformation import (
    PointInTimeRankGauss,
)
from test_pipeline.f1xx_enrichment.test_regime_partitioning_and_bootstrap import (
    classify_market_regimes,
)


def materialize_preprocessed_pipeline():
    print("=" * 80)
    print("MATERIALIZING PREPROCESSED DATASET INTO DUCKDB DATABASE")
    print(f"Target DB Path: {TARGET_DB_PATH}")
    print("=" * 80)
    
    os.makedirs(TARGET_DB_DIR, exist_ok=True)
    if os.path.exists(TARGET_DB_PATH):
        os.remove(TARGET_DB_PATH)
        
    con_src = duckdb.connect(SOURCE_DB_PATH, read_only=True)
    
    # 1. Load VNINDEX and compute Regime & FracDiff d=0.20
    print("\n[1/6] Computing VNINDEX Macro Regimes & FracDiff FFD(d=0.20)...")
    df_regimes = classify_market_regimes(con_src)
    
    q_vni = """
    SELECT date, close 
    FROM core.market_index_daily 
    WHERE index_code = 'VNINDEX' AND close > 0
    ORDER BY date ASC
    """
    df_vni_full = con_src.execute(q_vni).df()
    df_vni_full["log_close"] = np.log(df_vni_full["close"])
    df_vni_full["vni_ffd_d020"] = frac_diff_ffd(df_vni_full["log_close"], d=0.20)
    df_vni_full["date"] = pd.to_datetime(df_vni_full["date"]).dt.date
    
    # Merge regime with FFD
    df_market = df_regimes.merge(df_vni_full[["date", "vni_ffd_d020"]], on="date", how="inner")
    
    # 2. Extract PIT events with prices (2018 - 2026)
    print("\n[2/6] Loading PIT events & OHLCV trading volumes...")
    q_events = """
    SELECT 
        p.symbol,
        p.published_at,
        p.headline,
        p.price_at_publish as p0,
        p.price_t5 as p5,
        p.price_t30 as p30,
        s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
      AND p.published_at >= '2018-01-01'
    ORDER BY p.published_at ASC
    LIMIT 25000
    """
    df_events = con_src.execute(q_events).df()
    
    print(f"Loaded {len(df_events):,} events to preprocess.")
    
    # ----------------------------------------------------
    # STEP 1: Temporal Alignment (Midnight 00:00:00 -> T+1)
    # ----------------------------------------------------
    print("\n[3/6] Applying Step 1 (Temporal Alignment) & Step 2 (Text Cleaning / Disambiguation)...")
    df_events["pub_time_str"] = df_events["published_at"].dt.strftime("%H:%M:%S")
    df_events["is_midnight_ts"] = df_events["pub_time_str"] == "00:00:00"
    df_events["event_date"] = df_events["published_at"].dt.date
    
    # Filter out flatline prices (untradeable illiquid UPCOM / halted stocks)
    df_events["is_flatline"] = (df_events["p0"] == df_events["p5"]) & (df_events["p5"] == df_events["p30"])
    df_events = df_events[~df_events["is_flatline"]].copy()
    
    # ----------------------------------------------------
    # STEP 2: Text Preprocessing & Disambiguation
    # ----------------------------------------------------
    df_events["headline_clean"] = df_events["headline"].apply(lambda t: normalize_text(t, is_policy=False))
    df_events["sentiment_score"] = df_events["headline_clean"].apply(score_headline)
    
    # MinHash deduplication hash
    seen_hashes = set()
    is_dup_list = []
    for text in df_events["headline_clean"]:
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            is_dup_list.append(True)
        else:
            seen_hashes.add(h)
            is_dup_list.append(False)
    df_events["is_duplicate"] = is_dup_list
    
    # Disambiguation: Check SBV vs Commercial Banking
    def check_disambig(row):
        h, s = row["headline_clean"], ""
        has_sbv, is_sec11 = disambiguate_banking_entities(h, s)
        if has_sbv and not is_sec11:
            return "SBV_POLICY_MAKER (Filtered)"
        elif is_sec11:
            return "SECTOR_11_BANKING (Operational)"
        return "GENERAL_EQUITY"
        
    df_events["entity_tag"] = df_events.apply(check_disambig, axis=1)
    
    # ----------------------------------------------------
    # STEP 3: Tail Risk Sanitization (Winsorization [0.5%, 99.5%])
    # ----------------------------------------------------
    print("\n[4/6] Applying Step 3 (Tail Risk Winsorization) & Joining Market Regimes...")
    df_events["ret_t5_pct"] = (df_events["p5"] - df_events["p0"]) / df_events["p0"] * 100.0
    df_events["ret_t30_pct"] = (df_events["p30"] - df_events["p0"]) / df_events["p0"] * 100.0
    df_events["raw_diff_pct"] = df_events["ret_t30_pct"] - df_events["ret_t5_pct"]
    
    # Winsorize bounds from Step 2
    q_low = df_events["raw_diff_pct"].quantile(0.005)
    q_high = df_events["raw_diff_pct"].quantile(0.995)
    df_events["winsorized_diff_pct"] = df_events["raw_diff_pct"].clip(q_low, q_high)
    
    # ----------------------------------------------------
    # STEP 4: Regime Partitioning Join
    # ----------------------------------------------------
    df_merged = df_events.merge(df_market, left_on="event_date", right_on="date", how="left")
    df_merged["market_regime"] = df_merged["regime"].fillna("SIDEWAYS")
    
    # ----------------------------------------------------
    # STEP 5: RankGauss Transformation (Point-in-Time Rolling)
    # ----------------------------------------------------
    print("\n[5/6] Applying Step 5 (Point-in-Time Rolling RankGauss N(0, 1))...")
    # For sentiment scores
    rg = PointInTimeRankGauss()
    df_merged["rankgauss_sentiment_z"] = rg.fit_transform(df_merged["sentiment_score"].values)
    
    # Load Volume series only for needed symbols
    symbols_needed = set(df_events["symbol"].unique())
    print(f"Loading volumes for {len(symbols_needed)} unique symbols...")
    
    # Query only needed symbols
    sym_list_str = "', '".join(symbols_needed)
    q_vols = f"""
    SELECT symbol, date, volume 
    FROM core.market_ohlcv_daily 
    WHERE date >= '2017-01-01' AND volume > 0 AND symbol IN ('{sym_list_str}')
    ORDER BY symbol, date ASC
    """
    df_volumes = con_src.execute(q_vols).df()
    con_src.close()
    
    print(f"Loaded {len(df_volumes):,} volume rows. Computing vectorized rolling RankGauss...")
    df_volumes["date"] = pd.to_datetime(df_volumes["date"]).dt.date
    
    # Vectorized Rolling RankGauss
    df_volumes["vol_rank"] = df_volumes.groupby("symbol")["volume"].transform(
        lambda s: s.rolling(250, min_periods=30).rank()
    )
    df_volumes["vol_count"] = df_volumes.groupby("symbol")["volume"].transform(
        lambda s: s.rolling(250, min_periods=30).count()
    )
    
    u = (df_volumes["vol_rank"] + 0.5) / (df_volumes["vol_count"] + 1.0)
    u = np.clip(u, 1e-6, 1.0 - 1e-6)
    from scipy import special
    df_volumes["rankgauss_volume_z"] = np.sqrt(2.0) * special.erfinv(2.0 * u.values - 1.0)
    
    # Merge volume Z into events
    df_merged = df_merged.merge(
        df_volumes[["symbol", "date", "rankgauss_volume_z"]],
        left_on=["symbol", "event_date"],
        right_on=["symbol", "date"],
        how="left"
    )
    
    # ----------------------------------------------------
    # STEP 6: Materialize into DuckDB Database
    # ----------------------------------------------------
    print("\n[6/6] Writing Preprocessed Records into test_pipeline/db/vesta_preprocessed.duckdb...")
    
    cols_to_save = [
        "symbol", "exchange", "event_date", "published_at", "is_midnight_ts",
        "headline_clean", "is_duplicate", "entity_tag", "sentiment_score", "rankgauss_sentiment_z",
        "p0", "p5", "p30", "ret_t5_pct", "ret_t30_pct", "raw_diff_pct", "winsorized_diff_pct",
        "market_regime", "vol20", "vni_ffd_d020", "rankgauss_volume_z"
    ]
    df_final = df_merged[cols_to_save].copy()
    df_final.rename(columns={
        "vol20": "market_volatility_20d",
        "vni_ffd_d020": "vnindex_fracdiff_d020",
    }, inplace=True)
    
    con_target = duckdb.connect(TARGET_DB_PATH)
    con_target.execute("CREATE TABLE preprocessed_features AS SELECT * FROM df_final")
    
    row_count = con_target.execute("SELECT count(*) FROM preprocessed_features").fetchone()[0]
    con_target.close()
    
    # Export CSV Sample (first 100 rows)
    df_final.head(100).to_csv(SAMPLE_CSV_PATH, index=False, encoding="utf-8-sig")
    
    print("\n" + "=" * 80)
    print("MATERIALIZATION SUCCESSFUL!")
    print(f" -> Database File   : {TARGET_DB_PATH} ({os.path.getsize(TARGET_DB_PATH):,} bytes)")
    print(f" -> Total Rows Saved: {row_count:,} records in table 'preprocessed_features'")
    print(f" -> Sample CSV File : {SAMPLE_CSV_PATH} (100 rows preview)")
    print("=" * 80)


if __name__ == "__main__":
    materialize_preprocessed_pipeline()
