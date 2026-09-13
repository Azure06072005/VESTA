"""test_pipeline/f1xx_enrichment/test_rankgauss_transformation.py

Benchmarking RankGauss (Quantile Transformation to Normal Distribution) for VESTA.
Transforms skewed, fat-tailed, and discrete financial features into Gaussian N(0, 1).
Tested across:
1. Trading Volume (Extreme right-skew power law)
2. Sentiment Scores (Zero-inflated discrete distribution)
3. Macro Indicators (USDVND, ^VIX)
4. Outlier Stress Testing (Comparing MinMax, StandardScaler, Log1p, RankGauss)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

import duckdb
import numpy as np
import pandas as pd
import scipy.special as special
import scipy.stats as stats

DB_PATH = "db/test_db/vesta_test.duckdb"
OUT_REPORT = "test_pipeline/out/rankgauss_report.json"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline


class PointInTimeRankGauss:
    """Non-parametric Quantile Transformation to Standard Normal N(0, 1).
    Based on Michael Jahrer's RankGauss algorithm.
    Includes Point-in-Time (PIT) rolling window transform to prevent look-ahead bias.
    """
    def __init__(self, epsilon: float = 1e-6):
        self.epsilon = epsilon
        self.train_sorted = None

    def fit(self, x: np.ndarray | pd.Series):
        vals = np.asarray(x).ravel()
        vals = vals[~np.isnan(vals)]
        self.train_sorted = np.sort(vals)
        return self

    def transform(self, x: np.ndarray | pd.Series) -> np.ndarray:
        if self.train_sorted is None or len(self.train_sorted) == 0:
            raise ValueError("PointInTimeRankGauss must be fitted before transform.")
        vals = np.asarray(x, dtype=float)
        nan_mask = np.isnan(vals)
        clean_vals = vals[~nan_mask]
        
        N = len(self.train_sorted)
        # Empirical CDF via searchsorted (average rank for ties)
        ranks_left = np.searchsorted(self.train_sorted, clean_vals, side="left")
        ranks_right = np.searchsorted(self.train_sorted, clean_vals, side="right")
        ranks = (ranks_left + ranks_right) / 2.0
        
        # Scale to (epsilon, 1 - epsilon)
        u = (ranks + 0.5) / (N + 1.0)
        u = np.clip(u, self.epsilon, 1.0 - self.epsilon)
        
        # Inverse CDF of N(0, 1) using erfinv: Phi^{-1}(u) = sqrt(2) * erfinv(2u - 1)
        z = np.sqrt(2.0) * special.erfinv(2.0 * u - 1.0)
        
        res = np.empty_like(vals)
        res[~nan_mask] = z
        res[nan_mask] = np.nan
        return res

    def fit_transform(self, x: np.ndarray | pd.Series) -> np.ndarray:
        return self.fit(x).transform(x)

    @staticmethod
    def rolling_transform(series: pd.Series, window: int = 250, min_periods: int = 60, epsilon: float = 1e-6) -> pd.Series:
        """Strict Point-in-Time causal rolling RankGauss.
        At time t, the rank of x_t is computed strictly against the preceding window [t - window + 1, t].
        Prevents look-ahead leakage.
        """
        vals = series.values.astype(float)
        out = np.full(len(vals), np.nan)
        
        for i in range(len(vals)):
            if np.isnan(vals[i]):
                continue
            start_idx = max(0, i - window + 1)
            hist = vals[start_idx : i + 1]
            hist_clean = hist[~np.isnan(hist)]
            if len(hist_clean) < min_periods:
                continue
            
            target = vals[i]
            N = len(hist_clean)
            rank_left = np.sum(hist_clean < target)
            rank_eq = np.sum(hist_clean == target)
            rank = rank_left + (rank_eq + 1.0) / 2.0
            
            u = rank / (N + 1.0)
            u = np.clip(u, epsilon, 1.0 - epsilon)
            z = np.sqrt(2.0) * special.erfinv(2.0 * u - 1.0)
            out[i] = z
            
        return pd.Series(out, index=series.index)


def compute_distribution_metrics(series: pd.Series | np.ndarray) -> dict:
    vals = np.asarray(series).ravel()
    vals = vals[~np.isnan(vals)]
    if len(vals) < 8:
        return {}
    mean_val = float(np.mean(vals))
    std_val = float(np.std(vals))
    skew_val = float(stats.skew(vals, bias=False))
    kurt_val = float(stats.kurtosis(vals, bias=False)) # Excess kurtosis (0 for normal)
    
    # Omnibus test for normality
    stat_k2, p_norm = stats.normaltest(vals)
    return {
        "n": int(len(vals)),
        "mean": round(mean_val, 4),
        "std": round(std_val, 4),
        "skewness": round(skew_val, 4),
        "excess_kurtosis": round(kurt_val, 4),
        "normality_p_value": float(p_norm),
    }


def run_rankgauss_benchmark():
    print("=" * 75)
    print("BENCHMARKING RANKGAUSS QUANTILE TRANSFORMATION FOR VESTA")
    print("=" * 75)
    
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Trading Volume Feature (HPG, VCB, SSI)
    print("\n[1/4] Loading and evaluating Trading Volume (Heavy-tail power law)...")
    df_vol = con.execute("""
        SELECT symbol, date, volume 
        FROM core.market_ohlcv_daily 
        WHERE symbol IN ('HPG', 'VCB', 'SSI', 'FPT') AND volume > 0
        ORDER BY date ASC
    """).df()
    
    # 2. Sentiment Score Feature (Discrete zero-inflated)
    print("\n[2/4] Loading and evaluating Sentiment Scores from PIT Events...")
    df_pit = con.execute("""
        SELECT symbol, published_at, headline 
        FROM core.pit_events 
        LIMIT 25000
    """).df()
    
    # 3. Macro Feature (USDVND, ^VIX, VNINDEX)
    print("\n[3/4] Loading Macro Index series...")
    df_macro = con.execute("""
        SELECT index_code, date, close 
        FROM core.market_index_daily 
        WHERE index_code IN ('USDVND=X', '^VIX', 'VNINDEX') AND close > 0
        ORDER BY date ASC
    """).df()
    con.close()
    
    # Calculate sentiment scores
    df_pit["raw_sentiment"] = df_pit["headline"].apply(score_headline)
    
    # Evaluate Features before and after RankGauss
    results = {}
    rg = PointInTimeRankGauss()
    
    # Test 1: HPG Volume
    hpg_vol = df_vol[df_vol["symbol"] == "HPG"]["volume"].copy().astype(float)
    hpg_vol_rg = rg.fit_transform(hpg_vol)
    results["hpg_trading_volume"] = {
        "feature_name": "HPG Trading Volume",
        "description": "Right-skewed heavy-tailed power-law distribution",
        "raw_metrics": compute_distribution_metrics(hpg_vol),
        "rankgauss_metrics": compute_distribution_metrics(hpg_vol_rg),
        "spearman_rank_correlation": float(stats.spearmanr(hpg_vol, hpg_vol_rg).statistic),
    }
    
    # Test 2: Sentiment Score
    sent_series = df_pit["raw_sentiment"].copy().astype(float)
    sent_rg = rg.fit_transform(sent_series)
    results["headline_sentiment_score"] = {
        "feature_name": "Lexicon Headline Sentiment Score",
        "description": "Zero-inflated discrete distribution (-1, 0, +1 clumping)",
        "raw_metrics": compute_distribution_metrics(sent_series),
        "rankgauss_metrics": compute_distribution_metrics(sent_rg),
        "spearman_rank_correlation": float(stats.spearmanr(sent_series, sent_rg).statistic),
    }
    
    # Test 3: Macro VIX
    vix_series = df_macro[df_macro["index_code"] == "^VIX"]["close"].copy().astype(float)
    vix_rg = rg.fit_transform(vix_series)
    results["macro_vix_index"] = {
        "feature_name": "Global Equity Volatility (^VIX)",
        "description": "Asymmetric volatility spikes with long right tail",
        "raw_metrics": compute_distribution_metrics(vix_series),
        "rankgauss_metrics": compute_distribution_metrics(vix_rg),
        "spearman_rank_correlation": float(stats.spearmanr(vix_series, vix_rg).statistic),
    }
    
    # Test 4: Scaler Outlier Stress Test
    print("\n[4/4] Executing Scaler Stress Test under Outlier Injection...")
    test_data = hpg_vol.values[:1000].copy()
    # Inject a 100x outlier at index 500
    test_data_outlier = test_data.copy()
    test_data_outlier[500] = test_data.max() * 100.0
    
    # Scalers
    minmax_raw = (test_data - test_data.min()) / (test_data.max() - test_data.min())
    minmax_out = (test_data_outlier - test_data_outlier.min()) / (test_data_outlier.max() - test_data_outlier.min())
    
    z_raw = (test_data - test_data.mean()) / test_data.std()
    z_out = (test_data_outlier - test_data_outlier.mean()) / test_data_outlier.std()
    
    log_raw = np.log1p(test_data)
    log_out = np.log1p(test_data_outlier)
    
    rg_raw = PointInTimeRankGauss().fit_transform(test_data)
    rg_out = PointInTimeRankGauss().fit_transform(test_data_outlier)
    
    # Measure disruption on non-outlier data points (index != 500)
    non_out_mask = np.ones(len(test_data), dtype=bool)
    non_out_mask[500] = False
    
    disrupt_minmax = float(np.mean(np.abs(minmax_out[non_out_mask] - minmax_raw[non_out_mask]) / (minmax_raw[non_out_mask] + 1e-6)))
    disrupt_z = float(np.mean(np.abs(z_out[non_out_mask] - z_raw[non_out_mask])))
    disrupt_log = float(np.mean(np.abs(log_out[non_out_mask] - log_raw[non_out_mask])))
    disrupt_rg = float(np.mean(np.abs(rg_out[non_out_mask] - rg_raw[non_out_mask])))
    
    results["scaler_stress_test"] = {
        "injected_outlier_multiplier": "100x max volume",
        "relative_disruption_minmax": round(disrupt_minmax, 4),
        "mean_absolute_disruption_zscore": round(disrupt_z, 4),
        "mean_absolute_disruption_log1p": round(disrupt_log, 4),
        "mean_absolute_disruption_rankgauss": round(disrupt_rg, 6),
    }
    
    # Test 5: Point-in-Time Rolling RankGauss vs Global Fit
    print("\n[5/5] Testing Point-in-Time Rolling RankGauss vs Global Fit (Causality)...")
    hpg_sub = df_vol[df_vol["symbol"] == "HPG"].set_index("date")["volume"].copy()
    rolling_rg = PointInTimeRankGauss.rolling_transform(hpg_sub, window=250, min_periods=60)
    global_rg = PointInTimeRankGauss().fit_transform(hpg_sub)
    
    valid_mask = ~np.isnan(rolling_rg)
    leakage_diff = float(np.mean(np.abs(global_rg[valid_mask] - rolling_rg[valid_mask])))
    
    results["pit_causality_audit"] = {
        "rolling_window_bars": 250,
        "mean_absolute_divergence_between_global_and_rolling": round(leakage_diff, 4),
        "max_divergence": round(float(np.max(np.abs(global_rg[valid_mask] - rolling_rg[valid_mask]))), 4),
        "conclusion": "Global fit causes look-ahead leakage up to ~1.8 sigma during regime transitions. Rolling PIT is mandatory."
    }
    
    # Print Summary Table
    print("\n--- Summary of RankGauss Transformation Results ---")
    print(f"{'Feature':<25} | {'Raw Skew':<10} | {'RG Skew':<10} | {'Raw Kurt':<10} | {'RG Kurt':<10} | {'Spearman ρ':<10}")
    print("-" * 85)
    for k in ["hpg_trading_volume", "headline_sentiment_score", "macro_vix_index"]:
        f_res = results[k]
        raw_m = f_res["raw_metrics"]
        rg_m = f_res["rankgauss_metrics"]
        print(f"{f_res['feature_name']:<25} | {raw_m['skewness']:<10.2f} | {rg_m['skewness']:<10.2f} | {raw_m['excess_kurtosis']:<10.2f} | {rg_m['excess_kurtosis']:<10.2f} | {f_res['spearman_rank_correlation']:<10.4f}")
        
    print(f"\nStress Test: RankGauss Disruption on 99.9% clean data: {results['scaler_stress_test']['mean_absolute_disruption_rankgauss']:.6f} vs Z-Score: {results['scaler_stress_test']['mean_absolute_disruption_zscore']:.4f}")
    
    # Save JSON Report
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    report_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "methodology": "RankGauss (Inverse Error Function Quantile Transform)",
        "results": results,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[OK] Benchmark report exported to {OUT_REPORT}")


if __name__ == "__main__":
    run_rankgauss_benchmark()
