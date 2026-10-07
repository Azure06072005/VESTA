"""src/arena/microstructure.py

F501 Vietnam Market Microstructure Engine.
Simulates T+2.5 settlement lock, exchange daily price limits (+-7% HOSE / +-10% HNX / +-15% UPCOM),
transaction friction (brokerage fee + sales tax + execution slippage), and 25% NAV concentration cap.
Strictly simulation: zero broker execution or external network logic (Rule B1).
"""
from __future__ import annotations

import dataclasses
from enum import Enum
import math
import pathlib
from typing import Dict, List, Optional
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = str(REPO_ROOT / "configs" / "arena.yaml")


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    INDEX_FUTURE = "INDEX_FUTURE"
    BOND_FUTURE = "BOND_FUTURE"
    COVERED_WARRANT = "COVERED_WARRANT"
    ETF = "ETF"
    CORP_BOND = "CORP_BOND"


def detect_asset_class(symbol: str) -> AssetClass:
    """Classifies a Vietnamese financial ticker into its regulatory asset class."""
    s = symbol.upper().strip()
    if s.startswith("VN30F"):
        return AssetClass.INDEX_FUTURE
    if s.startswith("GB05") or s.startswith("GB10"):
        return AssetClass.BOND_FUTURE
    if s.startswith("C") and len(s) >= 8 and any(char.isdigit() for char in s):
        return AssetClass.COVERED_WARRANT
    if s in {"E1VFVN30", "FUEVFVND", "FUESSVFL", "FUESSV30", "FUEVN100", "FUEIP100", "FUEKIV30"} or s.startswith("FUE"):
        return AssetClass.ETF
    if s.startswith("BOND_") or (len(s) >= 8 and s[-4:].isdigit() and not s.startswith("C")):
        return AssetClass.CORP_BOND
    return AssetClass.EQUITY


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderResult(str, Enum):
    FILLED = "FILLED"
    REJECTED_T25_LOCKED = "REJECTED_T25_LOCKED"
    REJECTED_PRICE_LIMIT = "REJECTED_PRICE_LIMIT"
    REJECTED_FLOOR_NO_LIQUIDITY = "REJECTED_FLOOR_NO_LIQUIDITY"
    REJECTED_NAV_CAP = "REJECTED_NAV_CAP"
    REJECTED_INSUFFICIENT_CASH = "REJECTED_INSUFFICIENT_CASH"
    REJECTED_NO_POSITION = "REJECTED_NO_POSITION"


@dataclasses.dataclass
class Order:
    symbol: str
    side: OrderSide
    shares: int
    price: float
    session_idx: int


@dataclasses.dataclass
class ExecutionReport:
    order: Order
    result: OrderResult
    filled_shares: int = 0
    fill_price: float = 0.0
    fee_paid: float = 0.0
    tax_paid: float = 0.0
    slippage_cost: float = 0.0
    net_cash_impact: float = 0.0
    message: str = ""


@dataclasses.dataclass
class Position:
    symbol: str
    shares: int
    buy_session_idx: int
    avg_price: float
    asset_class: AssetClass = AssetClass.EQUITY


class Portfolio:
    """Tracks cash, holdings, and portfolio NAV for a single bot."""

    def __init__(self, initial_cash: float = 10_000_000.0) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}

    def get_nav(self, current_prices: Dict[str, float]) -> float:
        equity_val = 0.0
        for sym, pos in self.positions.items():
            price = current_prices.get(sym, pos.avg_price)
            if pos.asset_class == AssetClass.INDEX_FUTURE:
                # VN30 Futures: Initial Margin value + Unrealized PnL (100k VND / point)
                margin_locked = pos.shares * pos.avg_price * 100_000.0 * 0.17
                unrealized_pnl = pos.shares * (price - pos.avg_price) * 100_000.0
                equity_val += (margin_locked + unrealized_pnl)
            else:
                equity_val += pos.shares * price
        return self.cash + equity_val

    def get_holding_days(self, symbol: str, current_session_idx: int) -> int:
        if symbol not in self.positions:
            return 0
        return current_session_idx - self.positions[symbol].buy_session_idx


class MicrostructureEngine:
    """Applies Vietnamese exchange trading rules, limits, settlement, and costs."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        cfg_file = config_path or DEFAULT_CONFIG_PATH
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.buy_pct = float(cfg["fees"]["buy_pct"])
        self.sell_pct = float(cfg["fees"]["sell_pct"])
        self.sell_tax_pct = float(cfg["fees"]["sell_tax_pct"])
        self.slippage_pct = float(cfg["fees"]["slippage_pct"])
        self.futures_fee_per_contract = float(cfg.get("fees", {}).get("futures_fee_per_contract", 5000.0))

        self.min_hold_sessions = int(cfg["settlement"]["min_hold_sessions"])
        self.futures_hold_sessions = int(cfg.get("settlement", {}).get("futures_hold_sessions", 0))
        self.bond_hold_sessions = int(cfg.get("settlement", {}).get("bond_hold_sessions", 1))

        self.price_limits = {k: float(v) for k, v in cfg["price_limit"].items()}
        self.nav_cap_per_symbol = float(cfg["risk_rails"]["nav_cap_per_symbol"])
        self.initial_cash = float(cfg["risk_rails"]["initial_cash"])
        self.min_order_lot = int(cfg["risk_rails"].get("min_order_lot", 1))

    def get_price_band(
        self,
        reference_price: float,
        exchange: str = "HOSE",
        asset_class: AssetClass = AssetClass.EQUITY,
    ) -> tuple[float, float]:
        if asset_class == AssetClass.INDEX_FUTURE:
            limit_pct = self.price_limits.get("VN30F", 0.07)
        elif asset_class == AssetClass.CORP_BOND:
            limit_pct = self.price_limits.get("HNX", 0.10)
        else:
            limit_pct = self.price_limits.get(exchange, 0.07)

        floor_price = round(reference_price * (1.0 - limit_pct), 2)
        ceiling_price = round(reference_price * (1.0 + limit_pct), 2)
        return floor_price, ceiling_price

    def process_order(
        self,
        order: Order,
        portfolio: Portfolio,
        reference_price: float,
        exchange: str = "HOSE",
        is_floor_locked: bool = False,
    ) -> ExecutionReport:
        asset_class = detect_asset_class(order.symbol)
        floor_p, ceil_p = self.get_price_band(reference_price, exchange, asset_class=asset_class)

        # 1. Price Limit check
        if order.price < floor_p - 1e-4 or order.price > ceil_p + 1e-4:
            return ExecutionReport(
                order=order,
                result=OrderResult.REJECTED_PRICE_LIMIT,
                message=f"Order price {order.price} outside band [{floor_p}, {ceil_p}]",
            )

        current_prices = {order.symbol: order.price}
        nav = portfolio.get_nav(current_prices)

        # Determine required holding sessions for T settlement
        if asset_class in {AssetClass.INDEX_FUTURE, AssetClass.BOND_FUTURE}:
            required_hold = self.futures_hold_sessions  # T+0
        elif asset_class == AssetClass.CORP_BOND:
            required_hold = self.bond_hold_sessions     # T+1
        else:
            required_hold = self.min_hold_sessions      # T+2.5 (3 sessions)

        # 2. SELL Execution Logic
        if order.side == OrderSide.SELL:
            if order.symbol not in portfolio.positions or portfolio.positions[order.symbol].shares <= 0:
                return ExecutionReport(
                    order=order,
                    result=OrderResult.REJECTED_NO_POSITION,
                    message="No existing position to sell",
                )

            holding_days = portfolio.get_holding_days(order.symbol, order.session_idx)
            if holding_days < required_hold:
                return ExecutionReport(
                    order=order,
                    result=OrderResult.REJECTED_T25_LOCKED,
                    message=f"Holding sessions {holding_days} < required {required_hold} for {asset_class.value}",
                )

            # Rule: Floor liquidity lock
            if is_floor_locked or math.isclose(order.price, floor_p, rel_tol=1e-3):
                return ExecutionReport(
                    order=order,
                    result=OrderResult.REJECTED_FLOOR_NO_LIQUIDITY,
                    message=f"Asset at floor price {floor_p}; zero liquidity on sell side",
                )

            current_pos = portfolio.positions[order.symbol]
            shares_to_sell = min(order.shares, current_pos.shares)

            fill_price = order.price * (1.0 - self.slippage_pct)

            if asset_class == AssetClass.INDEX_FUTURE:
                # Close out futures position: return initial margin + realized PnL
                multiplier = 100_000.0
                margin_rate = 0.17
                initial_margin_returned = shares_to_sell * current_pos.avg_price * multiplier * margin_rate
                realized_pnl = shares_to_sell * (fill_price - current_pos.avg_price) * multiplier
                fee = shares_to_sell * self.futures_fee_per_contract
                tax = max(0.0, realized_pnl) * self.sell_tax_pct
                slippage_impact = shares_to_sell * (order.price - fill_price) * multiplier
                net_proceeds = initial_margin_returned + realized_pnl - fee - tax
            else:
                gross_val = shares_to_sell * fill_price
                fee = gross_val * self.sell_pct
                tax = gross_val * self.sell_tax_pct
                slippage_impact = shares_to_sell * (order.price - fill_price)
                net_proceeds = gross_val - fee - tax

            # Apply to portfolio
            current_pos.shares -= shares_to_sell
            if current_pos.shares == 0:
                del portfolio.positions[order.symbol]
            portfolio.cash += net_proceeds

            return ExecutionReport(
                order=order,
                result=OrderResult.FILLED,
                filled_shares=shares_to_sell,
                fill_price=fill_price,
                fee_paid=fee,
                tax_paid=tax,
                slippage_cost=slippage_impact,
                net_cash_impact=net_proceeds,
                message=f"Sell order successfully filled ({asset_class.value})",
            )

        # 3. BUY Execution Logic
        if order.side == OrderSide.BUY:
            # NAV Cap Clipping (25% NAV max per ticker/contract)
            max_symbol_nav = nav * self.nav_cap_per_symbol

            if asset_class == AssetClass.INDEX_FUTURE:
                multiplier = 100_000.0
                margin_rate = 0.17
                fill_price = order.price * (1.0 + self.slippage_pct)
                margin_per_contract = fill_price * multiplier * margin_rate
                total_per_contract_cash = margin_per_contract + self.futures_fee_per_contract

                current_sym_val = (
                    portfolio.positions[order.symbol].shares * margin_per_contract
                    if order.symbol in portfolio.positions
                    else 0.0
                )
                available_nav_for_symbol = max(0.0, max_symbol_nav - current_sym_val)

                contracts_by_nav = int(available_nav_for_symbol // total_per_contract_cash)
                contracts_by_cash = int(portfolio.cash // total_per_contract_cash)
                fillable_shares = min(order.shares, contracts_by_nav, contracts_by_cash)

                if fillable_shares <= 0:
                    if contracts_by_nav <= 0 and current_sym_val >= max_symbol_nav:
                        return ExecutionReport(
                            order=order,
                            result=OrderResult.REJECTED_NAV_CAP,
                            message=f"Futures margin exceeds 25% NAV cap ({max_symbol_nav:,.0f} VND)",
                        )
                    return ExecutionReport(
                        order=order,
                        result=OrderResult.REJECTED_INSUFFICIENT_CASH,
                        message=f"Insufficient cash for futures margin ({total_per_contract_cash:,.0f} VND needed)",
                    )

                outflow_margin = fillable_shares * margin_per_contract
                fee = fillable_shares * self.futures_fee_per_contract
                total_outflow = outflow_margin + fee
                slippage_impact = fillable_shares * (fill_price - order.price) * multiplier

                portfolio.cash -= total_outflow
                if order.symbol in portfolio.positions:
                    existing = portfolio.positions[order.symbol]
                    new_shares = existing.shares + fillable_shares
                    new_avg = ((existing.shares * existing.avg_price) + (fillable_shares * fill_price)) / new_shares
                    portfolio.positions[order.symbol] = Position(
                        symbol=order.symbol,
                        shares=new_shares,
                        buy_session_idx=order.session_idx,
                        avg_price=new_avg,
                        asset_class=asset_class,
                    )
                else:
                    portfolio.positions[order.symbol] = Position(
                        symbol=order.symbol,
                        shares=fillable_shares,
                        buy_session_idx=order.session_idx,
                        avg_price=fill_price,
                        asset_class=asset_class,
                    )

                return ExecutionReport(
                    order=order,
                    result=OrderResult.FILLED,
                    filled_shares=fillable_shares,
                    fill_price=fill_price,
                    fee_paid=fee,
                    tax_paid=0.0,
                    slippage_cost=slippage_impact,
                    net_cash_impact=-total_outflow,
                    message="Futures buy (Long) successfully filled",
                )

            # Equities / ETFs / Covered Warrants / Bonds
            current_sym_val = (
                portfolio.positions[order.symbol].shares * order.price
                if order.symbol in portfolio.positions
                else 0.0
            )
            available_nav_for_symbol = max(0.0, max_symbol_nav - current_sym_val)

            fill_price = order.price * (1.0 + self.slippage_pct)
            per_share_cost = fill_price * (1.0 + self.buy_pct)

            shares_by_nav = int(available_nav_for_symbol // per_share_cost)
            shares_by_cash = int(portfolio.cash // per_share_cost)

            # Enforce lot constraints (odd-lot support: step by self.min_order_lot)
            raw_fillable = min(order.shares, shares_by_nav, shares_by_cash)
            fillable_shares = (raw_fillable // self.min_order_lot) * self.min_order_lot

            if fillable_shares <= 0:
                if shares_by_nav <= 0 and current_sym_val >= max_symbol_nav:
                    return ExecutionReport(
                        order=order,
                        result=OrderResult.REJECTED_NAV_CAP,
                        message=f"Symbol value exceeds 25% NAV cap ({max_symbol_nav:,.0f} VND)",
                    )
                return ExecutionReport(
                    order=order,
                    result=OrderResult.REJECTED_INSUFFICIENT_CASH,
                    message="Insufficient cash to purchase minimum lot",
                )

            gross_val = fillable_shares * fill_price
            fee = gross_val * self.buy_pct
            total_outflow = gross_val + fee
            slippage_impact = fillable_shares * (fill_price - order.price)

            # Apply to portfolio
            portfolio.cash -= total_outflow
            if order.symbol in portfolio.positions:
                existing = portfolio.positions[order.symbol]
                new_shares = existing.shares + fillable_shares
                new_avg = ((existing.shares * existing.avg_price) + (fillable_shares * fill_price)) / new_shares
                portfolio.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    shares=new_shares,
                    buy_session_idx=order.session_idx,
                    avg_price=new_avg,
                    asset_class=asset_class,
                )
            else:
                portfolio.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    shares=fillable_shares,
                    buy_session_idx=order.session_idx,
                    avg_price=fill_price,
                    asset_class=asset_class,
                )

            return ExecutionReport(
                order=order,
                result=OrderResult.FILLED,
                filled_shares=fillable_shares,
                fill_price=fill_price,
                fee_paid=fee,
                tax_paid=0.0,
                slippage_cost=slippage_impact,
                net_cash_impact=-total_outflow,
                message=f"Buy order successfully filled ({asset_class.value})" if fillable_shares == order.shares else f"Buy order clipped by cash or NAV cap ({asset_class.value})",
            )

        return ExecutionReport(order=order, result=OrderResult.REJECTED_PRICE_LIMIT, message="Unknown side")

