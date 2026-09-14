"""Unit Test Suite for Module 2: NMAR Missing Data Handling, Distress Imputation & Confidence Gating.

Locks mathematical & financial invariants:
1. Invariant 1: Instrument classification cleanly isolates ETFs, Warrants, Bonds from Common Stocks.
2. Invariant 2: Staleness calculation is exact, non-negative, clamped at 365 days.
3. Invariant 3: ETFs/Warrants/Bonds are flagged is_non_equity=1 and NEVER hallucinate corporate ratios.
4. Invariant 4: Delinquent stocks (> 180d overdue) receive negative financial distress penalty imputation.
5. Invariant 5: Confidence gating smoothly decays with staleness and is strictly 0.0 for Delinquent/Missing/ETF.
6. Invariant 6: Gated feature vector zeroes out untrusted features when confidence weight is 0.
7. Invariant 7: Empirical validation confirms Delinquent stocks have lower win rate and higher volatility than Fresh stocks.
"""
from __future__ import annotations

import json
import pytest
from test_pipeline.f1xx_enrichment.test_nmar_missing_handling import (
    PENALTY_BENCHMARKS,
    classify_instrument_type,
    compute_confidence_weight,
    compute_nmar_imputation,
    extract_ratio_fields,
)


def test_instrument_type_classification_accuracy():
    """Validates structural instrument classification without look-ahead or false positive stocks."""
    cases = [
        ("E1VFVN30", "ETF"),
        ("FUEVFVND", "ETF"),
        ("FUESSV50", "ETF"),
        ("CFPT2301", "WARRANT"),
        ("CHPG2305", "WARRANT"),
        ("CTG123034", "BOND"),
        ("BCG122006", "BOND"),
        ("HPG", "STOCK"),
        ("VNM", "STOCK"),
        ("VCB", "STOCK"),
        ("XDC", "STOCK"),
    ]
    for symbol, expected in cases:
        actual = classify_instrument_type(symbol)
        assert actual == expected, f"Ticker {symbol} classified as {actual} != {expected}"


def test_staleness_calculation_and_delinquency_flag():
    """Validates staleness calculation and delinquency threshold (> 180 days)."""
    # Case A: Fresh report (30 days stale)
    res_fresh = compute_nmar_imputation(
        symbol="HPG",
        event_date="2024-05-30",
        available_at="2024-04-30",
        raw_ratios={"RT_PRT_ROE": 0.18},
    )
    assert res_fresh["staleness_days"] == 30
    assert res_fresh["is_delinquent_flag"] == 0
    assert res_fresh["imputed_ratios"]["imputed_RT_PRT_ROE"] == 0.18

    # Case B: Delinquent report (210 days stale > 180 days)
    res_delinq = compute_nmar_imputation(
        symbol="HPG",
        event_date="2024-11-26",
        available_at="2024-04-30",
        raw_ratios={"RT_PRT_ROE": 0.18},
    )
    assert res_delinq["staleness_days"] == 210
    assert res_delinq["is_delinquent_flag"] == 1
    # Because it is delinquent, must trigger distress penalty (-15%) instead of stale 18%
    assert res_delinq["imputed_ratios"]["imputed_RT_PRT_ROE"] == PENALTY_BENCHMARKS["RT_PRT_ROE"]

    # Case C: Completely missing report (None)
    res_missing = compute_nmar_imputation(
        symbol="VNM",
        event_date="2024-05-30",
        available_at=None,
        raw_ratios={},
    )
    assert res_missing["staleness_days"] == 365
    assert res_missing["is_missing_flag"] == 1
    assert res_missing["is_delinquent_flag"] == 1
    assert res_missing["imputed_ratios"]["imputed_RT_PRT_ROE"] == PENALTY_BENCHMARKS["RT_PRT_ROE"]


def test_etf_fund_warrant_fundamentals_non_hallucination():
    """Validates that ETFs and Warrants do NOT receive common stock median or distress penalties."""
    res_etf = compute_nmar_imputation(
        symbol="E1VFVN30",
        event_date="2024-05-30",
        available_at=None,
        raw_ratios={},
    )
    assert res_etf["instrument_type"] == "ETF"
    assert res_etf["is_non_equity"] == 1
    assert res_etf["is_delinquent_flag"] == 0
    assert res_etf["confidence_weight"] == 0.0
    assert res_etf["imputed_ratios"]["imputed_RT_PRT_ROE"] == 0.0
    assert res_etf["imputed_ratios"]["imputed_RT_LEV_DE"] == 0.0


def test_confidence_score_gating_behavior():
    """Validates exponential decay and strict zero-trust cutoff for confidence weights."""
    # 0 days stale (peak fresh)
    w0 = compute_confidence_weight(0, is_delinquent=0, is_missing=0, is_non_equity=0)
    assert abs(w0 - 1.0) < 1e-4

    # 90 days stale (1 quarter)
    w90 = compute_confidence_weight(90, is_delinquent=0, is_missing=0, is_non_equity=0)
    assert 0.60 < w90 < 0.62

    # 180 days stale (2 quarters, boundary)
    w180 = compute_confidence_weight(180, is_delinquent=0, is_missing=0, is_non_equity=0)
    assert 0.36 < w180 < 0.38

    # Delinquent (> 180 days) -> strictly 0.0
    w_delinq = compute_confidence_weight(200, is_delinquent=1, is_missing=0, is_non_equity=0)
    assert w_delinq == 0.0

    # Missing report -> strictly 0.0
    w_missing = compute_confidence_weight(365, is_delinquent=0, is_missing=1, is_non_equity=0)
    assert w_missing == 0.0

    # ETF -> strictly 0.0
    w_etf = compute_confidence_weight(10, is_delinquent=0, is_missing=0, is_non_equity=1)
    assert w_etf == 0.0


def test_gated_feature_vector_zero_trust_on_delinquent():
    """Validates that gated ratios are zeroed out when confidence weight is 0.0."""
    res_delinq = compute_nmar_imputation(
        symbol="FLC",
        event_date="2023-01-15",
        available_at=None,
        raw_ratios={},
    )
    assert res_delinq["confidence_weight"] == 0.0
    assert res_delinq["imputed_ratios"]["imputed_RT_PRT_ROE"] == -0.15
    # Gated ratio must be 0.0 because confidence is 0
    assert res_delinq["gated_ratios"]["gated_RT_PRT_ROE"] == 0.0


def test_delinquent_win_rate_and_tail_risk_degradation():
    """Validates that empirical report records lower win rate and higher volatility for Delinquent stocks."""
    report_file = "test_pipeline/out/nmar_missing_report.json"
    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = {row["reporting_status"]: row for row in data["stock_reporting_status"]}
    fresh = stats["Fresh (<=90d)"]
    delinq = stats["Delinquent (>180d)"]

    assert delinq["std"] > fresh["std"], f"Delinquent std ({delinq['std']}%) must exceed Fresh std ({fresh['std']}%)"
    assert delinq["win_rate_pct"] < fresh["win_rate_pct"], (
        f"Delinquent win rate ({delinq['win_rate_pct']}%) must be LOWER than Fresh ({fresh['win_rate_pct']}%)!"
    )
    assert delinq["avg_confidence_weight"] == 0.0, "Delinquent average confidence weight must be strictly 0.0!"
