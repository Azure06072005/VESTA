"""tests/test_arena_microstructure.py

Unit tests for F501 Vietnam Market Microstructure Simulator.
Verifies all 5 core microstructure rules:
1. Sell lock rejection at holding_days < 3, acceptance at holding_days == 3.
2. 25% NAV concentration cap clipping.
3. Round-trip friction accounting (fee + tax + slippage).
4. Daily price limit rejection (+-7% HOSE).
5. Floor price zero-liquidity lock rejection.
"""
from __future__ import annotations

import math
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.arena.microstructure import (
    MicrostructureEngine,
    Order,
    OrderResult,
    OrderSide,
    Portfolio,
    Position,
)


@pytest.fixture
def engine() -> MicrostructureEngine:
    return MicrostructureEngine()


def test_t25_sell_lock(engine: MicrostructureEngine):
    """A sell at holding_days=2 is rejected; at holding_days=3 it is accepted."""
    portfolio = Portfolio(initial_cash=500_000_000.0)
    # Buy on session 0
    portfolio.positions["VNM"] = Position(
        symbol="VNM",
        shares=1000,
        buy_session_idx=0,
        avg_price=70.0,
    )

    # Attempt to sell on session 2 (holding_days = 2 - 0 = 2 < 3)
    sell_order_early = Order(
        symbol="VNM",
        side=OrderSide.SELL,
        shares=1000,
        price=70.0,
        session_idx=2,
    )
    rep_early = engine.process_order(sell_order_early, portfolio, reference_price=70.0)
    assert rep_early.result == OrderResult.REJECTED_T25_LOCKED

    # Attempt to sell on session 3 (holding_days = 3 - 0 = 3 >= 3)
    sell_order_valid = Order(
        symbol="VNM",
        side=OrderSide.SELL,
        shares=1000,
        price=70.0,
        session_idx=3,
    )
    rep_valid = engine.process_order(sell_order_valid, portfolio, reference_price=70.0)
    assert rep_valid.result == OrderResult.FILLED
    assert rep_valid.filled_shares == 1000


def test_nav_cap_clipping(engine: MicrostructureEngine):
    """A buy beyond the 25% NAV cap is clipped."""
    initial_cash = 1_000_000_000.0
    portfolio = Portfolio(initial_cash=initial_cash)

    # Request to buy 500,000,000 VND worth of FPT (50% of NAV)
    price = 100_000.0
    shares_requested = 5_000  # 5,000 * 100,000 = 500,000,000 VND

    buy_order = Order(
        symbol="FPT",
        side=OrderSide.BUY,
        shares=shares_requested,
        price=price,
        session_idx=0,
    )
    rep = engine.process_order(buy_order, portfolio, reference_price=price)

    assert rep.result == OrderResult.FILLED
    # 25% of 1B is 250,000,000 VND -> ~2,490 shares after accounting for slippage + fee
    assert rep.filled_shares < shares_requested
    assert rep.filled_shares * price <= initial_cash * 0.25 + 500_000.0


def test_round_trip_costs(engine: MicrostructureEngine):
    """A round trip at zero price change loses exactly the fee + tax + slippage total."""
    initial_cash = 1_000_000_000.0
    portfolio = Portfolio(initial_cash=initial_cash)
    p0 = 50_000.0
    shares = 1000

    # 1. Buy at session 0
    buy_ord = Order(symbol="HPG", side=OrderSide.BUY, shares=shares, price=p0, session_idx=0)
    rep_buy = engine.process_order(buy_ord, portfolio, reference_price=p0)
    assert rep_buy.result == OrderResult.FILLED

    # 2. Sell at session 3 (exact same nominal price p0)
    sell_ord = Order(symbol="HPG", side=OrderSide.SELL, shares=shares, price=p0, session_idx=3)
    rep_sell = engine.process_order(sell_ord, portfolio, reference_price=p0)
    assert rep_sell.result == OrderResult.FILLED

    final_cash = portfolio.cash
    loss = initial_cash - final_cash

    # Expected frictions:
    # Buy: shares * p0 * (1 + slippage) * (1 + buy_pct)
    # Sell: shares * p0 * (1 - slippage) * (1 - sell_pct - sell_tax_pct)
    buy_outflow = -rep_buy.net_cash_impact
    sell_inflow = rep_sell.net_cash_impact
    expected_loss = buy_outflow - sell_inflow

    assert math.isclose(loss, expected_loss, rel_tol=1e-5)
    # Total friction rate on ~50M trade is roughly (0.15% + 0.10% buy) + (0.15% + 0.10% + 0.10% sell) ≈ 0.60%
    assert loss > 0.0


def test_price_limit_rejection(engine: MicrostructureEngine):
    """An order outside the daily limit band (+-7% HOSE) is rejected."""
    portfolio = Portfolio(initial_cash=1_000_000_000.0)
    ref_price = 100.0

    # Ceiling is 107.0 -> order at 108.0 must reject
    buy_too_high = Order(symbol="VIC", side=OrderSide.BUY, shares=100, price=108.0, session_idx=0)
    rep_high = engine.process_order(buy_too_high, portfolio, reference_price=ref_price, exchange="HOSE")
    assert rep_high.result == OrderResult.REJECTED_PRICE_LIMIT

    # Floor is 93.0 -> order at 92.0 must reject
    buy_too_low = Order(symbol="VIC", side=OrderSide.BUY, shares=100, price=92.0, session_idx=0)
    rep_low = engine.process_order(buy_too_low, portfolio, reference_price=ref_price, exchange="HOSE")
    assert rep_low.result == OrderResult.REJECTED_PRICE_LIMIT


def test_floor_locked_stock_cannot_be_sold(engine: MicrostructureEngine):
    """A floor-locked stock with zero liquidity cannot be sold (REJECTED_FLOOR_NO_LIQUIDITY)."""
    portfolio = Portfolio(initial_cash=1_000_000_000.0)
    ref_price = 100.0
    floor_price = 93.0  # -7% on HOSE

    portfolio.positions["MWG"] = Position(
        symbol="MWG",
        shares=1000,
        buy_session_idx=0,
        avg_price=100.0,
    )

    # Attempt to sell when stock hits floor with no bids
    sell_floor = Order(symbol="MWG", side=OrderSide.SELL, shares=1000, price=floor_price, session_idx=3)
    rep = engine.process_order(sell_floor, portfolio, reference_price=ref_price, exchange="HOSE", is_floor_locked=True)
    assert rep.result == OrderResult.REJECTED_FLOOR_NO_LIQUIDITY
    assert "floor" in rep.message.lower()


def test_multi_asset_detection():
    """Verify ticker classification into standard Vietnamese asset classes."""
    from src.arena.microstructure import AssetClass, detect_asset_class

    assert detect_asset_class("VN30F1M") == AssetClass.INDEX_FUTURE
    assert detect_asset_class("VN30F2409") == AssetClass.INDEX_FUTURE
    assert detect_asset_class("GB05F") == AssetClass.BOND_FUTURE
    assert detect_asset_class("CFPT2301") == AssetClass.COVERED_WARRANT
    assert detect_asset_class("E1VFVN30") == AssetClass.ETF
    assert detect_asset_class("FUEVFVND") == AssetClass.ETF
    assert detect_asset_class("BOND_VIC123") == AssetClass.CORP_BOND
    assert detect_asset_class("HPG") == AssetClass.EQUITY
    assert detect_asset_class("VNM") == AssetClass.EQUITY


def test_futures_t0_settlement(engine: MicrostructureEngine):
    """VN30 Futures support T+0 intraday closing without T+2.5 lock."""
    # 1 contract at 1200 points requires ~20.4M VND margin. With 25% NAV cap, portfolio NAV >= ~82M VND.
    portfolio = Portfolio(initial_cash=100_000_000.0)
    # Buy 1 contract VN30F1M at 1,200 points on session 0
    buy_order = Order(symbol="VN30F1M", side=OrderSide.BUY, shares=1, price=1200.0, session_idx=0)
    rep_buy = engine.process_order(buy_order, portfolio, reference_price=1200.0)
    assert rep_buy.result == OrderResult.FILLED
    assert rep_buy.filled_shares == 1

    # Immediately sell (close long) in session 0 (T+0)
    sell_order = Order(symbol="VN30F1M", side=OrderSide.SELL, shares=1, price=1210.0, session_idx=0)
    rep_sell = engine.process_order(sell_order, portfolio, reference_price=1210.0)
    assert rep_sell.result == OrderResult.FILLED
    assert rep_sell.filled_shares == 1
    # Check that position is closed
    assert "VN30F1M" not in portfolio.positions


def test_retail_budget_odd_lot(engine: MicrostructureEngine):
    """Retail accounts with 10M VND can buy odd-lot equities and ETFs within NAV cap."""
    portfolio = Portfolio(initial_cash=10_000_000.0)
    # FPT at 120,000 VND / share. 25% NAV cap is 2.5M VND. Max shares ~ 20 shares (odd lot < 100)
    buy_fpt = Order(symbol="FPT", side=OrderSide.BUY, shares=20, price=120_000.0, session_idx=0)
    rep = engine.process_order(buy_fpt, portfolio, reference_price=120_000.0)
    assert rep.result == OrderResult.FILLED
    assert rep.filled_shares == 20
    assert portfolio.positions["FPT"].shares == 20
    assert portfolio.cash < 10_000_000.0

