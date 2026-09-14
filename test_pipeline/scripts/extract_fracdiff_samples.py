"""Extracts raw representative data samples for Module 3: Fractional Differentiation (FracDiff).

Outputs 3 quantitative audit tables:
Table 1: Cross-Sectional Optimization across VN30 Flagships.
Table 2: Order-by-Order Tradeoff Spectrum for HPG (d = 0.0 to 1.0).
Table 3: Real Daily Price Series with Raw Close, Log Price, Daily Return (d=1.0), and FracDiff (d=0.30).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    frac_diff_ffd,
)


def extract_samples():
    print("=" * 105)
    print("TABLE 1: CROSS-SECTIONAL OPTIMAL d* & MEMORY RETENTION ACROSS VN30 FLAGSHIP EQUITIES")
    print("=" * 105)

    with open("test_pipeline/out/fracdiff_benchmark_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    df_summary = pd.DataFrame(data["summary"])
    df_summary["adf_p_val_sci"] = df_summary["adf_p_val"].apply(lambda x: f"{x:.4e}")
    df_summary["correlation_with_raw"] = df_summary["correlation_with_raw"].apply(lambda x: f"{x:.4f}")
    df_summary["memory_retention_r2_pct"] = df_summary["memory_retention_r2"].apply(lambda x: f"{x*100:.1f}%")

    cols = [
        "symbol", "total_bars", "optimal_d", "adf_p_val_sci",
        "correlation_with_raw", "memory_retention_r2_pct", "window_width"
    ]
    print(df_summary[cols].to_string(index=False))

    print("\n" + "=" * 105)
    print("TABLE 2: THE STATIONARITY VS. MEMORY TRADEOFF SPECTRUM (HPG CASE STUDY: d = 0.00 TO 1.00)")
    print("=" * 105)

    hpg_grid = data["details"]["HPG"]["grid"]
    df_hpg = pd.DataFrame(hpg_grid)
    df_hpg["adf_stat"] = df_hpg["adf_stat"].apply(lambda x: f"{x:.4f}")
    df_hpg["p_val"] = df_hpg["p_val"].apply(lambda x: f"{x:.4e}")
    df_hpg["corr"] = df_hpg["corr"].apply(lambda x: f"{x:.4f}")
    df_hpg["R2_memory"] = df_hpg["corr"].apply(lambda x: f"{float(x)**2*100:.1f}%")

    cols_hpg = ["d", "adf_stat", "p_val", "is_stationary", "corr", "R2_memory", "window_width"]
    print(df_hpg[cols_hpg].to_string(index=False))

    print("\n" + "=" * 105)
    print("TABLE 3: DUCKDB REAL PRICE HISTORY: RAW CLOSE VS DAILY RETURN (d=1.0) VS FRACDIFF (d=0.30)")
    print("=" * 105)

    con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)
    df_raw = con.execute("""
        SELECT date, close 
        FROM core.market_ohlcv_daily 
        WHERE symbol = 'HPG' AND close > 0
        ORDER BY date DESC
        LIMIT 30
    """).df()
    con.close()

    df_raw = df_raw.sort_values("date").reset_index(drop=True)
    log_p = pd.Series(np.log(df_raw["close"].values), index=df_raw["date"])

    # Compute full series for accurate FFD convolution
    con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)
    df_full = con.execute("""
        SELECT date, close 
        FROM core.market_ohlcv_daily 
        WHERE symbol = 'HPG' AND close > 0
        ORDER BY date ASC
    """).df()
    con.close()

    full_log = pd.Series(np.log(df_full["close"].values), index=df_full["date"])
    fd_030 = frac_diff_ffd(full_log, d=0.30, thres=1e-4)
    ret_10 = full_log.diff()

    # Align with the last 15 days
    recent_dates = df_raw["date"].tail(15).tolist()
    sample_rows = []
    for dt in recent_dates:
        row_close = df_full[df_full["date"] == dt]["close"].values[0]
        row_log = full_log.loc[dt]
        row_ret = ret_10.loc[dt] if dt in ret_10.index else np.nan
        row_fd = fd_030.loc[dt] if dt in fd_030.index else np.nan

        sample_rows.append({
            "Date": str(dt),
            "Close (VND)": f"{row_close:,.0f}",
            "Log Price": f"{row_log:.4f}",
            "Daily Return (d=1.0)": f"{row_ret*100:+.2f}%",
            "FracDiff (d=0.30)": f"{row_fd:+.4f}",
        })

    df_sample = pd.DataFrame(sample_rows)
    print(df_sample.to_string(index=False))


if __name__ == "__main__":
    extract_samples()
