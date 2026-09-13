"""test_pipeline/f1xx_enrichment/test_regime_bootstrap_suite.py

Pytest suite validating Step 6: Regime-Conditional Partitioning & Clustered Bootstrap Invariants.
Invariants:
1. Exhaustive and mutually exclusive regime classification.
2. Bear Market Rebound Effect: Mean return in Bear regime > Bull regime.
3. Clustered Bootstrap Variance Expansion: Clustered CI width is > 1.5x wider than I.I.D. CI width.
4. Positive Edge Persistence: P(Sharpe <= 0) < 0.05 under both I.I.D. and Clustered Bootstrap.
"""
from __future__ import annotations

import json
import os
import pytest

REPORT_JSON = "test_pipeline/out/regime_bootstrap_report.json"


@pytest.fixture(scope="module")
def audit_report():
    assert os.path.exists(REPORT_JSON), f"Audit report not found at {REPORT_JSON}"
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_regime_partitioning_exhaustiveness(audit_report):
    """Invariant 1: Regimes cover 100% of negative events without overlap."""
    regimes = audit_report["regime_breakdown"]
    total_events = audit_report["total_negative_events"]
    
    sum_events = sum(regimes[r]["n_events"] for r in ["BULL", "BEAR", "SIDEWAYS", "CRISIS_HIGH_VOL"])
    assert sum_events == total_events, f"Sum of events ({sum_events}) does not match total ({total_events})"


def test_bear_market_rebound_effect(audit_report):
    """Invariant 2: In Bear regimes, oversold bounce-back yields higher mean return and win-rate than Bull."""
    regimes = audit_report["regime_breakdown"]
    mean_bear = regimes["BEAR"]["mean_return_pct"]
    mean_bull = regimes["BULL"]["mean_return_pct"]
    wr_bear = regimes["BEAR"]["win_rate_pct"]
    wr_bull = regimes["BULL"]["win_rate_pct"]
    
    assert mean_bear > mean_bull, f"Expected Bear mean ({mean_bear}%) > Bull mean ({mean_bull}%)"
    assert wr_bear > wr_bull, f"Expected Bear win-rate ({wr_bear}%) > Bull win-rate ({wr_bull}%)"


def test_clustered_bootstrap_variance_expansion(audit_report):
    """Invariant 3: Clustered bootstrap confidence interval is strictly wider (>1.5x) than I.I.D. bootstrap."""
    audit = audit_report["bootstrap_audit"]
    expansion_factor = audit["ci_expansion_factor"]
    width_iid = audit["iid_bootstrap"]["mean_ci_width"]
    width_clustered = audit["clustered_block_bootstrap"]["mean_ci_width"]
    
    assert width_clustered > width_iid, "Clustered CI must be wider than I.I.D. CI"
    assert expansion_factor >= 1.50, f"Expected CI expansion factor >= 1.5x, got {expansion_factor}x"


def test_positive_edge_persistence_under_clustering(audit_report):
    """Invariant 4: Strategy retains positive statistical edge: P(Sharpe <= 0) < 5% in Clustered Bootstrap."""
    audit = audit_report["bootstrap_audit"]
    prob_loss_iid = audit["iid_bootstrap"]["prob_sharpe_le_zero_pct"]
    prob_loss_clustered = audit["clustered_block_bootstrap"]["prob_sharpe_le_zero_pct"]
    
    assert prob_loss_iid < 5.0, f"Expected I.I.D. P(Sharpe <= 0) < 5%, got {prob_loss_iid}%"
    assert prob_loss_clustered < 5.0, f"Expected Clustered P(Sharpe <= 0) < 5%, got {prob_loss_clustered}%"
