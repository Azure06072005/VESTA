"""src/pipeline/build_full_preprocessed_database.py

Full-Scale Production Preprocessing Pipeline for VESTA.
Transforms the ENTIRE historical database:
1. preprocessed.market_regimes: 2000-2026 VNINDEX history (Regimes + FFD d=0.20).
2. preprocessed.macro_policy: 477,733 documents (Cleaned, Classified Pillars, Disambiguated, Deduplicated).
3. preprocessed.events: 658,182 PIT events (T+1 Midnight shift, Flatline filter, Winsorized [0.5%, 99.5%],
   Rolling RankGauss N(0, 1), Regime tagging).

Writes to both:
- db/vesta.duckdb (Schema 'preprocessed')
- db/vesta_preprocessed_full.duckdb (Standalone production database)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd
from scipy import special

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta.duckdb"
STANDALONE_DB_PATH = "db/vesta_preprocessed_full.duckdb"

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


def run_full_database_preprocessing():
    start_time = time.time()
    print("=" * 85)
    print("FULL-SCALE PRODUCTION DATA PREPROCESSING PIPELINE — VESTA")
    print(f"Target 1: {CANONICAL_DB_PATH} (Schema 'preprocessed')")
    print(f"Target 2: {STANDALONE_DB_PATH} (Standalone Database)")
    print("=" * 85)

    con = duckdb.connect(CANONICAL_DB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS preprocessed;")

    # =========================================================================
    # PART 1: PREPROCESSED MARKET REGIMES & FRACDIFF FFD(d=0.20)
    # =========================================================================
    print("\n>>> [1/3] Preprocessing Market Regimes & VNINDEX FracDiff (Full History)...")
    t0 = time.time()
    df_regimes = classify_market_regimes(con)
    
    q_vni = """
    SELECT date, close 
    FROM core.market_index_daily 
    WHERE index_code = 'VNINDEX' AND close > 0
    ORDER BY date ASC
    """
    df_vni = con.execute(q_vni).df()
    df_vni["date"] = pd.to_datetime(df_vni["date"]).dt.date
    df_vni["log_close"] = np.log(df_vni["close"])
    df_vni["vni_fracdiff_d020"] = frac_diff_ffd(df_vni["log_close"], d=0.20)
    
    df_market_preprocessed = df_regimes.merge(df_vni[["date", "vni_fracdiff_d020"]], on="date", how="inner")
    df_market_preprocessed.rename(columns={"regime": "market_regime", "vol20": "volatility_20d_ann"}, inplace=True)
    
    # Materialize Table 1
    con.execute("DROP TABLE IF EXISTS preprocessed.market_regimes")
    con.execute("CREATE TABLE preprocessed.market_regimes AS SELECT * FROM df_market_preprocessed")
    cnt_mkt = con.execute("SELECT count(*) FROM preprocessed.market_regimes").fetchone()[0]
    print(f" -> [OK] preprocessed.market_regimes created: {cnt_mkt:,} trading days ({time.time()-t0:.2f}s)")

    # =========================================================================
    # PART 2: PREPROCESSED MACRO POLICY (477,733 DOCUMENTS)
    # =========================================================================
    print("\n>>> [2/3] Checking preprocessed.macro_policy...")
    t0 = time.time()
    try:
        cnt_pol_existing = con.execute("SELECT count(*) FROM preprocessed.macro_policy").fetchone()[0]
    except Exception:
        cnt_pol_existing = 0
        
    if cnt_pol_existing >= 477000:
        print(f" -> [OK] preprocessed.macro_policy already materialized with {cnt_pol_existing:,} rows. Skipping build.")
        cnt_pol = cnt_pol_existing
    else:
        q_policy = """
        SELECT 
            source_url,
            source,
            issuing_body,
            doc_type,
            published_at,
            headline,
            summary
        FROM core.macro_policy
        ORDER BY published_at ASC
        """
        df_policy = con.execute(q_policy).df()
        print(f" Loaded {len(df_policy):,} policy documents. Cleaning & classifying...")
        
        # 1. Text Normalization
        df_policy["headline_clean"] = df_policy["headline"].apply(lambda t: normalize_text(t, is_policy=True))
        df_policy["summary_clean"] = df_policy["summary"].apply(lambda t: normalize_text(t, is_policy=True) if t else "")
        
        # 2. Combined text for classification
        combined_texts = df_policy["headline_clean"] + " " + df_policy["summary_clean"]
        
        # 3. Classify 5 Pillars & Misrouted Corporate
        print(" Classifying policy pillars...")
        pillars_assigned = []
        misrouted_flags = []
        sector_links = []
        
        for text in combined_texts:
            matched = []
            sec_set = set()
            for p_code, p_info in POLICY_PILLARS.items():
                if p_info["pattern"].search(text):
                    matched.append(p_code)
                    for s_id in p_info["primary_sectors"]:
                        sec_set.add(s_id)
                        
            p_str = ", ".join(matched) if matched else "GENERAL_MACRO"
            is_misrouted = "MISROUTED_CORPORATE" in matched
            s_str = ", ".join(map(str, sorted(sec_set))) if sec_set else ""
            
            pillars_assigned.append(p_str)
            misrouted_flags.append(is_misrouted)
            sector_links.append(s_str)
            
        df_policy["policy_pillar"] = pillars_assigned
        df_policy["is_misrouted_corporate"] = misrouted_flags
        df_policy["affected_sectors"] = sector_links
        
        # 4. Entity Disambiguation (SBV vs Commercial Banking)
        print(" Disambiguating SBV vs Commercial Banking...")
        entity_tags = []
        for h, s in zip(df_policy["headline_clean"], df_policy["summary_clean"]):
            has_sbv, is_sec11 = disambiguate_banking_entities(h, s)
            if has_sbv and not is_sec11:
                entity_tags.append("SBV_POLICY_MAKER (No Sector 11)")
            elif is_sec11:
                entity_tags.append("SECTOR_11_BANKING (Operational)")
            else:
                entity_tags.append("GENERAL_MACRO")
        df_policy["entity_tag"] = entity_tags
        
        # 5. Exact & Near Deduplication Flag
        print(" Deduplicating text signatures...")
        seen_hashes = set()
        dup_flags = []
        for text in df_policy["headline_clean"]:
            h = hashlib.md5(text.encode("utf-8")).hexdigest()
            if h in seen_hashes:
                dup_flags.append(True)
            else:
                seen_hashes.add(h)
                dup_flags.append(False)
        df_policy["is_duplicate"] = dup_flags
        
        # Materialize Table 2
        cols_policy = [
            "source_url", "source", "issuing_body", "doc_type", "published_at",
            "headline_clean", "summary_clean", "policy_pillar", "is_misrouted_corporate",
            "affected_sectors", "entity_tag", "is_duplicate"
        ]
        df_policy_save = df_policy[cols_policy].copy()
        con.execute("DROP TABLE IF EXISTS preprocessed.macro_policy")
        con.execute("CREATE TABLE preprocessed.macro_policy AS SELECT * FROM df_policy_save")
        cnt_pol = con.execute("SELECT count(*) FROM preprocessed.macro_policy").fetchone()[0]
        print(f" -> [OK] preprocessed.macro_policy created: {cnt_pol:,} rows ({time.time()-t0:.2f}s)")

    # =========================================================================
    # PART 3: PREPROCESSED EVENTS (658,182 PIT EVENTS)
    # =========================================================================
    print("\n>>> [3/3] Preprocessing 658,182 PIT Events...")
    t0 = time.time()
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
    ORDER BY p.published_at ASC
    """
    df_events = con.execute(q_events).df()
    print(f" Loaded {len(df_events):,} valid PIT events. Applying 6 preprocessing steps...")
    
    # 1. Temporal Alignment
    df_events["pub_time_str"] = df_events["published_at"].dt.strftime("%H:%M:%S")
    df_events["is_midnight_ts"] = df_events["pub_time_str"] == "00:00:00"
    df_events["event_date"] = df_events["published_at"].dt.date
    
    # Filter flatline prices
    df_events["is_flatline"] = (df_events["p0"] == df_events["p5"]) & (df_events["p5"] == df_events["p30"])
    n_before = len(df_events)
    df_events = df_events[~df_events["is_flatline"]].copy()
    print(f" Filtered {n_before - len(df_events):,} untradeable flatline events. Remaining: {len(df_events):,}")
    
    # 2. Text Normalization & Sentiment Scoring
    print(" Normalizing headlines & scoring lexicon sentiment...")
    df_events["headline_clean"] = df_events["headline"].apply(lambda t: normalize_text(t, is_policy=False))
    df_events["sentiment_score"] = df_events["headline_clean"].apply(score_headline)
    
    # Deduplication
    seen_h = set()
    dup_ev = []
    for t in df_events["headline_clean"]:
        h = hashlib.md5(t.encode("utf-8")).hexdigest()
        if h in seen_h:
            dup_ev.append(True)
        else:
            seen_h.add(h)
            dup_ev.append(False)
    df_events["is_duplicate"] = dup_ev
    
    # Disambiguation
    def check_ev_disambig(h):
        has_sbv, is_sec11 = disambiguate_banking_entities(h, "")
        if has_sbv and not is_sec11:
            return "SBV_POLICY_MAKER (Filtered)"
        elif is_sec11:
            return "SECTOR_11_BANKING"
        return "GENERAL_EQUITY"
    df_events["entity_tag"] = df_events["headline_clean"].apply(check_ev_disambig)
    
    # 3. Tail Risk Sanitization (Winsorization [0.5%, 99.5%])
    print(" Computing returns & applying Winsorization [0.5%, 99.5%]...")
    df_events["ret_t5_pct"] = (df_events["p5"] - df_events["p0"]) / df_events["p0"] * 100.0
    df_events["ret_t30_pct"] = (df_events["p30"] - df_events["p0"]) / df_events["p0"] * 100.0
    df_events["raw_diff_pct"] = df_events["ret_t30_pct"] - df_events["ret_t5_pct"]
    
    q_low = df_events["raw_diff_pct"].quantile(0.005)
    q_high = df_events["raw_diff_pct"].quantile(0.995)
    df_events["winsorized_diff_pct"] = df_events["raw_diff_pct"].clip(q_low, q_high)
    print(f" Winsorize Bounds: [{q_low:.2f}%, {q_high:.2f}%]")
    
    # 4. Regime Partitioning Join
    print(" Joining Market Regimes & VNINDEX FracDiff...")
    df_events = df_events.merge(df_market_preprocessed[["date", "market_regime", "vni_fracdiff_d020"]],
                                left_on="event_date", right_on="date", how="left")
    df_events["market_regime"] = df_events["market_regime"].fillna("SIDEWAYS")
    
    # 5. RankGauss Transformation (Point-in-Time Rolling)
    print(" Applying RankGauss Normalization to Sentiment & Trading Volumes...")
    rg = PointInTimeRankGauss()
    df_events["rankgauss_sentiment_z"] = rg.fit_transform(df_events["sentiment_score"].values)
    
    # Load Volume and compute vectorized rolling RankGauss
    symbols_needed = set(df_events["symbol"].unique())
    print(f" Computing rolling RankGauss volume for {len(symbols_needed):,} unique symbols...")
    
    sym_list_str = "', '".join(symbols_needed)
    q_vols = f"""
    SELECT symbol, date, volume 
    FROM core.market_ohlcv_daily 
    WHERE volume > 0 AND symbol IN ('{sym_list_str}')
    ORDER BY symbol, date ASC
    """
    df_vols = con.execute(q_vols).df()
    df_vols["date"] = pd.to_datetime(df_vols["date"]).dt.date
    
    df_vols["vol_rank"] = df_vols.groupby("symbol")["volume"].transform(
        lambda s: s.rolling(250, min_periods=30).rank()
    )
    df_vols["vol_count"] = df_vols.groupby("symbol")["volume"].transform(
        lambda s: s.rolling(250, min_periods=30).count()
    )
    u = (df_vols["vol_rank"] + 0.5) / (df_vols["vol_count"] + 1.0)
    u = np.clip(u, 1e-6, 1.0 - 1e-6)
    df_vols["rankgauss_volume_z"] = np.sqrt(2.0) * special.erfinv(2.0 * u.values - 1.0)
    
    df_events = df_events.merge(
        df_vols[["symbol", "date", "rankgauss_volume_z"]],
        left_on=["symbol", "event_date"],
        right_on=["symbol", "date"],
        how="left"
    )
    
    # Materialize Table 3
    cols_events = [
        "symbol", "exchange", "event_date", "published_at", "is_midnight_ts",
        "headline_clean", "is_duplicate", "entity_tag", "sentiment_score", "rankgauss_sentiment_z",
        "p0", "p5", "p30", "ret_t5_pct", "ret_t30_pct", "raw_diff_pct", "winsorized_diff_pct",
        "market_regime", "vni_fracdiff_d020", "rankgauss_volume_z"
    ]
    df_events_save = df_events[cols_events].copy()
    con.execute("DROP TABLE IF EXISTS preprocessed.events")
    con.execute("CREATE TABLE preprocessed.events AS SELECT * FROM df_events_save")
    cnt_ev = con.execute("SELECT count(*) FROM preprocessed.events").fetchone()[0]
    print(f" -> [OK] preprocessed.events created: {cnt_ev:,} rows ({time.time()-t0:.2f}s)")
    
    # =========================================================================
    # PART 4: CREATE STANDALONE DATABASE & EXPORT CSV PREVIEW
    # =========================================================================
    print(f"\n>>> [4/4] Creating Standalone Database: {STANDALONE_DB_PATH}...")
    if os.path.exists(STANDALONE_DB_PATH):
        os.remove(STANDALONE_DB_PATH)
        
    con.execute(f"ATTACH '{STANDALONE_DB_PATH}' AS standalone_db")
    con.execute("CREATE TABLE standalone_db.market_regimes AS SELECT * FROM preprocessed.market_regimes")
    con.execute("CREATE TABLE standalone_db.macro_policy AS SELECT * FROM preprocessed.macro_policy")
    con.execute("CREATE TABLE standalone_db.events AS SELECT * FROM preprocessed.events")
    con.execute("DETACH standalone_db")
    con.close()
    
    # Export CSV Preview (500 rows)
    csv_preview_path = "test_pipeline/out/full_preprocessed_events_preview.csv"
    df_events_save.head(500).to_csv(csv_preview_path, index=False, encoding="utf-8-sig")
    
    elapsed = time.time() - start_time
    print("\n" + "=" * 85)
    print("FULL PREPROCESSING COMPLETED SUCCESSFULLY!")
    print(f"Total Processing Time: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
    print(f"1. Canonical DB Updated: {CANONICAL_DB_PATH}")
    print(f"   - preprocessed.market_regimes : {cnt_mkt:,} rows")
    print(f"   - preprocessed.macro_policy   : {cnt_pol:,} rows")
    print(f"   - preprocessed.events         : {cnt_ev:,} rows")
    print(f"2. Standalone Database Created: {STANDALONE_DB_PATH} ({os.path.getsize(STANDALONE_DB_PATH):,} bytes)")
    print(f"3. CSV Preview Exported       : {csv_preview_path} (500 rows UTF-8 BOM)")
    print("=" * 85)


if __name__ == "__main__":
    run_full_database_preprocessing()
