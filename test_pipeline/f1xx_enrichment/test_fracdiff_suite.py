"""Unit Test Suite for Module 3: Fractional Differentiation (FracDiff FFD).

Locks mathematical & financial invariants:
1. Invariant 1: Binomial weights obey exact recursive formulation: w_0 = 1, w_1 = -d, alternating decay.
2. Invariant 2: FFD window truncation correctly clips weights at threshold tau = 1e-4.
3. Invariant 3: d = 1.0 exactly reproduces 1st order lag difference (standard log return).
4. Invariant 4: Fractional differentiation at optimal d* passes ADF stationarity test (p-value <= 0.01).
5. Invariant 5: Optimal d* preserves significantly higher memory correlation than integer differencing (r(d*) >> r(1.0)).
6. Invariant 6: Causal convolution strictly avoids look-ahead (future prices do not alter current values).
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.stattools import adfuller

from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    evaluate_fracdiff_grid,
    frac_diff_ffd,
    get_weights_ffd,
)


def test_weights_generation_binomial_properties():
    """Validates recursive binomial expansion weights for fractional and integer d."""
    # Case A: Integer d = 1.0 (Standard differencing kernel: [ 1.0, -1.0 ])
    w_d1 = get_weights_ffd(1.0, thres=1e-5)
    assert len(w_d1) == 2
    assert np.isclose(w_d1[0], 1.0)
    assert np.isclose(w_d1[1], -1.0)
    assert np.isclose(np.sum(w_d1), 0.0)

    # Case B: Fractional d = 0.35
    w_d035 = get_weights_ffd(0.35, thres=1e-4)
    # w[0] is w_0 = 1.0
    assert np.isclose(w_d035[0], 1.0)
    # w[1] is w_1 = -d = -0.35
    assert np.isclose(w_d035[1], -0.35)
    # Weights decay in absolute magnitude
    abs_weights = np.abs(w_d035)
    assert np.all(np.diff(abs_weights) <= 0)


def test_ffd_window_truncation_preserves_memory_boundary():
    """Validates that all truncated weights are strictly smaller than threshold tau."""
    thres = 1e-4
    w = get_weights_ffd(0.4, thres=thres)
    # Oldest weight included is at w[-1]
    oldest_w = w[-1]
    assert abs(oldest_w) >= thres or len(w) == 2000
    # Next theoretical weight must be < threshold
    k = len(w)
    next_w = abs(oldest_w * (0.4 - k + 1) / k)
    assert next_w < thres


def test_integer_differencing_reproduces_standard_returns():
    """Validates that d = 1.0 on log prices perfectly matches standard diff: ln(P_t) - ln(P_{t-1})."""
    np.random.seed(42)
    prices = 100.0 * np.exp(np.cumsum(np.random.normal(0, 0.02, 100)))
    log_p = pd.Series(np.log(prices))

    fd_1 = frac_diff_ffd(log_p, d=1.0, thres=1e-5)
    standard_diff = log_p.diff().dropna()

    assert len(fd_1) == len(standard_diff)
    assert np.allclose(fd_1.values, standard_diff.values, atol=1e-10)


def test_fracdiff_stationarity_achievement():
    """Validates that synthetic random walk (I(1)) becomes stationary (p < 0.01) under fractional diff."""
    np.random.seed(12345)
    # Generate geometric Brownian motion (unit root process)
    n = 2000
    rw = np.cumsum(np.random.normal(0, 1.0, n))
    s_rw = pd.Series(rw)

    # Raw series must fail stationarity
    adf_raw = adfuller(s_rw, maxlag=1, autolag=None)
    assert adf_raw[1] > 0.10, f"Raw random walk should be non-stationary, got p = {adf_raw[1]}"

    # FracDiff at d = 0.40 must pass stationarity
    fd_040 = frac_diff_ffd(s_rw, d=0.40, thres=1e-4)
    adf_fd = adfuller(fd_040, maxlag=1, autolag=None)
    assert adf_fd[1] < 0.01, f"FracDiff at d=0.40 must be stationary (p < 0.01), got p = {adf_fd[1]}"


def test_fracdiff_memory_preservation_over_integer_diff():
    """Validates that d* preserves significantly higher memory correlation with raw prices than d = 1.0."""
    np.random.seed(42)
    t = np.linspace(0, 20, 1500)
    # Trend + cyclical drift + random walk
    trend = 0.5 * t + 2.0 * np.sin(t)
    rw = trend + np.cumsum(np.random.normal(0, 0.5, len(t)))
    series = pd.Series(rw)

    fd_dstar = frac_diff_ffd(series, d=0.35, thres=1e-4)
    fd_d1 = frac_diff_ffd(series, d=1.0, thres=1e-4)

    corr_dstar = np.corrcoef(series.loc[fd_dstar.index], fd_dstar)[0, 1]
    corr_d1 = np.corrcoef(series.loc[fd_d1.index], fd_d1)[0, 1]

    # Memory retention of d* should be much higher than d=1.0 (difference > 0.50)
    assert corr_dstar > 0.70, f"Expected high memory correlation for d=0.35, got {corr_dstar:.4f}"
    assert corr_dstar - corr_d1 > 0.50, (
        f"Memory retention of d=0.35 ({corr_dstar:.4f}) should dominate d=1.0 ({corr_d1:.4f}) by > 0.50"
    )


def test_no_lookahead_causal_convolution():
    """Validates that modifying future prices does not alter current fractional differentiated values."""
    series = pd.Series(np.linspace(10, 50, 100))
    fd_orig = frac_diff_ffd(series, d=0.35, thres=1e-4)

    # Create mutated series where points after index 70 are replaced with wild outliers
    series_mutated = series.copy()
    series_mutated.iloc[70:] = series_mutated.iloc[70:] * 50.0

    fd_mutated = frac_diff_ffd(series_mutated, d=0.35, thres=1e-4)

    # Values strictly before index 70 must be IDENTICAL (zero look-ahead leakage)
    cutoff_idx = series.index[69]
    orig_prefix = fd_orig.loc[:cutoff_idx]
    mutated_prefix = fd_mutated.loc[:cutoff_idx]

    assert np.allclose(orig_prefix.values, mutated_prefix.values, atol=1e-12), (
        "Lookahead bias detected! Future prices altered historical fractional values."
    )
