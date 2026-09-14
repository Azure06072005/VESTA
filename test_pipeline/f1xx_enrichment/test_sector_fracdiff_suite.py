"""test_pipeline/f1xx_enrichment/test_sector_fracdiff_suite.py

Invariant Test Suite for Dynamic Sector-Specific Fractional Differentiation.
Locks in 4 mathematical & financial invariants:
1. Strict Stationarity: Every sector at its d* must achieve ADF p-value <= 0.01.
2. High Memory Retention: Every sector at its d* must preserve Pearson rho >= 0.85.
3. Structural Heterogeneity: Sector d* spread >= 0.15, mathematically disproving uniform d.
4. High-Beta Vulnerability: Banking/Financials at d=0.20 fail p <= 0.01, requiring d* = 0.25.
"""
import os
import sys
import pytest
import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_sector_specific_fracdiff import (
    extract_sector_price_series,
    optimize_sector_d,
    DB_PATH,
)


@pytest.fixture(scope="module")
def sector_data():
    con = duckdb.connect(DB_PATH, read_only=True)
    series_dict = extract_sector_price_series(con)
    con.close()
    
    results = {}
    for name, s in series_dict.items():
        results[name] = optimize_sector_d(s, name)
    return results


def test_strict_stationarity_all_sectors(sector_data):
    """Invariant 1: All sectors at their optimal d* must achieve ADF p-value <= 0.01."""
    for sector_name, res in sector_data.items():
        p_val = res["optimal_p_value"]
        assert p_val <= 0.01, (
            f"Sector '{sector_name}' failed stationarity at d*={res['optimal_d']}: p={p_val}"
        )


def test_memory_retention_all_sectors(sector_data):
    """Invariant 2: Every sector at d* must retain Pearson rho >= 0.85 with raw log-price."""
    for sector_name, res in sector_data.items():
        corr = res["optimal_corr"]
        assert corr >= 0.85, (
            f"Sector '{sector_name}' lost excessive memory at d*={res['optimal_d']}: rho={corr:.4f}"
        )


def test_structural_heterogeneity_proof(sector_data):
    """Invariant 3: Sectors exhibit distinct memory depths; spread(d*) >= 0.15."""
    d_stars = [res["optimal_d"] for res in sector_data.values()]
    spread = max(d_stars) - min(d_stars)
    assert spread >= 0.15, (
        f"Sector d* values are too uniform (spread={spread:.2f} < 0.15), failing heterogeneity proof."
    )


def test_high_beta_banking_vulnerability(sector_data):
    """Invariant 4: Banking & Financials must require d* >= 0.25 to overcome trend persistence."""
    assert sector_data["Ngân hàng"]["optimal_d"] >= 0.25, (
        f"Banking should require d* >= 0.25 due to credit cycle persistence."
    )
    assert sector_data["Tài chính"]["optimal_d"] >= 0.25, (
        f"Financials should require d* >= 0.25 due to market beta persistence."
    )
    # Also verify that defensive sectors achieve stationarity at lower d*
    assert sector_data["Tiện ích Cộng đồng"]["optimal_d"] <= 0.10, (
        f"Utilities should achieve stationarity at d* <= 0.10 due to strong mean-reversion."
    )
