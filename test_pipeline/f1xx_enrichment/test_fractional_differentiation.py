"""test_pipeline/f1xx_enrichment/test_fractional_differentiation.py

Benchmarking Fractional Differentiation (FracDiff - FFD) for VESTA Time Series.
Evaluates the optimal degree of differentiation d* that balances stationarity
(ADF test p < 0.05) with memory preservation (Pearson & Spearman correlation with log-price).
Tested on VNINDEX and VN30 liquid assets against db/test_db/vesta_test.duckdb.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

DB_PATH = "db/test_db/vesta_test.duckdb"
OUT_REPORT = "test_pipeline/out/fractional_differentiation_report.json"


def get_weights_ffd(d: float, thres: float = 1e-4, max_l: int = 10000) -> np.ndarray:
    """Computes weights for Fixed-Width Window Fractional Differentiation (FFD).
    w_0 = 1, w_k = -w_{k-1} / k * (d - k + 1)
    Drops weights where |w_k| < thres.
    Returns reversed weights array for standard convolution.
    """
    if d == 0.0:
        return np.array([1.0])
    w = [1.0]
    k = 1
    while k < max_l:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < thres:
            break
        w.append(w_k)
        k += 1
    return np.array(w[::-1])  # Reversed for convolution


def frac_diff_ffd(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    """Applies Fixed-Width Window Fractional Differentiation (FFD) to a pandas Series.
    Preserves index. Head values before window length are NaN.
    """
    if d == 0.0:
        return series.copy()
    w = get_weights_ffd(d, thres=thres)
    width = len(w)
    if len(series) < width:
        return pd.Series(np.nan, index=series.index)
    
    vals = series.values.astype(float)
    valid_conv = np.convolve(vals, w, mode="valid")
    out = pd.Series(np.nan, index=series.index)
    out.iloc[width - 1 :] = valid_conv
    return out


def evaluate_series_grid(series: pd.Series, asset_name: str, d_range: np.ndarray, thres: float = 1e-4) -> dict:
    """Evaluates ADF stationarity and memory preservation across a grid of d values."""
    log_p = np.log(series).dropna()
    results = []
    
    d_star_95 = None
    d_star_99 = None
    
    for d in d_range:
        d = round(float(d), 3)
        diff_s = frac_diff_ffd(log_p, d=d, thres=thres)
        clean_df = pd.DataFrame({"raw": log_p, "diff": diff_s}).dropna()
        
        if len(clean_df) < 50:
            continue
            
        try:
            adf_res = adfuller(clean_df["diff"], autolag="AIC")
            adf_stat = float(adf_res[0])
            p_val = float(adf_res[1])
            used_lag = int(adf_res[2])
            crit_1 = float(adf_res[4]["1%"])
            crit_5 = float(adf_res[4]["5%"])
            crit_10 = float(adf_res[4]["10%"])
        except Exception as e:
            adf_stat, p_val, used_lag, crit_1, crit_5, crit_10 = np.nan, 1.0, 0, np.nan, np.nan, np.nan
            
        corr_pearson = float(clean_df["raw"].corr(clean_df["diff"], method="pearson"))
        corr_spearman = float(clean_df["raw"].corr(clean_df["diff"], method="spearman"))
        
        is_stationary_95 = (p_val < 0.05)
        is_stationary_99 = (p_val < 0.01)
        
        if is_stationary_95 and d_star_95 is None:
            d_star_95 = d
        if is_stationary_99 and d_star_99 is None:
            d_star_99 = d
            
        w = get_weights_ffd(d, thres=thres)
        memory_window = len(w)
        
        results.append({
            "d": d,
            "memory_window_bars": memory_window,
            "adf_stat": round(adf_stat, 4),
            "p_value": round(p_val, 6),
            "is_stationary_95": is_stationary_95,
            "is_stationary_99": is_stationary_99,
            "corr_pearson": round(corr_pearson, 4),
            "corr_spearman": round(corr_spearman, 4),
            "crit_5pct": round(crit_5, 4),
        })
        
    return {
        "asset": asset_name,
        "n_obs": len(series),
        "d_star_95": d_star_95,
        "d_star_99": d_star_99,
        "grid": results,
    }


def run_benchmark():
    print("=" * 70)
    print("BENCHMARKING FRACTIONAL DIFFERENTIATION (FracDiff FFD) FOR VESTA")
    print("=" * 70)
    
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Fetch VNINDEX
    q_index = """
    SELECT date, close 
    FROM core.market_index_daily 
    WHERE index_code = 'VNINDEX' AND close > 0
    ORDER BY date ASC
    """
    df_vnindex = con.execute(q_index).df()
    df_vnindex.set_index("date", inplace=True)
    vnindex_series = df_vnindex["close"]
    
    # 2. Fetch VN30 liquid candidates
    test_symbols = ["VCB", "FPT", "HPG", "SSI", "VNM", "MWG", "TCB"]
    symbol_series = {}
    for sym in test_symbols:
        q_sym = f"""
        SELECT date, close 
        FROM core.market_ohlcv_daily 
        WHERE symbol = '{sym}' AND close > 0
        ORDER BY date ASC
        """
        df_sym = con.execute(q_sym).df()
        df_sym.set_index("date", inplace=True)
        symbol_series[sym] = df_sym["close"]
        
    con.close()
    
    d_range = np.arange(0.0, 1.05, 0.05)
    
    # Evaluate VNINDEX
    print("\n[1/2] Evaluating VNINDEX across d in [0.0, 1.0]...")
    vnindex_eval = evaluate_series_grid(vnindex_series, "VNINDEX", d_range)
    print(f" -> VNINDEX Optimal d* (95% confidence): {vnindex_eval['d_star_95']}")
    print(f" -> VNINDEX Optimal d** (99% confidence): {vnindex_eval['d_star_99']}")
    
    # Print VNINDEX Grid Table
    print("\n--- VNINDEX FFD Grid Search Summary ---")
    print(f"{'d':<6} | {'Window':<8} | {'ADF Stat':<10} | {'p-value':<10} | {'Stationary?':<12} | {'Pearson Corr':<14} | {'Spearman Corr':<14}")
    print("-" * 84)
    for row in vnindex_eval["grid"]:
        stat_mark = "YES (95%)" if row["is_stationary_95"] else "NO"
        if row["is_stationary_99"]:
            stat_mark = "YES (99%)"
        print(f"{row['d']:<6.2f} | {row['memory_window_bars']:<8} | {row['adf_stat']:<10.4f} | {row['p_value']:<10.6f} | {stat_mark:<12} | {row['corr_pearson']:<14.4f} | {row['corr_spearman']:<14.4f}")
        
    # Evaluate VN30 assets
    print("\n[2/2] Evaluating VN30 Liquid Assets...")
    asset_summaries = []
    for sym, s in symbol_series.items():
        res = evaluate_series_grid(s, sym, d_range)
        # Find metrics at d=0, d=d*, d=1
        d_star = res["d_star_95"]
        grid_dict = {r["d"]: r for r in res["grid"]}
        
        corr_d0 = grid_dict.get(0.0, {}).get("corr_pearson", 1.0)
        corr_dstar = grid_dict.get(d_star, {}).get("corr_pearson", np.nan) if d_star is not None else np.nan
        corr_d1 = grid_dict.get(1.0, {}).get("corr_pearson", np.nan)
        
        p_d0 = grid_dict.get(0.0, {}).get("p_value", np.nan)
        p_dstar = grid_dict.get(d_star, {}).get("p_value", np.nan) if d_star is not None else np.nan
        p_d1 = grid_dict.get(1.0, {}).get("p_value", np.nan)
        
        print(f" -> {sym:<4}: d*={d_star:<4} | Corr(d*)={corr_dstar:<6.4f} vs Corr(d=1)={corr_d1:<6.4f} | Memory Boost: +{(corr_dstar - corr_d1):.4f}")
        
        asset_summaries.append({
            "symbol": sym,
            "n_bars": res["n_obs"],
            "d_star_95": d_star,
            "d_star_99": res["d_star_99"],
            "corr_at_d0": corr_d0,
            "corr_at_dstar": corr_dstar,
            "corr_at_d1": corr_d1,
            "p_val_d0": p_d0,
            "p_val_dstar": p_dstar,
            "p_val_d1": p_d1,
            "detailed_grid": res["grid"],
        })
        
    # Save report
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    report_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "methodology": "Fixed-Width Window Fractional Differentiation (FFD)",
        "threshold": 1e-4,
        "vnindex": vnindex_eval,
        "vn30_assets": asset_summaries,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
        
    print(f"\n[OK] Benchmark report exported to {OUT_REPORT}")


if __name__ == "__main__":
    run_benchmark()
