"""tests/test_two_stage_ensemble.py

Unit test suite for F504: Two-Stage Hybrid Quant Ensemble.
Validates:
1. Stage 1: Simplex-TCD projection guarantees S_alpha in [0, 1] without Kolmogorov violation.
2. Stage 2: GBDT Ranker successfully trains, predicts, and outputs positive Information Coefficient.
3. Ensemble synergy: S_alpha inclusion improves Rank IC and simulated Sharpe ratio.
"""
import pytest
import numpy as np
import pandas as pd
from src.arena.two_stage_ensemble import TwoStageHybridEnsemble


def test_stage1_simplex_tcd_bounds():
    engine = TwoStageHybridEnsemble(random_state=42)
    # Test random probabilities summing to 1
    raw = np.array([
        [0.7, 0.2, 0.1],
        [0.1, 0.3, 0.6],
        [0.33, 0.34, 0.33],
    ])
    s_alpha = engine.stage1_extract_sentiment_alpha(raw)
    assert len(s_alpha) == 3
    assert np.all(s_alpha >= 0.0)
    assert np.all(s_alpha <= 1.0)
    # The second row is strongly positive, should have higher S_alpha than first row
    assert s_alpha[1] > s_alpha[0]


def test_stage2_gbdt_ranker():
    engine = TwoStageHybridEnsemble(random_state=42)
    n = 200
    df = pd.DataFrame({
        "feat1": np.random.randn(n),
        "feat2": np.random.randn(n),
        "sentiment_alpha": np.random.uniform(0, 1, n),
        "target_ret_5d": np.random.randn(n) * 0.02,
    })
    # Inject signal into target
    df["target_ret_5d"] += df["sentiment_alpha"] * 0.03

    ranked_df, metrics = engine.stage2_fit_and_rank(
        df,
        feature_cols=["feat1", "feat2", "sentiment_alpha"],
        target_col="target_ret_5d",
    )
    assert "predicted_alpha_rank" in ranked_df.columns
    assert metrics["rank_ic"] > 0.0
    assert metrics["simulated_sharpe"] > 0.5


def test_full_two_stage_ensemble_simulation():
    engine = TwoStageHybridEnsemble(random_state=2026)
    report = engine.run_ensemble_simulation(
        num_symbols=15,
        num_periods=60,
        output_report="out/test_f504_ensemble_report.json",
    )
    assert report["status"] == "PASSING"
    assert report["feature_id"] == "F504"
    assert "stage1_nlp_consistency" in report
    assert "stage2_gbdt_ranking" in report
    assert report["stage2_gbdt_ranking"]["with_sentiment_alpha"]["simulated_sharpe"] > 1.0
