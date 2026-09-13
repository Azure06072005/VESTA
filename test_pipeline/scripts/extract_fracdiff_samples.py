"""test_pipeline/scripts/extract_fracdiff_samples.py

Extracts raw sample tables and snapshots for Fractional Differentiation (FracDiff - FFD).
Prints directly to stdout with UTF-8 encoding.
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    get_weights_ffd,
    frac_diff_ffd,
)

REPORT_JSON = "test_pipeline/out/fractional_differentiation_report.json"
DB_PATH = "db/test_db/vesta_test.duckdb"


def extract_samples():
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)
        
    print("=" * 85)
    print("SAMPLE 1: VNINDEX FFD GRID SEARCH (STATIONARITY VS MEMORY FRONTIER)")
    print("=" * 85)
    df_grid = pd.DataFrame(report["vnindex"]["grid"])
    cols = ["d", "memory_window_bars", "adf_stat", "p_value", "is_stationary_95", "corr_pearson", "corr_spearman"]
    df_show = df_grid[cols].copy()
    df_show.rename(columns={
        "memory_window_bars": "Window (Bars)",
        "adf_stat": "ADF Stat",
        "p_value": "p-value",
        "is_stationary_95": "Stat (95%)?",
        "corr_pearson": "Pearson Corr",
        "corr_spearman": "Spearman Corr"
    }, inplace=True)
    print(df_show.to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 2: FFD WEIGHT VECTORS (w_0 TO w_8) ACROSS DEGREE d")
    print("=" * 85)
    test_ds = [0.15, 0.30, 0.45, 0.60, 1.00]
    weights_dict = {}
    for d in test_ds:
        w_rev = get_weights_ffd(d, thres=1e-4)
        w = list(w_rev[::-1])
        # Pad with 0.0 if length < 9
        if len(w) < 9:
            w = w + [0.0] * (9 - len(w))
        w_sub = [round(float(x), 5) for x in w[:9]]
        weights_dict[f"d = {d:.2f}"] = w_sub
    df_weights = pd.DataFrame(weights_dict, index=[f"w_{k} (Lag {k})" for k in range(9)])
    print(df_weights.to_string())

    print("\n" + "=" * 85)
    print("SAMPLE 3: RAW DATA SNAPSHOT AT VNINDEX MARKET BOTTOM (NOVEMBER 2022)")
    print("=" * 85)
    con = duckdb.connect(DB_PATH, read_only=True)
    df_vni = con.execute("""
        SELECT date, close 
        FROM core.market_index_daily 
        WHERE index_code = 'VNINDEX' AND date >= '2022-11-01' AND date <= '2022-11-30'
        ORDER BY date ASC
    """).df()
    con.close()
    
    # We compute FFD using full series to avoid edge window effect
    con = duckdb.connect(DB_PATH, read_only=True)
    df_full = con.execute("""
        SELECT date, close 
        FROM core.market_index_daily 
        WHERE index_code = 'VNINDEX'
        ORDER BY date ASC
    """).df()
    con.close()
    
    df_full["log_p"] = np.log(df_full["close"])
    df_full["frac_diff_020"] = frac_diff_ffd(df_full["log_p"], d=0.20)
    df_full["ret_d1_pct"] = df_full["close"].pct_change() * 100
    
    df_full["date"] = pd.to_datetime(df_full["date"])
    sub_df = df_full[(df_full["date"] >= pd.to_datetime("2022-11-10")) & 
                     (df_full["date"] <= pd.to_datetime("2022-11-25"))].copy()
    
    sub_df = sub_df[["date", "close", "log_p", "frac_diff_020", "ret_d1_pct"]]
    sub_df.columns = ["Date", "VNINDEX Close", "Log(Close)", "FracDiff (d=0.20)", "Daily Return (%)"]
    print(sub_df.to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 4: VN30 ASSET SENSITIVITY & PRESERVED MEMORY BOOST")
    print("=" * 85)
    df_assets = pd.DataFrame(report["vn30_assets"])
    df_assets_show = df_assets[["symbol", "n_bars", "d_star_95", "corr_at_dstar", "corr_at_d1"]].copy()
    df_assets_show["memory_boost"] = df_assets_show["corr_at_dstar"] - df_assets_show["corr_at_d1"]
    df_assets_show.columns = ["Ticker", "Total Bars", "Optimal d*", "Corr(d*)", "Corr(d=1)", "Memory Boost"]
    print(df_assets_show.to_string(index=False))


if __name__ == "__main__":
    extract_samples()
