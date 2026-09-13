"""test_pipeline/f1xx_enrichment/test_regime_partitioning_and_bootstrap.py

Step 6: Regime-Conditional Partitioning & Clustered Bootstrap for VESTA.
Evaluates the robustness of the negative sentiment mean-reversion hypothesis across:
1. Macro Market Regimes: BULL, BEAR, SIDEWAYS, CRISIS_HIGH_VOL.
2. Clustered Block Bootstrap (1,000 resamples): Compares I.I.D. vs Clustered Bootstrap
   to expose cross-sectional correlation and compute honest 95% Confidence Intervals.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import duckdb
import numpy as np
import pandas as pd
import scipy.stats as stats

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "db/test_db/vesta_test.duckdb"
OUT_REPORT = "test_pipeline/out/regime_bootstrap_report.json"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline


def classify_market_regimes(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Computes technical regime indicators on VNINDEX daily series:
    - SMA50 and SMA200 trend filters.
    - 20-day annualized rolling volatility.
    Classifies each trading day into: BULL, BEAR, CRISIS_HIGH_VOL, SIDEWAYS.
    """
    q = """
    SELECT date, close 
    FROM core.market_index_daily 
    WHERE index_code = 'VNINDEX' AND close > 0
    ORDER BY date ASC
    """
    df_vni = con.execute(q).df()
    df_vni["date"] = pd.to_datetime(df_vni["date"]).dt.date
    
    # Technical Indicators
    df_vni["sma50"] = df_vni["close"].rolling(50).mean()
    df_vni["sma200"] = df_vni["close"].rolling(200).mean()
    # 20-day annualized volatility (252 trading days)
    df_vni["vol20"] = df_vni["close"].pct_change().rolling(20).std() * np.sqrt(252) * 100.0
    
    def get_regime(row):
        if pd.isna(row["sma200"]) or pd.isna(row["vol20"]):
            return "WARMUP"
        # High volatility / panic shock regime (top quartile of historical volatility)
        if row["vol20"] > 28.0:
            return "CRISIS_HIGH_VOL"
        # Bull regime: Price above SMA50 and SMA50 >= SMA200
        if row["close"] > row["sma50"] and row["sma50"] >= row["sma200"]:
            return "BULL"
        # Bear regime: Price below SMA50 and SMA50 <= SMA200
        if row["close"] < row["sma50"] and row["sma50"] <= row["sma200"]:
            return "BEAR"
        # Sideways / Range-bound consolidation
        return "SIDEWAYS"
        
    df_vni["regime"] = df_vni.apply(get_regime, axis=1)
    return df_vni[["date", "close", "vol20", "regime"]]


def run_regime_and_bootstrap_audit():
    print("=" * 80)
    print("STEP 6: REGIME-CONDITIONAL PARTITIONING & CLUSTERED BOOTSTRAP AUDIT")
    print("=" * 80)
    
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Classify VNINDEX regimes
    print("\n[1/5] Classifying VNINDEX historical market regimes (2007 - 2026)...")
    df_regimes = classify_market_regimes(con)
    regime_counts = df_regimes[df_regimes["regime"] != "WARMUP"]["regime"].value_counts()
    print("VNINDEX Days per Regime:")
    for reg, cnt in regime_counts.items():
        print(f" -> {reg:<16}: {cnt} trading days ({cnt / len(df_regimes) * 100:.1f}%)")
        
    # 2. Fetch pit_events and join with regime
    print("\n[2/5] Loading and scoring PIT events for negative sentiment...")
    q_events = """
    SELECT 
        p.symbol,
        p.published_at::DATE as event_date,
        p.headline,
        p.price_at_publish as p0,
        p.price_t5 as p5,
        p.price_t30 as p30,
        s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
    """
    df_events = con.execute(q_events).df()
    con.close()
    
    df_events["event_date"] = pd.to_datetime(df_events["event_date"]).dt.date
    df_events["sentiment_score"] = df_events["headline"].apply(score_headline)
    df_neg = df_events[df_events["sentiment_score"] < 0].copy()
    
    # Join with market regime on event_date
    df_neg = df_neg.merge(df_regimes, left_on="event_date", right_on="date", how="inner")
    df_neg = df_neg[df_neg["regime"] != "WARMUP"].copy()
    
    # Compute return diff (P30 - P0)/P0 - (P5 - P0)/P0 = (P30 - P5)/P0
    df_neg["ret_t5"] = (df_neg["p5"] - df_neg["p0"]) / df_neg["p0"] * 100.0
    df_neg["ret_t30"] = (df_neg["p30"] - df_neg["p0"]) / df_neg["p0"] * 100.0
    df_neg["diff_pct"] = df_neg["ret_t30"] - df_neg["ret_t5"]
    
    # Winsorize [0.5%, 99.5%] (proven in Step 2 to eliminate lottery pump distortions like XDC)
    q_low = df_neg["diff_pct"].quantile(0.005)
    q_high = df_neg["diff_pct"].quantile(0.995)
    df_neg["diff_clean"] = df_neg["diff_pct"].clip(q_low, q_high)
    
    print(f"Total Negative Events Analyzed: {len(df_neg):,} across {df_neg['event_date'].nunique():,} distinct trading dates")
    
    # 3. Regime-Conditional Breakdown
    print("\n[3/5] Evaluating Signal Performance Across Market Regimes...")
    regime_results = {}
    regimes_to_eval = ["ALL", "BULL", "BEAR", "SIDEWAYS", "CRISIS_HIGH_VOL"]
    
    for reg in regimes_to_eval:
        sub = df_neg if reg == "ALL" else df_neg[df_neg["regime"] == reg]
        diffs = sub["diff_clean"].values
        n = len(diffs)
        mean_ret = float(np.mean(diffs))
        std_ret = float(np.std(diffs, ddof=1))
        win_rate = float(np.mean(diffs > 0) * 100.0)
        # Annualized Sharpe: holding period is 25 trading days (T+5 to T+30) -> sqrt(252 / 25) = ~3.175
        ann_sharpe = float(mean_ret / (std_ret + 1e-6) * np.sqrt(252.0 / 25.0))
        cohen_d = float(mean_ret / (std_ret + 1e-6))
        left_tail_5pct = float(np.percentile(diffs, 5))
        
        regime_results[reg] = {
            "regime": reg,
            "n_events": int(n),
            "pct_of_total": round(n / len(df_neg) * 100.0, 1),
            "mean_return_pct": round(mean_ret, 2),
            "std_return_pct": round(std_ret, 2),
            "win_rate_pct": round(win_rate, 2),
            "annualized_sharpe": round(ann_sharpe, 4),
            "cohen_d": round(cohen_d, 4),
            "left_tail_5pct": round(left_tail_5pct, 2),
        }
        
    # Print Regime Breakdown Table
    print(f"{'Regime':<16} | {'N Events':<10} | {'Mean Ret (%)':<14} | {'Win Rate (%)':<14} | {'Ann. Sharpe':<12} | {'Cohen d':<10} | {'5% Tail Risk':<12}")
    print("-" * 88)
    for reg in regimes_to_eval:
        r = regime_results[reg]
        print(f"{r['regime']:<16} | {r['n_events']:<10} | {r['mean_return_pct']:<14.2f} | {r['win_rate_pct']:<14.2f} | {r['annualized_sharpe']:<12.4f} | {r['cohen_d']:<10.4f} | {r['left_tail_5pct']:<12.2f}")

    # 4. Clustered Block Bootstrap vs. I.I.D. Bootstrap (1,000 resamples)
    print("\n[4/5] Running 1,000 Resamples: I.I.D. Bootstrap vs. Clustered Block Bootstrap...")
    np.random.seed(42)
    B = 1000
    
    # Method A: I.I.D. Bootstrap
    all_diffs = df_neg["diff_clean"].values
    N = len(all_diffs)
    iid_means = np.empty(B)
    iid_sharpes = np.empty(B)
    
    for b in range(B):
        sample = np.random.choice(all_diffs, size=N, replace=True)
        m = np.mean(sample)
        s = np.std(sample, ddof=1)
        iid_means[b] = m
        iid_sharpes[b] = m / (s + 1e-6) * np.sqrt(252.0 / 25.0)
        
    # Method B: Clustered Block Bootstrap (Clustered by Event Week to preserve panic cross-correlation)
    df_neg["year_week"] = pd.to_datetime(df_neg["event_date"]).dt.to_period("W")
    unique_weeks = df_neg["year_week"].unique()
    n_weeks = len(unique_weeks)
    week_groups = [group["diff_clean"].values for _, group in df_neg.groupby("year_week")]
    
    clustered_means = np.empty(B)
    clustered_sharpes = np.empty(B)
    
    for b in range(B):
        # Sample cluster weeks with replacement
        sampled_week_indices = np.random.choice(len(week_groups), size=len(week_groups), replace=True)
        # Concatenate all events belonging to sampled weeks
        sampled_events = np.concatenate([week_groups[idx] for idx in sampled_week_indices])
        m = np.mean(sampled_events)
        s = np.std(sampled_events, ddof=1)
        clustered_means[b] = m
        clustered_sharpes[b] = m / (s + 1e-6) * np.sqrt(252.0 / 25.0)
        
    # Calculate 95% Confidence Intervals
    ci_iid_mean = (np.percentile(iid_means, 2.5), np.percentile(iid_means, 97.5))
    ci_clustered_mean = (np.percentile(clustered_means, 2.5), np.percentile(clustered_means, 97.5))
    
    ci_iid_sharpe = (np.percentile(iid_sharpes, 2.5), np.percentile(iid_sharpes, 97.5))
    ci_clustered_sharpe = (np.percentile(clustered_sharpes, 2.5), np.percentile(clustered_sharpes, 97.5))
    
    width_iid = ci_iid_mean[1] - ci_iid_mean[0]
    width_clustered = ci_clustered_mean[1] - ci_clustered_mean[0]
    ci_inflation_ratio = width_clustered / width_iid
    
    prob_sharpe_le_zero_iid = float(np.mean(iid_sharpes <= 0.0) * 100.0)
    prob_sharpe_le_zero_clustered = float(np.mean(clustered_sharpes <= 0.0) * 100.0)
    
    print("\n--- Bootstrap Confidence Interval Comparison (95%) ---")
    print(f"I.I.D. Bootstrap Mean CI     : [{ci_iid_mean[0]:.2f}%, {ci_iid_mean[1]:.2f}%] (Width: {width_iid:.2f}%)")
    print(f"Clustered Bootstrap Mean CI : [{ci_clustered_mean[0]:.2f}%, {ci_clustered_mean[1]:.2f}%] (Width: {width_clustered:.2f}%)")
    print(f"CI Expansion Factor         : {ci_inflation_ratio:.2f}x (Clustered CI is {ci_inflation_ratio:.2f}x wider due to cross-asset correlation!)")
    print(f"I.I.D. Sharpe CI            : [{ci_iid_sharpe[0]:.4f}, {ci_iid_sharpe[1]:.4f}] | P(Sharpe <= 0): {prob_sharpe_le_zero_iid:.2f}%")
    print(f"Clustered Sharpe CI         : [{ci_clustered_sharpe[0]:.4f}, {ci_clustered_sharpe[1]:.4f}] | P(Sharpe <= 0): {prob_sharpe_le_zero_clustered:.2f}%")
    
    # Compile Report
    bootstrap_comparison = {
        "num_iterations": B,
        "num_clusters_weeks": int(n_weeks),
        "iid_bootstrap": {
            "mean_ci_95": [round(ci_iid_mean[0], 2), round(ci_iid_mean[1], 2)],
            "mean_ci_width": round(width_iid, 2),
            "sharpe_ci_95": [round(ci_iid_sharpe[0], 4), round(ci_iid_sharpe[1], 4)],
            "prob_sharpe_le_zero_pct": prob_sharpe_le_zero_iid,
        },
        "clustered_block_bootstrap": {
            "mean_ci_95": [round(ci_clustered_mean[0], 2), round(ci_clustered_mean[1], 2)],
            "mean_ci_width": round(width_clustered, 2),
            "sharpe_ci_95": [round(ci_clustered_sharpe[0], 4), round(ci_clustered_sharpe[1], 4)],
            "prob_sharpe_le_zero_pct": prob_sharpe_le_zero_clustered,
        },
        "ci_expansion_factor": round(ci_inflation_ratio, 2),
    }
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_negative_events": len(df_neg),
        "regime_breakdown": regime_results,
        "bootstrap_audit": bootstrap_comparison,
    }
    
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n[OK] Report exported to {OUT_REPORT}")


if __name__ == "__main__":
    run_regime_and_bootstrap_audit()
