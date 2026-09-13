"""test_pipeline/scripts/extract_tail_risk_samples.py

Extracts raw sample records for 2. Tail Risk & Outlier Sanitization.
"""
import os
import sys
import duckdb
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
DB_PATH = "db/test_db/vesta_test.duckdb"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline

def extract_samples():
    con = duckdb.connect(DB_PATH, read_only=True)
    q = """
    SELECT 
        p.symbol, p.published_at::DATE as event_date, p.headline,
        p.price_at_publish as p0, p.price_t5 as p5, p.price_t30 as p30,
        s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
    """
    df = con.execute(q).df()
    con.close()
    
    df["sentiment_score"] = df["headline"].apply(score_headline)
    df_neg = df[df["sentiment_score"] < 0].copy()
    
    df_neg["ret_t5_pct"] = (df_neg["p5"] - df_neg["p0"]) / df_neg["p0"] * 100
    df_neg["ret_t30_pct"] = (df_neg["p30"] - df_neg["p0"]) / df_neg["p0"] * 100
    df_neg["diff_pct"] = df_neg["ret_t30_pct"] - df_neg["ret_t5_pct"]
    
    # 1. Top 4 Outliers
    top4 = df_neg.sort_values("diff_pct", ascending=False).head(4).copy()
    print("### SAMPLE 1: TOP EXTREME OUTLIERS (PENNY STOCK PUMPS & DELISTING)")
    print(top4[["symbol", "exchange", "event_date", "p0", "p5", "p30", "diff_pct", "headline"]].to_string(index=False))
    
    # 2. Winsorization clamping comparison on these 4
    q_low = df_neg["diff_pct"].quantile(0.005)
    q_high = df_neg["diff_pct"].quantile(0.995)
    print(f"\nWinsorization Boundaries [0.5%, 99.5%]: Lower = {q_low:.2f}%, Upper = {q_high:.2f}%")
    
    top4["winsorized_diff_pct"] = top4["diff_pct"].clip(q_low, q_high)
    print("\n### SAMPLE 2: WINSORIZATION EFFECT (CLAMPING TAILS)")
    print(top4[["symbol", "p0", "p30", "diff_pct", "winsorized_diff_pct"]].to_string(index=False))

    # 3. Penny vs Bluechip Comparison
    penny_sample = df_neg[df_neg["p0"] < 3.0].sort_values("diff_pct", ascending=False).iloc[[0, 10, 50, 100]][["symbol", "exchange", "p0", "diff_pct", "headline"]]
    print("\n### SAMPLE 3: PENNY STOCK SAMPLES (< 3,000 VND)")
    print(penny_sample.to_string(index=False))
    
    bluechip_sample = df_neg[(df_neg["p0"] >= 20.0) & (df_neg["exchange"] == "HOSE")].head(4)[["symbol", "exchange", "p0", "diff_pct", "headline"]]
    print("\n### SAMPLE 4: LIQUID BLUECHIPS (HOSE >= 20,000 VND)")
    print(bluechip_sample.to_string(index=False))

if __name__ == "__main__":
    extract_samples()
