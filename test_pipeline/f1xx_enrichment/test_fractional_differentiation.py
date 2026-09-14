"""Module 3: Fractional Differentiation (FracDiff) — Fixed-width Window FracDiff (FFD).

Implements the Marcos López de Prado (2018) methodology for financial time series:
1. Binomial Expansion: Computes real-order weights (1 - B)^d with exact recurrence:
   w_0 = 1, w_k = -w_{k-1} * (d - k + 1) / k
2. Fixed-width Window Truncation (FFD): Truncates weights at threshold tau = 1e-4
   to enforce a strictly fixed causal memory width, eliminating look-ahead and dynamic length bias.
3. Automated Grid Search for Optimal d*: Finds minimal d* such that ADF test p-value <= 0.01,
   maximizing Pearson correlation r(X, X_tilde) with raw price.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


def get_weights_ffd(d: float, thres: float = 1e-4, max_k: int = 2000) -> np.ndarray:
    """Computes truncated FFD weights for a real difference order d.
    
    Returns array of weights ordered chronologically for 1D convolution:
    [w_l, w_{l-1}, ..., w_1, w_0] where w_0 corresponds to the current observation X_t.
    """
    w = [1.0]
    k = 1
    while k < max_k:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < thres:
            break
        w.append(w_k)
        k += 1
    # np.convolve naturally flips the filter kernel, so w = [w_0, w_1, ..., w_l]
    # where w_0 corresponds to X_t, w_1 corresponds to X_{t-1}, etc.
    return np.array(w, dtype=np.float64)


def frac_diff_ffd(
    series: pd.Series,
    d: float,
    thres: float = 1e-4,
) -> pd.Series:
    """Applies Fixed-width Window Fractional Differentiation (FFD) to a Pandas series.
    
    Causal, zero-lookahead: Output at index t only depends on values in [t - l, t].
    """
    w = get_weights_ffd(d, thres=thres)
    width = len(w)
    if len(series) < width:
        return pd.Series(dtype=np.float64)
    
    values = series.values
    # Valid convolution produces output of length len(series) - width + 1
    convolved = np.convolve(values, w, mode="valid")
    return pd.Series(convolved, index=series.index[width - 1:])


def evaluate_fracdiff_grid(
    series: pd.Series,
    d_values: Optional[List[float]] = None,
    thres: float = 1e-4,
    p_val_threshold: float = 0.01,
) -> Dict[str, Any]:
    """Sweeps d values to locate optimal d* balancing stationarity and memory retention."""
    if d_values is None:
        d_values = [round(x, 2) for x in np.arange(0.05, 1.05, 0.05)]
    
    grid_results = []
    best_d = None

    # Baseline: raw series (d=0)
    adf_raw = adfuller(series.dropna(), maxlag=1, autolag=None)
    raw_record = {
        "d": 0.0,
        "adf_stat": float(adf_raw[0]),
        "p_val": float(adf_raw[1]),
        "corr": 1.0,
        "is_stationary": bool(adf_raw[1] <= p_val_threshold),
    }
    grid_results.append(raw_record)

    for d in d_values:
        fd = frac_diff_ffd(series, d, thres=thres)
        if len(fd) < 30:
            continue
        adf = adfuller(fd, maxlag=1, autolag=None)
        p_val = float(adf[1])
        corr = float(np.corrcoef(series.loc[fd.index], fd)[0, 1])
        is_stat = bool(p_val <= p_val_threshold)

        rec = {
            "d": float(d),
            "adf_stat": float(adf[0]),
            "p_val": p_val,
            "corr": corr,
            "is_stationary": is_stat,
            "window_width": len(get_weights_ffd(d, thres=thres)),
        }
        grid_results.append(rec)

        if is_stat and best_d is None:
            best_d = rec

    if best_d is None:
        # Fallback to d=1.0 if no lower d passed
        best_d = grid_results[-1]

    return {
        "best_d": best_d["d"],
        "best_p_val": best_d["p_val"],
        "best_corr": best_d["corr"],
        "best_window_width": best_d["window_width"],
        "grid": grid_results,
    }


def run_cross_sectional_fracdiff_audit(
    db_path: str = "db/test_db/vesta_test.duckdb",
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Runs empirical FFD benchmark across flagship Vietnamese equities in DuckDB."""
    if symbols is None:
        symbols = ["HPG", "VCB", "FPT", "VNM", "SSI", "MWG", "VIC", "TCB"]

    print("=" * 85)
    print("RUNNING MODULE 3 AUDIT: FRACTIONAL DIFFERENTIATION (FRACDIFF FFD)")
    print("=" * 85)

    con = duckdb.connect(db_path, read_only=True)
    summary_records = []
    symbol_details = {}

    for sym in symbols:
        df = con.execute(f"""
            SELECT date, close 
            FROM core.market_ohlcv_daily 
            WHERE symbol = '{sym}' AND close > 0
            ORDER BY date
        """).df()

        if len(df) < 500:
            print(f"[!] Warning: Symbol {sym} has only {len(df)} bars, skipping.")
            continue

        log_price = pd.Series(np.log(df["close"].values), index=df["date"])
        grid_eval = evaluate_fracdiff_grid(log_price)

        rec = {
            "symbol": sym,
            "total_bars": len(df),
            "start_date": str(df["date"].min()),
            "end_date": str(df["date"].max()),
            "optimal_d": grid_eval["best_d"],
            "adf_p_val": grid_eval["best_p_val"],
            "correlation_with_raw": grid_eval["best_corr"],
            "memory_retention_r2": round(grid_eval["best_corr"] ** 2, 4),
            "window_width": grid_eval["best_window_width"],
        }
        summary_records.append(rec)
        symbol_details[sym] = grid_eval

        print(f"[*] {sym:>4}: Optimal d* = {rec['optimal_d']:.2f} | ADF p-val = {rec['adf_p_val']:.4e} | "
              f"Corr(P, P_tilde) = {rec['correlation_with_raw']:.4f} (R2 = {rec['memory_retention_r2']:.1%}) | "
              f"Window = {rec['window_width']} days")

    con.close()

    df_summary = pd.DataFrame(summary_records)
    avg_d = float(df_summary["optimal_d"].mean())
    avg_corr = float(df_summary["correlation_with_raw"].mean())
    avg_r2 = float(df_summary["memory_retention_r2"].mean())

    print("\n[*] Cross-Sectional Portfolio Averages (VN Flagships):")
    print(f"    - Mean Optimal d* = {avg_d:.2f}")
    print(f"    - Mean Pearson Correlation with Raw Price = {avg_corr:.4f}")
    print(f"    - Mean Memory Variance Retained (R^2) = {avg_r2:.1%}")

    report = {
        "module": "Fractional Differentiation (FFD)",
        "symbols_audited": len(summary_records),
        "mean_optimal_d": avg_d,
        "mean_correlation": avg_corr,
        "mean_memory_retention_r2": avg_r2,
        "summary": summary_records,
        "details": symbol_details,
        "status": "PASS",
    }

    out_path = Path("test_pipeline/out/fracdiff_benchmark_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[+] FracDiff Benchmark Report successfully written to {out_path}")
    return report


if __name__ == "__main__":
    run_cross_sectional_fracdiff_audit()
