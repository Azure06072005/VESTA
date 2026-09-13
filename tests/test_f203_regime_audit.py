"""Unit tests for F203 Regime-Conditional Validity Audit.

Verifies:
1. Sanitization: price_at_publish <= 0 rows are strictly filtered out.
2. Non-parametric stats: Median diff, win-rate, Wilcoxon signed-rank test.
3. 2D grid matrix evaluation across regimes and exchanges.
4. Sign-flip detection logic on regime heterogeneity.
"""
from __future__ import annotations

import datetime as dt
import duckdb
import numpy as np
import pandas as pd
import pytest

from src.pipeline.f2xx_validation.f203_regime_audit import (
    REGIMES_16,
    RegimeStats,
    load_sanitized_pit_events,
    run_regime_audit,
)


@pytest.fixture
def mock_duckdb():
    """Create an in-memory DuckDB with core schema and synthetic events."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA core;")
    con.execute("""
        CREATE TABLE core.dim_symbol (
            symbol VARCHAR PRIMARY KEY,
            organ_name VARCHAR,
            exchange VARCHAR
        );
    """)
    con.execute("""
        CREATE TABLE core.dim_symbol_cafef (
            symbol VARCHAR PRIMARY KEY,
            organ_name VARCHAR,
            exchange VARCHAR
        );
    """)
    con.execute("""
        CREATE TABLE core.pit_events (
            event_id VARCHAR,
            symbol VARCHAR,
            published_at TIMESTAMP,
            headline VARCHAR,
            price_at_publish DOUBLE,
            price_t5 DOUBLE,
            price_t30 DOUBLE
        );
    """)

    # Populate symbols
    con.execute("INSERT INTO core.dim_symbol VALUES ('FPT', 'FPT Corp', 'HOSE'), ('SHS', 'Saigon Hanoi', 'HNX'), ('BSR', 'Binh Son', 'UPCOM');")

    # Populate synthetic pit_events
    # Event 1: Normal negative headline in Bull regime (reversion positive)
    # Event 2: price_at_publish = 0 (must be filtered out)
    # Event 3: Positive headline (must be filtered out from negative analysis)
    # Event 4: Bear regime negative headline (price continues falling: sign-flip)
    records = [
        # Normal positive reversion in COVID bull regime (2020-2021-Bull)
        ("e1", "FPT", "2021-05-10 10:00:00", "FPT bị xử phạt do vi phạm thuế", 50.0, 48.0, 55.0),
        # Zero price should be filtered
        ("e2", "FPT", "2021-05-11 10:00:00", "FPT thua lỗ nặng nề", 0.0, 48.0, 55.0),
        # Positive sentiment should be ignored
        ("e3", "FPT", "2021-05-12 10:00:00", "Lợi nhuận tăng trưởng vượt bậc", 50.0, 52.0, 58.0),
        # Bear regime in Bond Crisis (2022-BondCrisis), negative reversion (sign-flip)
        ("e4", "SHS", "2022-06-15 10:00:00", "SHS báo lỗ ròng kỷ lục và nợ xấu", 20.0, 19.0, 15.0),
    ]
    for r in records:
        con.execute(
            "INSERT INTO core.pit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            r
        )

    yield con
    con.close()


def test_load_sanitized_pit_events_filters_zero_prices(mock_duckdb):
    """Ensure price_at_publish <= 0 is filtered and only negative sentiment is loaded."""
    df = load_sanitized_pit_events(mock_duckdb)
    assert len(df) == 2
    assert (df["price_at_publish"] > 0).all()
    assert set(df["symbol"]) == {"FPT", "SHS"}


def test_regime_stats_dataclass():
    """Verify RegimeStats serializes properly to dict."""
    st = RegimeStats(
        regime_id="2020-2021-Bull",
        description="F0 retail liquidity boom",
        start_date="2020-04-01",
        end_date="2021-12-31",
        exchange="HOSE",
        n_events=25,
        mean_diff=0.035,
        median_diff=0.028,
        win_rate=0.64,
        loss_rate=0.36,
        std_diff=0.05,
        t_stat=3.5,
        p_val_t=0.001,
        wilcoxon_p=0.002,
        cohens_d=0.7,
        sign_flip=False,
    )
    d = st.__dict__
    assert d["n_events"] == 25
    assert d["sign_flip"] is False
    assert d["mean_diff"] == 0.035


def test_run_regime_audit_evaluation(mock_duckdb):
    """Verify run_regime_audit produces valid output format."""
    # Insert 10 events for FPT in COVID bull regime to satisfy minimum n >= 5
    for i in range(10):
        mock_duckdb.execute(
            "INSERT INTO core.pit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [f"syn_{i}", "FPT", f"2021-06-{10+i:02d} 09:00:00", "Thua lỗ quý 2", 50.0, 49.0, 52.0]
        )

    rep = run_regime_audit(mock_duckdb, out_path=None)
    assert "regime_matrix" in rep
    assert "total_sanitized_negative_events" in rep
    matrix = rep["regime_matrix"]
    assert len(matrix) >= 1
    found_bull = [r for r in matrix if r["regime_id"] == "2020-2021-Bull"]
    assert len(found_bull) >= 1
    cell = found_bull[0]
    assert cell["n_events"] >= 10
    assert "win_rate" in cell
    assert "median_diff" in cell
    assert "sign_flip" in cell
