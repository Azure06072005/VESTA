"""test_pipeline/f1xx_enrichment/test_fracdiff_suite.py

Pytest suite validating Fractional Differentiation (FracDiff - FFD) Invariants in test_pipeline.
Invariants:
1. Raw log-price (d=0) is non-stationary (ADF p > 0.05).
2. Integer difference (d=1) is stationary (p < 0.01) but destroys memory (Pearson corr < 0.10).
3. Optimal FracDiff d* achieves stationarity (p < 0.05) while preserving substantial memory (corr >= 0.50).
4. FFD weights property: w_0 = 1, w_k < 0 for all k >= 1 when 0 < d < 1, and |w_k| monotonically decreases.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.stattools import adfuller

from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    get_weights_ffd,
    frac_diff_ffd,
)

DB_PATH = "db/test_db/vesta_test.duckdb"


@pytest.fixture(scope="module")
def vnindex_log_series():
    con = duckdb.connect(DB_PATH, read_only=True)
    q = """
    SELECT date, close 
    FROM core.market_index_daily 
    WHERE index_code = 'VNINDEX' AND close > 0
    ORDER BY date ASC
    """
    df = con.execute(q).df()
    con.close()
    return np.log(df.set_index("date")["close"]).dropna()


def test_ffd_weight_mathematical_invariants():
    """Invariant 4: w_0 = 1, w_k < 0 for all k >= 1 for 0 < d < 1, monotonically decreasing."""
    d = 0.35
    w_rev = get_weights_ffd(d, thres=1e-4)
    # w_rev is reversed for convolution, so w_0 is w_rev[-1]
    w = w_rev[::-1]
    
    assert np.isclose(w[0], 1.0), f"Expected w_0 = 1, got {w[0]}"
    assert np.all(w[1:] < 0), "Expected all weights w_k < 0 for k >= 1 when 0 < d < 1"
    
    abs_weights = np.abs(w)
    # Monotonically decreasing
    diffs = np.diff(abs_weights)
    assert np.all(diffs <= 0), "Expected monotonic decrease in absolute weight magnitudes"


def test_raw_log_price_is_non_stationary(vnindex_log_series):
    """Invariant 1: Raw log price series fails ADF stationarity test at 95% confidence."""
    adf_res = adfuller(vnindex_log_series, autolag="AIC")
    p_val = adf_res[1]
    assert p_val > 0.05, f"Expected non-stationary log price (p > 0.05), got p = {p_val:.4f}"


def test_integer_difference_destroys_memory(vnindex_log_series):
    """Invariant 2: d=1 is stationary, but Pearson correlation with price level drops below 0.10."""
    diff1 = frac_diff_ffd(vnindex_log_series, d=1.0)
    clean = pd.DataFrame({"raw": vnindex_log_series, "diff1": diff1}).dropna()
    
    adf_res = adfuller(clean["diff1"], autolag="AIC")
    p_val = adf_res[1]
    corr = clean["raw"].corr(clean["diff1"], method="pearson")
    
    assert p_val < 0.01, f"Expected d=1 to be stationary (p < 0.01), got {p_val}"
    assert abs(corr) < 0.10, f"Expected d=1 to destroy memory (|corr| < 0.10), got {corr:.4f}"


def test_optimal_fracdiff_balances_stationarity_and_memory(vnindex_log_series):
    """Invariant 3: Optimal d* (e.g. d=0.20 or 0.30) achieves p < 0.01 AND preserves Pearson corr >= 0.50."""
    # Test at d=0.20 (stationary at 99% for VNINDEX)
    diff_opt = frac_diff_ffd(vnindex_log_series, d=0.20)
    clean = pd.DataFrame({"raw": vnindex_log_series, "diff_opt": diff_opt}).dropna()
    
    adf_res = adfuller(clean["diff_opt"], autolag="AIC")
    p_val = adf_res[1]
    corr = clean["raw"].corr(clean["diff_opt"], method="pearson")
    
    assert p_val < 0.01, f"Expected d=0.20 to achieve stationarity (p < 0.01), got {p_val:.4f}"
    assert corr >= 0.50, f"Expected d=0.20 to retain high memory (corr >= 0.50), got {corr:.4f}"
