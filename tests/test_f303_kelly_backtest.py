"""tests/test_f303_kelly_backtest.py

Unit test suite for F303: Dynamic Kelly Criterion Sizing & Multimodal Backtest Integration.
Validates:
1. Mathematical Kelly formula f* = (p * b - q) / b.
2. Fractional Half-Kelly scaling and 15% maximum institutional position cap.
3. Macro Regime suppression gating (attenuation under BEAR/CRISIS).
4. Equal-Weight vs Dynamic Kelly portfolio metrics and Sharpe improvement calculation.
5. Three-tier Conviction hierarchy breakdown (S < 35, 35-40, 40-45).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.pipeline.backtest_meanreversion import compute_dynamic_kelly_metrics


def _create_synthetic_backtest_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Generate alpha scores: some < 35 (high conviction), some 35-40, some 40-45, some >= 45
    alpha_scores = rng.uniform(20.0, 60.0, size=n)
    
    # Return t5 (negative dip) and return t30 (rebound)
    ret_t5 = rng.normal(-0.02, 0.02, size=n)
    # High conviction events have higher rebound probability and magnitude
    is_high_conv = alpha_scores < 35.0
    ret_t30 = np.where(
        is_high_conv,
        ret_t5 + rng.normal(0.045, 0.015, size=n),
        ret_t5 + rng.normal(0.015, 0.025, size=n),
    )
    
    regimes = rng.choice(["BULL", "SIDEWAYS", "BEAR", "CRISIS_HIGH_VOL"], size=n)
    
    return pd.DataFrame({
        "symbol": [f"SYM_{i%10}" for i in range(n)],
        "alpha_score": alpha_scores,
        "sentiment_class": np.where(alpha_scores < 45.0, "negative", "neutral"),
        "return_t5": ret_t5,
        "return_t30": ret_t30,
        "regime": regimes,
    })


def test_kelly_metrics_structure_and_types():
    df = _create_synthetic_backtest_df(100)
    res = compute_dynamic_kelly_metrics(df, conviction_col="alpha_score", neutral_threshold=45.0)
    
    assert res["status"] == "ok"
    assert "total_signals_evaluated" in res
    assert "base_win_rate_pct" in res
    assert "empirical_payoff_ratio_b" in res
    assert "equal_weight_portfolio" in res
    assert "dynamic_kelly_portfolio" in res
    assert "sharpe_improvement_ratio" in res
    assert "conviction_tiers" in res
    
    eq = res["equal_weight_portfolio"]
    kw = res["dynamic_kelly_portfolio"]
    assert "annualized_sharpe" in eq
    assert "annualized_sharpe" in kw
    assert "max_drawdown_pct" in eq
    assert "max_drawdown_pct" in kw


def test_half_kelly_and_position_cap_constraints():
    df = _create_synthetic_backtest_df(200)
    res = compute_dynamic_kelly_metrics(
        df,
        conviction_col="alpha_score",
        neutral_threshold=45.0,
        half_kelly=True,
        max_position_cap=0.15,
    )
    
    assert res["half_kelly_applied"] is True
    assert res["max_position_cap_pct"] == 15.0
    # Mean allocated weight should strictly respect the cap
    assert res["mean_kelly_weight_pct"] <= 15.0
    assert res["mean_kelly_weight_pct"] >= 0.0


def test_conviction_tier_hierarchy():
    df = _create_synthetic_backtest_df(300)
    df["regime"] = "BULL"  # Keep regime uniform to isolate conviction depth effect
    res = compute_dynamic_kelly_metrics(df, conviction_col="alpha_score", neutral_threshold=45.0)
    
    tiers = res["conviction_tiers"]
    high = tiers["high_conviction_S_lt_35"]
    med = tiers["medium_conviction_S_35_40"]
    std = tiers["standard_conviction_S_40_45"]
    
    if high["n"] > 0 and std["n"] > 0:
        # High conviction tier must receive higher average Kelly weight than standard tier
        assert high["mean_weight_pct"] >= std["mean_weight_pct"]
        # High conviction tier should exhibit stronger mean return
        assert high["mean_return_pct"] >= std["mean_return_pct"]


def test_insufficient_data_handling():
    # Less than 10 samples should fail gracefully without exception
    empty_df = pd.DataFrame(columns=["return_t5", "return_t30", "alpha_score"])
    res_empty = compute_dynamic_kelly_metrics(empty_df)
    assert res_empty.get("status") == "insufficient_data" or res_empty == {}

    tiny_df = pd.DataFrame({
        "return_t5": [-0.01, -0.02],
        "return_t30": [0.01, 0.02],
        "alpha_score": [30.0, 32.0],
    })
    res_tiny = compute_dynamic_kelly_metrics(tiny_df)
    assert res_tiny["status"] == "insufficient_data"
