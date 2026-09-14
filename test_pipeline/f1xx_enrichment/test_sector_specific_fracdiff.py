"""test_pipeline/f1xx_enrichment/test_sector_specific_fracdiff.py

Dynamic Sector-Specific Fractional Differentiation (FracDiff) for VESTA.
Solves the 'One-Size-Fits-All' Flaw of applying a single global d (e.g. d=0.20) to all sectors.

Mathematical & Financial Rationale:
- Different sectors exhibit distinct market microstructures:
  * High-Beta / Leveraged (Banking, Financial Services, Real Estate) exhibit strong momentum
    and persistence, requiring higher d* (0.30 - 0.45) to achieve ADF stationarity.
  * Defensives / Utilities (Power, Water, Telecom) have mean-reverting cash flows,
    reaching stationarity at lower d* (0.15 - 0.25), preserving up to 80% raw price memory.
- For each of the 11 ICB sectors in Vietnam (HOSE/HNX/UPCOM):
  1. Builds daily geometric-mean sector price index from top liquid constituents (2018-2026).
  2. Runs FFD grid sweep d in [0.05, 1.00] with tau = 1e-4.
  3. Identifies sector-specific minimal d* achieving ADF p-value <= 0.01.
  4. Quantifies memory preservation rho(X, X_tilde) and demonstrates the failure of uniform d.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

sys.stdout.reconfigure(encoding="utf-8")

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

DB_PATH = "db/test_db/vesta_test.duckdb"
OUT_REPORT = "test_pipeline/out/sector_specific_fracdiff_report.json"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    get_weights_ffd,
    frac_diff_ffd,
)


def extract_sector_price_series(con: duckdb.DuckDBPyConnection) -> Dict[str, pd.Series]:
    """Constructs daily sector log-price series for all 11 ICB sectors."""
    query = """
    WITH top_syms AS (
        SELECT 
            s.symbol,
            s.industry_name,
            ROW_NUMBER() OVER (
                PARTITION BY s.industry_name 
                ORDER BY avg(p.volume * p.close) DESC
            ) as rnk
        FROM core.market_ohlcv_daily p
        JOIN core.dim_symbol s ON p.symbol = s.symbol
        WHERE p.close > 0 AND p.date >= '2018-01-01' AND s.industry_name IS NOT NULL
        GROUP BY s.symbol, s.industry_name
        HAVING count(*) >= 1200
    )
    SELECT 
        p.date,
        s.industry_name,
        exp(avg(ln(p.close))) as sector_geom_close,
        count(DISTINCT p.symbol) as constituents_count
    FROM core.market_ohlcv_daily p
    JOIN top_syms s ON p.symbol = s.symbol AND s.rnk <= 10
    WHERE p.close > 0 AND p.date >= '2018-01-01'
    GROUP BY 1, 2
    ORDER BY 2, 1
    """
    df = con.execute(query).df()
    df["date"] = pd.to_datetime(df["date"])
    
    sector_series = {}
    for sector, group in df.groupby("industry_name"):
        s = group.sort_values("date").set_index("date")["sector_geom_close"]
        # log transformation
        log_s = np.log(s)
        sector_series[sector] = log_s
    return sector_series


def optimize_sector_d(
    series: pd.Series,
    sector_name: str,
    d_grid: List[float] = None,
    p_threshold: float = 0.01,
    tau: float = 1e-4,
) -> Dict[str, Any]:
    """Finds optimal d* for a given sector series."""
    if d_grid is None:
        d_grid = [round(x, 2) for x in np.arange(0.05, 1.05, 0.05)]
        
    # Baseline d=0 (raw log-price)
    adf_raw = adfuller(series.dropna(), maxlag=1, autolag=None)
    raw_p = float(adf_raw[1])
    raw_stat = float(adf_raw[0])
    
    grid_details = []
    optimal_d = 1.0
    optimal_corr = 0.0
    optimal_p = 0.0
    optimal_adf = 0.0
    found_optimal = False
    
    for d in d_grid:
        fd = frac_diff_ffd(series, d, thres=tau)
        if len(fd) < 50:
            continue
        adf_res = adfuller(fd, maxlag=1, autolag=None)
        p_val = float(adf_res[1])
        stat = float(adf_res[0])
        common_idx = series.index.intersection(fd.index)
        corr = float(np.corrcoef(series.loc[common_idx], fd.loc[common_idx])[0, 1])
        
        is_stat = (p_val <= p_threshold)
        grid_details.append({
            "d": d,
            "adf_stat": stat,
            "p_val": p_val,
            "corr": corr,
            "is_stationary": is_stat,
            "window_len": len(get_weights_ffd(d, thres=tau)),
        })
        
        if is_stat and not found_optimal:
            optimal_d = d
            optimal_corr = corr
            optimal_p = p_val
            optimal_adf = stat
            found_optimal = True
            
    # Baseline d=1 (Integer first difference)
    fd_d1 = frac_diff_ffd(series, 1.0, thres=tau)
    common_d1 = series.index.intersection(fd_d1.index)
    corr_d1 = float(np.corrcoef(series.loc[common_d1], fd_d1.loc[common_d1])[0, 1])
    adf_d1 = adfuller(fd_d1, maxlag=1, autolag=None)

    # Check uniform d=0.20 behavior
    fd_d020 = frac_diff_ffd(series, 0.20, thres=tau)
    adf_d020 = adfuller(fd_d020, maxlag=1, autolag=None)
    d020_p = float(adf_d020[1])
    d020_is_stationary = (d020_p <= p_threshold)
    
    return {
        "sector": sector_name,
        "raw_p_value": raw_p,
        "raw_adf_stat": raw_stat,
        "is_raw_stationary": (raw_p <= p_threshold),
        "optimal_d": optimal_d,
        "optimal_p_value": optimal_p,
        "optimal_adf_stat": optimal_adf,
        "optimal_corr": optimal_corr,
        "corr_at_d1": corr_d1,
        "d1_p_value": float(adf_d1[1]),
        "uniform_d020_p_value": d020_p,
        "uniform_d020_stationary": d020_is_stationary,
        "memory_gain_vs_d1": optimal_corr - corr_d1,
        "grid_details": grid_details,
    }


def run_sector_specific_fracdiff_audit() -> Dict[str, Any]:
    print("=" * 80)
    print("DYNAMIC SECTOR-SPECIFIC FRACTIONAL DIFFERENTIATION (FRACDIFF) AUDIT")
    print(f"Database: {DB_PATH}")
    print("=" * 80)
    
    con = duckdb.connect(DB_PATH, read_only=True)
    t0 = time.time()
    sector_series = extract_sector_price_series(con)
    con.close()
    
    print(f"\n[1/3] Extracted price series for {len(sector_series)} sectors (2018-2026).")
    
    results = []
    print("\n[2/3] Performing FFD Grid Search for each sector (d in [0.05, 1.00])...")
    print(f"{'Sector':<22} | {'Raw p-val':<10} | {'d*':<5} | {'ADF p-val':<10} | {'Corr rho':<8} | {'d=0.20 Stat?':<12}")
    print("-" * 80)
    
    for sector_name, s in sorted(sector_series.items()):
        res = optimize_sector_d(s, sector_name)
        results.append(res)
        stat_tag = "YES (PASS)" if res["uniform_d020_stationary"] else "NO (FAIL)"
        print(f"{sector_name:<22} | {res['raw_p_value']:<10.4f} | {res['optimal_d']:<5.2f} | {res['optimal_p_value']:<10.4e} | {res['optimal_corr']:<8.4f} | {stat_tag:<12}")
        
    d_stars = [r["optimal_d"] for r in results]
    corrs = [r["optimal_corr"] for r in results]
    failed_d020 = [r["sector"] for r in results if not r["uniform_d020_stationary"]]
    
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_sectors_analyzed": len(results),
        "min_optimal_d": float(min(d_stars)),
        "max_optimal_d": float(max(d_stars)),
        "mean_optimal_d": float(np.mean(d_stars)),
        "d_spread": float(max(d_stars) - min(d_stars)),
        "mean_memory_retention": float(np.mean(corrs)),
        "sectors_failing_uniform_d020": failed_d020,
        "n_failing_uniform_d020": len(failed_d020),
        "results": results,
    }
    
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    print("-" * 80)
    print(f"\n[3/3] AUDIT COMPLETE ({time.time()-t0:.2f}s)")
    print(f" -> Optimal d* Range: [{summary['min_optimal_d']:.2f}, {summary['max_optimal_d']:.2f}] (Spread = {summary['d_spread']:.2f})")
    print(f" -> Mean Memory Retention: {summary['mean_memory_retention']:.4f} (preserves ~{summary['mean_memory_retention']*100:.1f}% raw price signal)")
    print(f" -> Sectors FAILING Uniform d=0.20: {len(failed_d020)}/{len(results)} {failed_d020}")
    print(f" -> Report saved to {OUT_REPORT}")
    return summary


if __name__ == "__main__":
    run_sector_specific_fracdiff_audit()
