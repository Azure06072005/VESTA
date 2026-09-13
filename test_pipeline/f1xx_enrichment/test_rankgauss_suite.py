"""test_pipeline/f1xx_enrichment/test_rankgauss_suite.py

Pytest suite validating RankGauss Invariants in test_pipeline.
Invariants:
1. Strict Gaussianity on continuous skewed data: |Skewness| < 0.05, |Excess Kurtosis| < 0.10.
2. Exact monotonic rank preservation: Spearman correlation == 1.0000.
3. Outlier immunity: 100x outlier injection disrupts clean 99.9% data by < 0.01 sigma (vs > 0.50 for z-score).
4. Point-in-Time causality: Rolling RankGauss at index t only depends on window [t-W+1, t].
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import scipy.stats as stats

from test_pipeline.f1xx_enrichment.test_rankgauss_transformation import (
    PointInTimeRankGauss,
    compute_distribution_metrics,
)


@pytest.fixture
def skewed_continuous_series():
    """Generates synthetic log-normal continuous financial series (resembling trading volume)."""
    np.random.seed(42)
    # Lognormal distribution: heavily right-skewed
    return np.random.lognormal(mean=5.0, sigma=1.2, size=5000)


def test_strict_gaussianity_on_continuous_data(skewed_continuous_series):
    """Invariant 1: RankGauss transforms heavily skewed continuous data to standard normal N(0, 1)."""
    raw_skew = stats.skew(skewed_continuous_series)
    assert raw_skew > 2.0, f"Expected raw data to be heavily skewed, got {raw_skew:.2f}"
    
    rg = PointInTimeRankGauss()
    transformed = rg.fit_transform(skewed_continuous_series)
    
    metrics = compute_distribution_metrics(transformed)
    assert abs(metrics["mean"]) < 0.02, f"Expected mean ~ 0, got {metrics['mean']}"
    assert abs(metrics["std"] - 1.0) < 0.02, f"Expected std ~ 1, got {metrics['std']}"
    assert abs(metrics["skewness"]) < 0.05, f"Expected skewness ~ 0, got {metrics['skewness']}"
    assert abs(metrics["excess_kurtosis"]) < 0.10, f"Expected excess kurtosis ~ 0, got {metrics['excess_kurtosis']}"


def test_exact_monotonic_rank_preservation(skewed_continuous_series):
    """Invariant 2: Rank order is strictly preserved. Spearman correlation must be 1.0000."""
    rg = PointInTimeRankGauss()
    transformed = rg.fit_transform(skewed_continuous_series)
    
    spearman_rho = stats.spearmanr(skewed_continuous_series, transformed).statistic
    assert np.isclose(spearman_rho, 1.0, atol=1e-5), f"Expected Spearman rho = 1.0, got {spearman_rho}"


def test_outlier_immunity_vs_standard_scaler(skewed_continuous_series):
    """Invariant 3: Outlier injection creates negligible disruption (< 0.01 sigma) on clean data for RankGauss,
    whereas StandardScaler shifts by > 0.50 sigma.
    """
    clean_data = skewed_continuous_series[:1000].copy()
    outlier_data = clean_data.copy()
    outlier_data[500] = clean_data.max() * 100.0  # 100x spike
    
    # 1. Z-Score disruption
    z_clean = (clean_data - clean_data.mean()) / clean_data.std()
    z_out = (outlier_data - outlier_data.mean()) / outlier_data.std()
    mask = np.ones(len(clean_data), dtype=bool)
    mask[500] = False
    z_disrupt = np.mean(np.abs(z_out[mask] - z_clean[mask]))
    
    # 2. RankGauss disruption
    rg = PointInTimeRankGauss()
    rg_clean = rg.fit_transform(clean_data)
    rg_out = PointInTimeRankGauss().fit_transform(outlier_data)
    rg_disrupt = np.mean(np.abs(rg_out[mask] - rg_clean[mask]))
    
    assert z_disrupt > 0.30, f"Expected Z-score to suffer > 0.30 disruption, got {z_disrupt:.4f}"
    assert rg_disrupt < 0.01, f"Expected RankGauss disruption < 0.01, got {rg_disrupt:.6f}"
    assert z_disrupt > 30 * rg_disrupt, f"Expected Z-score disruption to be at least 30x higher than RankGauss"


def test_point_in_time_causality_no_future_leakage():
    """Invariant 4: In rolling PIT RankGauss, changing future values has ZERO effect on past values."""
    np.random.seed(123)
    s1 = pd.Series(np.random.lognormal(size=300))
    s2 = s1.copy()
    # Mutate only the last 50 elements (the future)
    s2.iloc[250:] = s2.iloc[250:] * 50.0
    
    window = 100
    res1 = PointInTimeRankGauss.rolling_transform(s1, window=window, min_periods=30)
    res2 = PointInTimeRankGauss.rolling_transform(s2, window=window, min_periods=30)
    
    # Values before index 250 must be IDENTICAL (zero future leakage)
    past_mask = np.arange(len(s1)) < 250
    valid_past = past_mask & (~np.isnan(res1))
    
    max_diff = np.max(np.abs(res1[valid_past] - res2[valid_past]))
    assert np.isclose(max_diff, 0.0), f"Expected ZERO future leakage in past values, got diff = {max_diff}"
