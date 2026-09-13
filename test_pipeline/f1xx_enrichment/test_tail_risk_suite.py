"""test_pipeline/f1xx_enrichment/test_tail_risk_suite.py

Pytest suite validating 2. Tail Risk & Outlier Sanitization Invariants in test_pipeline.
Invariants:
1. Winsorization [0.5%, 99.5%] collapses excess kurtosis below 15.0 (financial benchmark).
2. XDC outlier isolation: removing XDC reduces raw kurtosis by >= 90%.
3. HOSE main board partition exhibits natural structural kurtosis (< 25.0) without UPCOM penny distortions.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest
import scipy.stats as stats

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline

DB_PATH = "db/test_db/vesta_test.duckdb"

@pytest.fixture(scope="module")
def negative_events_diff():
    con = duckdb.connect(DB_PATH, read_only=True)
    q = """
    SELECT 
        p.symbol,
        p.headline,
        (p.price_t30 - p.price_at_publish)/p.price_at_publish - (p.price_t5 - p.price_at_publish)/p.price_at_publish as diff,
        s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
    """
    df = con.execute(q).df()
    con.close()
    
    # Filter for negative sentiment events (as defined in F201 / F202b event study)
    df["sentiment_score"] = df["headline"].apply(score_headline)
    df_neg = df[df["sentiment_score"] < 0].dropna(subset=["diff"]).copy()
    return df_neg


def test_raw_distribution_exhibits_extreme_kurtosis(negative_events_diff):
    """Invariant: Raw distribution confirms extreme tail risk (> 1,000 kurtosis)."""
    kurt = stats.kurtosis(negative_events_diff["diff"], bias=False)
    assert kurt > 1000.0, f"Expected extreme fat-tail kurtosis, got {kurt}"


def test_xdc_isolation_reduces_kurtosis_by_over_90_pct(negative_events_diff):
    """Invariant: Isolating XDC collapses >90% of excess kurtosis."""
    raw_kurt = stats.kurtosis(negative_events_diff["diff"], bias=False)
    no_xdc = negative_events_diff[negative_events_diff["symbol"] != "XDC"]["diff"]
    no_xdc_kurt = stats.kurtosis(no_xdc, bias=False)
    
    reduction_pct = (raw_kurt - no_xdc_kurt) / raw_kurt * 100
    assert reduction_pct >= 90.0, f"Expected >=90% reduction, got {reduction_pct:.2f}% (from {raw_kurt:.1f} to {no_xdc_kurt:.1f})"


def test_winsorization_collapses_kurtosis_to_normal_range(negative_events_diff):
    """Invariant: Winsorizing at [0.5%, 99.5%] brings kurtosis to standard financial levels (< 15.0)."""
    s = negative_events_diff["diff"]
    low = s.quantile(0.005)
    high = s.quantile(0.995)
    s_win = s.clip(lower=low, upper=high)
    win_kurt = stats.kurtosis(s_win, bias=False)
    assert win_kurt < 15.0, f"Expected winsorized kurtosis < 15.0, got {win_kurt:.2f}"


def test_hose_main_board_isolation_protects_against_penny_distortion(negative_events_diff):
    """Invariant: HOSE main board is naturally free of extreme UPCOM/penny outliers."""
    hose_diff = negative_events_diff[negative_events_diff["exchange"] == "HOSE"]["diff"]
    hose_kurt = stats.kurtosis(hose_diff, bias=False)
    assert hose_kurt < 25.0, f"Expected HOSE raw kurtosis < 25.0, got {hose_kurt:.2f}"
