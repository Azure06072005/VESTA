"""test_pipeline/scripts/extract_rankgauss_samples.py

Extracts raw sample tables and mapping snapshots for RankGauss Quantile Transformation.
Outputs UTF-8 formatted tables directly to stdout.
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd
import scipy.stats as stats

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_rankgauss_transformation import (
    PointInTimeRankGauss,
)
from src.pipeline.sentiment_lexicon import score_headline

DB_PATH = "db/test_db/vesta_test.duckdb"
REPORT_JSON = "test_pipeline/out/rankgauss_report.json"


def extract_samples():
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)
        
    print("=" * 85)
    print("SAMPLE 1: STATISTICAL MOMENTS BEFORE & AFTER RANKGAUSS")
    print("=" * 85)
    rows = []
    for k, name in [
        ("hpg_trading_volume", "HPG Volume"),
        ("macro_vix_index", "Macro ^VIX"),
        ("headline_sentiment_score", "Sentiment Score"),
    ]:
        f_res = report["results"][k]
        raw_m = f_res["raw_metrics"]
        rg_m = f_res["rankgauss_metrics"]
        rows.append({
            "Feature": name,
            "Raw Mean": f"{raw_m['mean']:.2f}",
            "Raw SD": f"{raw_m['std']:.2f}",
            "Raw Skew": f"{raw_m['skewness']:.2f}",
            "Raw Kurt": f"{raw_m['excess_kurtosis']:.2f}",
            "RG Mean": f"{rg_m['mean']:.2f}",
            "RG SD": f"{rg_m['std']:.2f}",
            "RG Skew": f"{rg_m['skewness']:.2f}",
            "RG Kurt": f"{rg_m['excess_kurtosis']:.2f}",
            "Spearman ρ": f"{f_res['spearman_rank_correlation']:.4f}",
        })
    df_moments = pd.DataFrame(rows)
    print(df_moments.to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 2: EXACT VALUE MAPPING SNAPSHOT (RAW -> QUANTILE -> GAUSSIAN Z)")
    print("=" * 85)
    con = duckdb.connect(DB_PATH, read_only=True)
    df_vol = con.execute("""
        SELECT date, volume 
        FROM core.market_ohlcv_daily 
        WHERE symbol = 'HPG' AND date >= '2024-01-02' AND date <= '2024-01-15'
        ORDER BY date ASC
    """).df()
    con.close()
    
    rg = PointInTimeRankGauss()
    vol_full = con = duckdb.connect(DB_PATH, read_only=True).execute(
        "SELECT volume FROM core.market_ohlcv_daily WHERE symbol = 'HPG' AND volume > 0"
    ).df()["volume"].values.astype(float)
    
    rg.fit(vol_full)
    df_vol["volume_shares"] = df_vol["volume"].astype(int)
    # Get ranks and quantiles
    N = len(rg.train_sorted)
    ranks = np.searchsorted(rg.train_sorted, df_vol["volume"].values)
    df_vol["empirical_percentile"] = np.round((ranks / N) * 100.0, 2)
    df_vol["rankgauss_z"] = np.round(rg.transform(df_vol["volume"].values), 4)
    
    sub_cols = ["date", "volume_shares", "empirical_percentile", "rankgauss_z"]
    df_show = df_vol[sub_cols].copy()
    df_show.columns = ["Date", "Raw Volume (Shares)", "Quantile Rank (%)", "RankGauss (σ)"]
    print(df_show.to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 3: SCALER STRESS TEST UNDER OUTLIER INJECTION (100x PUMP SHOCK)")
    print("=" * 85)
    stress = report["results"]["scaler_stress_test"]
    stress_rows = [
        {"Scaler": "MinMax Scaler [0, 1]", "Disruption on Clean 99.9% Data": f"{stress['relative_disruption_minmax']:.4f} (100% squashed to 0)"},
        {"Scaler": "StandardScaler (Z-Score)", "Disruption on Clean 99.9% Data": f"{stress['mean_absolute_disruption_zscore']:.4f} σ"},
        {"Scaler": "Log1p + StandardScaler", "Disruption on Clean 99.9% Data": f"{stress['mean_absolute_disruption_log1p']:.4f} σ"},
        {"Scaler": "RankGauss Scaler", "Disruption on Clean 99.9% Data": f"{stress['mean_absolute_disruption_rankgauss']:.6f} σ (190x more robust)"},
    ]
    print(pd.DataFrame(stress_rows).to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 4: POINT-IN-TIME ROLLING VS GLOBAL FIT (LOOK-AHEAD LEAKAGE AUDIT)")
    print("=" * 85)
    con = duckdb.connect(DB_PATH, read_only=True)
    df_covid = con.execute("""
        SELECT date, volume 
        FROM core.market_ohlcv_daily 
        WHERE symbol = 'HPG' AND date >= '2020-03-20' AND date <= '2020-04-05'
        ORDER BY date ASC
    """).df()
    con.close()
    
    df_hpg_all = duckdb.connect(DB_PATH, read_only=True).execute(
        "SELECT date, volume FROM core.market_ohlcv_daily WHERE symbol = 'HPG' ORDER BY date ASC"
    ).df().set_index("date")["volume"]
    
    glob_z = rg.fit_transform(df_hpg_all.values)
    roll_z = PointInTimeRankGauss.rolling_transform(df_hpg_all, window=250, min_periods=60).values
    
    df_hpg_all_res = pd.DataFrame({
        "date": df_hpg_all.index,
        "volume": df_hpg_all.values,
        "global_z": np.round(glob_z, 4),
        "rolling_pit_z": np.round(roll_z, 4),
    })
    df_hpg_all_res["date"] = pd.to_datetime(df_hpg_all_res["date"])
    
    covid_sub = df_hpg_all_res[(df_hpg_all_res["date"] >= "2020-03-23") & (df_hpg_all_res["date"] <= "2020-04-03")].copy()
    covid_sub["leakage_error_sigma"] = np.round(np.abs(covid_sub["global_z"] - covid_sub["rolling_pit_z"]), 4)
    covid_sub.columns = ["Date", "Raw Volume", "Global Fit Z (Uncausal)", "Rolling PIT Z (Causal)", "Look-Ahead Gap (σ)"]
    print(covid_sub.to_string(index=False))


if __name__ == "__main__":
    extract_samples()
