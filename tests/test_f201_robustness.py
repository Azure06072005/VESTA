"""Unit tests for src/pipeline/f201_robustness_check.py."""
import math
import numpy as np
import pandas as pd
import pytest

from src.pipeline.f201_robustness_check import (
    classify_negative_from_headline,
    naive_paired_test,
    cluster_bootstrap,
    regime_heterogeneity_flag,
    regime_breakdown,
)

def test_classify_negative_from_headline():
    assert classify_negative_from_headline("Thua lỗ nặng nề và bị phạt vi phạm") is True
    assert classify_negative_from_headline("Lợi nhuận tăng trưởng kỷ lục") is False
    assert classify_negative_from_headline("") is False
    assert classify_negative_from_headline(None) is False

def test_naive_paired_test_calculation():
    # diff = return_t30 - return_t5
    diffs = np.array([0.02, 0.04, 0.01, 0.03, 0.05])
    res = naive_paired_test(diffs)
    assert res["n"] == 5
    assert math.isclose(res["mean_diff"], 0.03, rel_tol=1e-5)
    assert res["se_naive"] > 0
    assert res["t_naive"] > 0
    assert 0 <= res["p_naive"] <= 1.0
    assert res["cohens_d"] > 0

def test_cluster_bootstrap_symbol():
    # 10 clusters (symbols), each with 20 events with positive reversion diff
    rng = np.random.default_rng(42)
    records = []
    for s in range(10):
        sym = f"SYM{s}"
        for _ in range(20):
            records.append({
                "symbol": sym,
                "diff": rng.normal(0.02, 0.005),
                "published_at": pd.Timestamp("2023-01-01"),
                "month": "2023-01"
            })
    df = pd.DataFrame(records)
    res = cluster_bootstrap(df, "symbol", n_boot=200, seed=42)
    assert res["n_clusters"] == 10
    assert res["n_events"] == 200
    assert res["ci_excludes_zero"] is True
    assert res["p_cluster"] < 0.01

def test_regime_heterogeneity_sign_flip():
    regimes = [
        {"regime": "rally_regime", "scope": "BOTH", "naive": {"mean_diff": 0.03}},
        {"regime": "crisis_regime", "scope": "BOTH", "naive": {"mean_diff": -0.04}},
    ]
    res = regime_heterogeneity_flag(regimes)
    assert res["sign_flip_detected"] is True

def test_regime_heterogeneity_no_sign_flip():
    regimes = [
        {"regime": "rally_regime_1", "scope": "BOTH", "naive": {"mean_diff": 0.03}},
        {"regime": "rally_regime_2", "scope": "BOTH", "naive": {"mean_diff": 0.01}},
    ]
    res = regime_heterogeneity_flag(regimes)
    assert res["sign_flip_detected"] is False
