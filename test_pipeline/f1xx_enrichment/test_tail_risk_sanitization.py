"""test_pipeline/f1xx_enrichment/test_tail_risk_sanitization.py

Step 2: Tail Risk & Outlier Sanitization (Loop Engineering).
Audits:
2.1 Extreme Kurtosis & Outlier Decomposition (Root cause analysis: XDC & UPCOM penny pumps)
2.2 Robust Sanitization Treatments (Raw vs Exclude XDC vs Winsorization vs HOSE)
2.3 Penny Stock (<3k, <5k, >=10k VND) Variance & Effect Size Distortion Analysis
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import duckdb
import numpy as np
import pandas as pd
import scipy.stats as stats

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline

def compute_moments_and_cohen_d(series: pd.Series) -> dict:
    s = series.dropna()
    n = len(s)
    if n < 30:
        return {"n": n, "mean": 0, "sd": 0, "skew": 0, "kurtosis": 0, "cohen_d": 0}
    
    mean = float(s.mean())
    sd = float(s.std(ddof=1))
    skew = float(stats.skew(s, bias=False))
    kurt = float(stats.kurtosis(s, bias=False)) # excess kurtosis (Normal = 0)
    cohen_d = mean / sd if sd > 0 else 0.0
    
    return {
        "n": n,
        "mean_pct": mean * 100,
        "sd_pct": sd * 100,
        "skewness": skew,
        "excess_kurtosis": kurt,
        "cohen_d": cohen_d,
    }

def winsorize_series(series: pd.Series, lower_q: float = 0.005, upper_q: float = 0.995) -> pd.Series:
    low = series.quantile(lower_q)
    high = series.quantile(upper_q)
    return series.clip(lower=low, upper=high)

def run_tail_risk_audit(db_path: str = "db/test_db/vesta_test.duckdb"):
    print("="*75)
    print(">>> 2. TAIL RISK & OUTLIER SANITIZATION AUDIT (LOOP ENGINEERING) <<<")
    print("="*75)
    
    con = duckdb.connect(db_path, read_only=True)
    
    # -------------------------------------------------------------
    # 2.1 LOAD NEGATIVE SENTIMENT EVENTS
    # -------------------------------------------------------------
    print("\n[Sub-sequence 2.1] Loading negative sentiment events with forward horizons...")
    q = """
    SELECT 
        p.symbol,
        p.published_at,
        p.headline,
        p.price_at_publish,
        p.price_t1,
        p.price_t5,
        p.price_t30,
        s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 
      AND p.price_t5 > 0 
      AND p.price_t30 > 0
    """
    df = con.execute(q).df()
    con.close()
    
    # Filter negative sentiment
    df["sentiment_score"] = df["headline"].apply(score_headline)
    df_neg = df[df["sentiment_score"] < 0].copy()
    
    # Calculate returns and diff
    df_neg["ret_t5"] = (df_neg["price_t5"] - df_neg["price_at_publish"]) / df_neg["price_at_publish"]
    df_neg["ret_t30"] = (df_neg["price_t30"] - df_neg["price_at_publish"]) / df_neg["price_at_publish"]
    df_neg["diff_t30_t5"] = df_neg["ret_t30"] - df_neg["ret_t5"]
    
    total_neg = len(df_neg)
    print(f"Total sanitized negative events: {total_neg:,}")
    
    # Raw moments
    raw_m = compute_moments_and_cohen_d(df_neg["diff_t30_t5"])
    print(f"\n--- RAW BASELINE DISTRIBUTION ---")
    print(f"  - Mean Diff (T+30 - T+5):  {raw_m['mean_pct']:+.4f}%")
    print(f"  - Standard Deviation:     {raw_m['sd_pct']:.4f}%")
    print(f"  - Skewness:               {raw_m['skewness']:.2f}")
    print(f"  - Excess Kurtosis:        {raw_m['excess_kurtosis']:.2f}  <-- EXTREME NON-NORMALITY (Gaussian = 0)")
    print(f"  - Cohen's d Effect Size:  {raw_m['cohen_d']:.4f}")
    
    # -------------------------------------------------------------
    # TOP 10 EXTREME OUTLIERS
    # -------------------------------------------------------------
    print("\n--- TOP 10 EXTREME OUTLIERS (DIFF = RET_T30 - RET_T5) ---")
    df_neg["abs_diff"] = df_neg["diff_t30_t5"].abs()
    top10 = df_neg.sort_values("abs_diff", ascending=False).head(10)
    
    top10_out = []
    for idx, r in top10.iterrows():
        top10_out.append({
            "symbol": r["symbol"],
            "exchange": r["exchange"],
            "published_at": str(r["published_at"])[:10],
            "p0": float(r["price_at_publish"]),
            "p5": float(r["price_t5"]),
            "p30": float(r["price_t30"]),
            "diff_pct": float(r["diff_t30_t5"] * 100),
            "headline": r["headline"][:60],
        })
    df_top10 = pd.DataFrame(top10_out)
    print(df_top10[["symbol", "exchange", "published_at", "p0", "p30", "diff_pct", "headline"]].to_string(index=False))

    # -------------------------------------------------------------
    # 2.2 OUTLIER MITIGATION TREATMENTS
    # -------------------------------------------------------------
    print("\n[Sub-sequence 2.2] Evaluating 6 Outlier Sanitization Treatments...")
    
    # Treatment 1: Raw
    # Treatment 2: Exclude XDC
    df_no_xdc = df_neg[df_neg["symbol"] != "XDC"]
    m_no_xdc = compute_moments_and_cohen_d(df_no_xdc["diff_t30_t5"])
    
    # Treatment 3: Winsorized 0.5% - 99.5%
    s_win05 = winsorize_series(df_neg["diff_t30_t5"], 0.005, 0.995)
    m_win05 = compute_moments_and_cohen_d(s_win05)
    
    # Treatment 4: Winsorized 1.0% - 99.0%
    s_win10 = winsorize_series(df_neg["diff_t30_t5"], 0.010, 0.990)
    m_win10 = compute_moments_and_cohen_d(s_win10)
    
    # Treatment 5: HOSE-only Raw
    df_hose = df_neg[df_neg["exchange"] == "HOSE"]
    m_hose_raw = compute_moments_and_cohen_d(df_hose["diff_t30_t5"])
    
    # Treatment 6: HOSE-only Winsorized 0.5%
    s_hose_win = winsorize_series(df_hose["diff_t30_t5"], 0.005, 0.995)
    m_hose_win = compute_moments_and_cohen_d(s_hose_win)

    treatment_rows = [
        {"Treatment": "1. Raw Baseline (All)", "N": raw_m["n"], "Mean (%)": f"{raw_m['mean_pct']:+.2f}", "SD (%)": f"{raw_m['sd_pct']:.2f}", "Skew": f"{raw_m['skewness']:.2f}", "Kurtosis": f"{raw_m['excess_kurtosis']:.2f}", "Cohen's d": f"{raw_m['cohen_d']:.4f}"},
        {"Treatment": "2. Exclude XDC Only", "N": m_no_xdc["n"], "Mean (%)": f"{m_no_xdc['mean_pct']:+.2f}", "SD (%)": f"{m_no_xdc['sd_pct']:.2f}", "Skew": f"{m_no_xdc['skewness']:.2f}", "Kurtosis": f"{m_no_xdc['excess_kurtosis']:.2f}", "Cohen's d": f"{m_no_xdc['cohen_d']:.4f}"},
        {"Treatment": "3. Winsorized [0.5%, 99.5%]", "N": m_win05["n"], "Mean (%)": f"{m_win05['mean_pct']:+.2f}", "SD (%)": f"{m_win05['sd_pct']:.2f}", "Skew": f"{m_win05['skewness']:.2f}", "Kurtosis": f"{m_win05['excess_kurtosis']:.2f}", "Cohen's d": f"{m_win05['cohen_d']:.4f}"},
        {"Treatment": "4. Winsorized [1.0%, 99.0%]", "N": m_win10["n"], "Mean (%)": f"{m_win10['mean_pct']:+.2f}", "SD (%)": f"{m_win10['sd_pct']:.2f}", "Skew": f"{m_win10['skewness']:.2f}", "Kurtosis": f"{m_win10['excess_kurtosis']:.2f}", "Cohen's d": f"{m_win10['cohen_d']:.4f}"},
        {"Treatment": "5. HOSE-Only Raw", "N": m_hose_raw["n"], "Mean (%)": f"{m_hose_raw['mean_pct']:+.2f}", "SD (%)": f"{m_hose_raw['sd_pct']:.2f}", "Skew": f"{m_hose_raw['skewness']:.2f}", "Kurtosis": f"{m_hose_raw['excess_kurtosis']:.2f}", "Cohen's d": f"{m_hose_raw['cohen_d']:.4f}"},
        {"Treatment": "6. HOSE-Only Winsorized [0.5%]", "N": m_hose_win["n"], "Mean (%)": f"{m_hose_win['mean_pct']:+.2f}", "SD (%)": f"{m_hose_win['sd_pct']:.2f}", "Skew": f"{m_hose_win['skewness']:.2f}", "Kurtosis": f"{m_hose_win['excess_kurtosis']:.2f}", "Cohen's d": f"{m_hose_win['cohen_d']:.4f}"},
    ]
    df_treatments = pd.DataFrame(treatment_rows)
    print(df_treatments.to_string(index=False))

    # -------------------------------------------------------------
    # 2.3 PENNY STOCK DISTORTION ANALYSIS
    # -------------------------------------------------------------
    print("\n[Sub-sequence 2.3] Evaluating Penny Stock Thresholds (<3k, <5k, >=10k VND)...")
    penny3k = df_neg[df_neg["price_at_publish"] < 3.0]
    penny5k = df_neg[df_neg["price_at_publish"] < 5.0]
    midlarge = df_neg[df_neg["price_at_publish"] >= 10.0]
    
    m_p3k = compute_moments_and_cohen_d(penny3k["diff_t30_t5"])
    m_p5k = compute_moments_and_cohen_d(penny5k["diff_t30_t5"])
    m_ml = compute_moments_and_cohen_d(midlarge["diff_t30_t5"])
    
    penny_rows = [
        {"Category": "Penny Stocks (< 3,000 VND)", "N": m_p3k["n"], "Mean Diff (%)": f"{m_p3k['mean_pct']:+.2f}", "SD (%)": f"{m_p3k['sd_pct']:.2f}", "Kurtosis": f"{m_p3k['excess_kurtosis']:.2f}", "Win-Rate (%)": f"{(penny3k['diff_t30_t5'] > 0).mean()*100:.1f}%"},
        {"Category": "Small Caps (< 5,000 VND)", "N": m_p5k["n"], "Mean Diff (%)": f"{m_p5k['mean_pct']:+.2f}", "SD (%)": f"{m_p5k['sd_pct']:.2f}", "Kurtosis": f"{m_p5k['excess_kurtosis']:.2f}", "Win-Rate (%)": f"{(penny5k['diff_t30_t5'] > 0).mean()*100:.1f}%"},
        {"Category": "Mid & Large Caps (>= 10,000 VND)", "N": m_ml["n"], "Mean Diff (%)": f"{m_ml['mean_pct']:+.2f}", "SD (%)": f"{m_ml['sd_pct']:.2f}", "Kurtosis": f"{m_ml['excess_kurtosis']:.2f}", "Win-Rate (%)": f"{(midlarge['diff_t30_t5'] > 0).mean()*100:.1f}%"},
    ]
    df_penny = pd.DataFrame(penny_rows)
    print(df_penny.to_string(index=False))
    
    # Save results to json
    os.makedirs("test_pipeline/out", exist_ok=True)
    report_file = "test_pipeline/out/tail_risk_sanitization_report.json"
    report_data = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_negative_events": total_neg,
        "treatments": treatment_rows,
        "top10_outliers": top10_out,
        "penny_analysis": penny_rows,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nReport saved to {report_file}")
    
    return report_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="db/test_db/vesta_test.duckdb")
    args = parser.parse_args()
    run_tail_risk_audit(args.db_path)
