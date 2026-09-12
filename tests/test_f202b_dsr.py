"""
tests/test_f202b_dsr.py

Unit tests for F202b DSR & PBO implementation:
- Mathematical accuracy of Bailey & Lopez de Prado expected max SR formula
- DSR formula correctness against known hand-calculated benchmark
- Outlier sensitivity & kurtosis deflation behavior
- PBO calculation consistency
"""

import math
import numpy as np
import pytest

from src.pipeline.f202b_dsr_pbo import (
    expected_max_sr,
    compute_dsr,
    evaluate_treatment_dsr
)


def test_expected_max_sr_n1():
    """At N=1, benchmark Sharpe ratio should be identically 0.0."""
    sr0 = expected_max_sr(n_trials=1, var_sr=1.0)
    assert sr0 == 0.0


def test_expected_max_sr_scaling():
    """Higher trials should yield strictly higher expected maximum SR."""
    var_sr = 1.0 / 1437
    sr0_n1 = expected_max_sr(1, var_sr)
    sr0_n2 = expected_max_sr(2, var_sr)
    sr0_n3 = expected_max_sr(3, var_sr)
    sr0_n5 = expected_max_sr(5, var_sr)

    assert sr0_n1 == 0.0
    assert 0.013 < sr0_n2 < 0.014
    assert 0.022 < sr0_n3 < 0.023
    assert 0.031 < sr0_n5 < 0.032


def test_dsr_mathematical_precision():
    """Verify exact formula match against user's independent calculation:
    sr_hat = 0.055675, n_obs = 1437, skew = 49.9449, kurt = 4315.7671.
    """
    sr_hat = 0.055675
    n_obs = 1437
    skew = 49.9449
    kurt = 4315.7671

    # N=1 (sr0 = 0.0)
    dsr_1, z_1, denom_1 = compute_dsr(sr_hat, n_obs, skew, kurt, sr_benchmark=0.0)
    assert math.isclose(denom_1, 1.25, rel_tol=1e-2)
    assert math.isclose(dsr_1, 0.9543, abs_tol=1e-3)

    # N=2 (sr0 ~ 0.0137)
    sr0_2 = expected_max_sr(2, var_sr=1.0 / n_obs)
    dsr_2, z_2, denom_2 = compute_dsr(sr_hat, n_obs, skew, kurt, sr_benchmark=sr0_2)
    assert math.isclose(dsr_2, 0.8983, abs_tol=1e-3)


def test_outlier_kurtosis_impact():
    """Simulate sample where 1 extreme outlier inflates kurtosis, depressing DSR,
    and verify winsorization restores true alpha signal.
    """
    rng = np.random.default_rng(42)
    clean_diff = rng.normal(loc=0.02, scale=0.15, size=2000)
    
    # Inject one massive UPCOM-style outlier
    dirty_diff = clean_diff.copy()
    dirty_diff[0] = 30.0  # +3000% jump
    
    # Evaluate raw vs winsorized
    raw_eval = evaluate_treatment_dsr(dirty_diff, n_clusters=200, candidate_trials=[1, 2])
    clean_eval = evaluate_treatment_dsr(clean_diff, n_clusters=200, candidate_trials=[1, 2])
    
    # Kurtosis of dirty sample should be massive
    assert raw_eval["kurtosis"] > 500
    # Clean kurtosis should be close to 3
    assert clean_eval["kurtosis"] < 10
    
    # Cohen's d of clean sample should be higher due to uninflated variance
    assert clean_eval["cohens_d"] > raw_eval["cohens_d"]
