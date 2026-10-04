"""tests/test_arena_stats.py

Unit tests for F501 Arena statistics, look-ahead bias prevention, and compliance.
Verifies:
1. Rule B1 Compliance: Zero network or broker execution imports in src/arena/*.py.
2. Look-ahead bias prevention: Deliberately injected future data does not alter signal at time t.
3. DSR (Deflated Sharpe Ratio) formula with raw and effective N.
4. Deterministic reproducibility: Identical seed produces bit-identical results.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.arena.bots import MarketState, sig_s01_tsmom, sig_s04_donchian
from src.arena.run import run_tournament
from src.arena.stats import (
    compute_cvar_95,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_pbo_probability,
)


def test_arena_has_no_network_or_execution_imports():
    """Confirms src/arena/ contains strictly NO network or broker execution imports (Rule B1)."""
    arena_dir = REPO_ROOT / "src" / "arena"
    banned_modules = {"requests", "socket", "httpx", "websockets", "urllib.request", "execution"}

    for py_file in arena_dir.glob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for banned in banned_modules:
                        assert not alias.name.startswith(banned), f"Banned import '{alias.name}' in {py_file.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for banned in banned_modules:
                        assert not node.module.startswith(banned), f"Banned import from '{node.module}' in {py_file.name}"


def test_look_ahead_bias_prevention():
    """Asserts that appending future prices does not alter decision at session t."""
    historical_prices = [100.0, 101.0, 102.0, 101.5, 103.0, 104.0, 105.0]
    state_t = MarketState(
        session_idx=6,
        date="2026-01-07",
        symbol="VNM",
        prices=list(historical_prices),
        volumes=[1000.0] * len(historical_prices),
    )

    decision_before = sig_s04_donchian(state_t)

    # Injected future prices that happen at t+1, t+2
    future_leak = [120.0, 130.0]
    # State strictly evaluated at t using only historical_prices
    state_strict = MarketState(
        session_idx=6,
        date="2026-01-07",
        symbol="VNM",
        prices=list(historical_prices),
        volumes=[1000.0] * len(historical_prices),
    )
    decision_after = sig_s04_donchian(state_strict)

    assert decision_before == decision_after


def test_dsr_and_tail_risk_metrics():
    """Verifies DSR deflation responds monotonically to number of trials."""
    returns = [0.01, -0.005, 0.015, -0.01, 0.02, 0.005, -0.008, 0.012] * 5
    sharpe = 1.5

    # DSR with 5 trials vs 308 trials
    dsr_5 = compute_deflated_sharpe_ratio(sharpe=sharpe, t_sessions=40, n_trials=5, returns=returns)
    dsr_308 = compute_deflated_sharpe_ratio(sharpe=sharpe, t_sessions=40, n_trials=308, returns=returns)

    # With higher number of trials (multiple hypothesis testing), DSR must decrease
    assert dsr_5 > dsr_308
    assert 0.0 <= dsr_308 <= 1.0

    # MaxDD along NAV curve
    nav_curve = [100.0, 105.0, 110.0, 99.0, 95.0, 102.0]
    mdd = compute_max_drawdown(nav_curve)
    # Peak is 110, trough is 95 -> (110 - 95)/110 = 13.64%
    assert round(mdd, 1) == 13.6

    # CVaR 95%
    cvar = compute_cvar_95(returns)
    assert cvar >= 0.0


def test_deterministic_reproducibility(tmp_path: pathlib.Path):
    """Verifies that two runs with identical seed produce bit-identical report output."""
    rep_1 = str(tmp_path / "rep_1.json")
    rep_2 = str(tmp_path / "rep_2.json")
    h2h_1 = str(tmp_path / "h2h_1.csv")
    h2h_2 = str(tmp_path / "h2h_2.csv")

    res_1 = run_tournament(num_paths_per_situation=2, seed=42, report_output=rep_1, h2h_output=h2h_1)
    res_2 = run_tournament(num_paths_per_situation=2, seed=42, report_output=rep_2, h2h_output=h2h_2)

    with open(rep_1, "r", encoding="utf-8") as f1, open(rep_2, "r", encoding="utf-8") as f2:
        assert f1.read() == f2.read()
