"""src/arena/bots.py

F501 Modular Bot Protocol and Strategy Component Evaluator.
Implements pure functional components (Signals S01-S21, Filters S14-S23, Overlays S09-S24, Baselines S25-S26).
Composes 308 bots dynamically from strategyID tokens (e.g. S11+S15+S09).
Strictly simulation: zero network, zero broker order code (Rule B1).
"""
from __future__ import annotations

import dataclasses
import math
from typing import Callable, Dict, List, Optional, Tuple

from src.arena.microstructure import (
    AssetClass,
    Order,
    OrderSide,
    Portfolio,
    detect_asset_class,
)



@dataclasses.dataclass
class MarketState:
    """Historical and fundamental context available strictly at or before decision time t."""
    session_idx: int
    date: str
    symbol: str
    prices: List[float]       # Close prices up to t (index -1 is current close at t)
    volumes: List[float]      # Volumes up to t
    sentiment_score: float = 50.0  # Scale [0, 100], 50 is neutral
    source_trust_weight: float = 0.85
    inconsistency_v: float = 0.10
    news_count_30d: int = 5
    news_count_avg_30d: float = 4.0
    piotroski_f_score: int = 7
    regime_label: str = "BULL_EUPHORIA"
    is_floor_hit: bool = False
    traded_value_20d: float = 15_000_000_000.0  # 15B VND
    earnings_yield: float = 0.08
    roc: float = 0.18
    pead_surprise: float = 0.15
    days_to_ex_dividend: Optional[int] = None
    is_insider_buying: bool = False


# =============================================================================
# STRATEGY COMPONENTS (Pure Functions)
# =============================================================================

def calc_sma(prices: List[float], window: int) -> float:
    if len(prices) < window:
        return prices[-1]
    return sum(prices[-window:]) / window


def calc_rsi(prices: List[float], window: int = 14) -> float:
    if len(prices) <= window:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-window, 0):
        diff = prices[i] - prices[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0.0:
        return 100.0
    rs = (gains / window) / (losses / window)
    return 100.0 - (100.0 / (1.0 + rs))


# 1. SIGNALS: Return (should_buy: bool, should_sell: bool)
def sig_s01_tsmom(state: MarketState) -> Tuple[bool, bool]:
    # S01: TSMOM 12-1
    if len(state.prices) < 22:
        return False, False
    ret = (state.prices[-1] / state.prices[-20]) - 1.0
    return (ret > 0.05, ret < -0.03)


def sig_s02_reversal(state: MarketState) -> Tuple[bool, bool]:
    # S02: ST reversal 5d
    if len(state.prices) < 6:
        return False, False
    ret_5d = (state.prices[-1] / state.prices[-6]) - 1.0
    return (ret_5d < -0.05, ret_5d > 0.05)


def sig_s03_sma_trend(state: MarketState) -> Tuple[bool, bool]:
    # S03: SMA 50/200 trend
    p = state.prices
    if len(p) < 20:
        return False, False
    sma_short = calc_sma(p, min(10, len(p)))
    sma_long = calc_sma(p, min(20, len(p)))
    return (p[-1] > sma_long and sma_short > sma_long, p[-1] < sma_long)


def sig_s04_donchian(state: MarketState) -> Tuple[bool, bool]:
    # S04: Donchian breakout
    p = state.prices
    if len(p) < 20:
        return False, False
    high_20 = max(p[-20:-1]) if len(p) > 20 else max(p[:-1])
    low_10 = min(p[-10:-1]) if len(p) > 10 else min(p[:-1])
    return (p[-1] > high_20, p[-1] < low_10)


def sig_s05_rsi(state: MarketState) -> Tuple[bool, bool]:
    # S05: RSI(14) oversold
    rsi = calc_rsi(state.prices, 14)
    sma_ref = calc_sma(state.prices, min(20, len(state.prices)))
    return (rsi < 30.0 and state.prices[-1] >= sma_ref * 0.98, rsi > 60.0)


def sig_s06_bollinger(state: MarketState) -> Tuple[bool, bool]:
    # S06: Bollinger reversion
    p = state.prices
    if len(p) < 20:
        return False, False
    ma = calc_sma(p, 20)
    std = math.sqrt(sum((x - ma) ** 2 for x in p[-20:]) / 20)
    lower = ma - (2.0 * std)
    return (p[-1] < lower, p[-1] >= ma)


def sig_s07_low_vol(state: MarketState) -> Tuple[bool, bool]:
    # S07: Low volatility
    p = state.prices
    if len(p) < 20:
        return False, False
    vol = math.sqrt(sum((p[i]/p[i-1] - 1.0) ** 2 for i in range(-19, 0)) / 19)
    return (vol < 0.015, vol > 0.035)


def sig_s08_volume_surge(state: MarketState) -> Tuple[bool, bool]:
    # S08: Volume surge breakout
    v = state.volumes
    p = state.prices
    if len(v) < 20 or len(p) < 2:
        return False, False
    avg_v = sum(v[-20:-1]) / 19
    ret = (p[-1] / p[-2]) - 1.0
    return (v[-1] > 2.5 * avg_v and ret > 0.02, ret < -0.05)


def sig_s10_limit_down(state: MarketState) -> Tuple[bool, bool]:
    # S10: Limit-down rebound
    return (state.is_floor_hit, False)


def sig_s11_negative_dip(state: MarketState) -> Tuple[bool, bool]:
    # S11: Negative-sentiment dip buy
    p = state.prices
    if len(p) < 5:
        return False, False
    dip = (p[-1] / p[-5]) - 1.0
    return (state.sentiment_score < 35.0 and dip < -0.03, False)


def sig_s12_positive_momentum(state: MarketState) -> Tuple[bool, bool]:
    # S12: Positive-sentiment momentum
    p = state.prices
    if len(p) < 2:
        return False, False
    ret = (p[-1] / p[-2]) - 1.0
    return (state.sentiment_score > 65.0 and ret > 0.01, False)


def sig_s13_sentiment_fade(state: MarketState) -> Tuple[bool, bool]:
    # S13: Sentiment-shock fade
    return (abs(state.sentiment_score - 50.0) > 30.0, False)


def sig_s17_magic_formula(state: MarketState) -> Tuple[bool, bool]:
    # S17: Greenblatt Magic Formula
    return (state.earnings_yield > 0.07 and state.roc > 0.15, False)


def sig_s18_pead(state: MarketState) -> Tuple[bool, bool]:
    # S18: Post-Earnings Announcement Drift
    return (state.pead_surprise > 0.10, False)


def sig_s19_dividend_runup(state: MarketState) -> Tuple[bool, bool]:
    # S19: Dividend ex-date runup
    if state.days_to_ex_dividend is not None:
        return (1 <= state.days_to_ex_dividend <= 10, state.days_to_ex_dividend <= 0)
    return False, False


def sig_s20_share_bonus(state: MarketState) -> Tuple[bool, bool]:
    # S20: Share issue / bonus drift
    return (state.pead_surprise > 0.05, False)


def sig_s21_insider_follow(state: MarketState) -> Tuple[bool, bool]:
    # S21: Insider buying follow
    return (state.is_insider_buying, False)


def sig_s25_equal_weight(state: MarketState) -> Tuple[bool, bool]:
    # S25: Baseline equal weight (always active buy on session 0)
    return (state.session_idx == 0, False)


def sig_s26_buy_and_hold(state: MarketState) -> Tuple[bool, bool]:
    # S26: Baseline buy and hold
    return (state.session_idx == 0, False)


SIGNALS: Dict[str, Callable[[MarketState], Tuple[bool, bool]]] = {
    "S01": sig_s01_tsmom,
    "S02": sig_s02_reversal,
    "S03": sig_s03_sma_trend,
    "S04": sig_s04_donchian,
    "S05": sig_s05_rsi,
    "S06": sig_s06_bollinger,
    "S07": sig_s07_low_vol,
    "S08": sig_s08_volume_surge,
    "S10": sig_s10_limit_down,
    "S11": sig_s11_negative_dip,
    "S12": sig_s12_positive_momentum,
    "S13": sig_s13_sentiment_fade,
    "S17": sig_s17_magic_formula,
    "S18": sig_s18_pead,
    "S19": sig_s19_dividend_runup,
    "S20": sig_s20_share_bonus,
    "S21": sig_s21_insider_follow,
    "S25": sig_s25_equal_weight,
    "S26": sig_s26_buy_and_hold,
}


# 2. FILTERS: Return passes_filter: bool
def flt_s14_attention(state: MarketState) -> bool:
    # S14: Attention-spike filter: skip if news count > 3x average
    return state.news_count_30d <= 3.0 * state.news_count_avg_30d


def flt_s15_rumor_gate(state: MarketState) -> bool:
    # S15: HybridACD Rumor gate: source weight >= 0.70 and inconsistency V <= 0.35
    return state.source_trust_weight >= 0.70 and state.inconsistency_v <= 0.35


def flt_s16_piotroski(state: MarketState) -> bool:
    # S16: Piotroski F-score >= 7
    return state.piotroski_f_score >= 7


def flt_s22_regime_gate(state: MarketState) -> bool:
    # S22: Regime gate: only risk-on regimes (Bull, Sideway)
    return state.regime_label not in ("BEAR_CREDIT_CRISIS", "SYSTEMIC_BLACK_SWAN")


def flt_s23_liquidity(state: MarketState) -> bool:
    # S23: Liquidity filter: min 20d average value >= 5B VND
    return state.traded_value_20d >= 5_000_000_000.0


FILTERS: Dict[str, Callable[[MarketState], bool]] = {
    "S14": flt_s14_attention,
    "S15": flt_s15_rumor_gate,
    "S16": flt_s16_piotroski,
    "S22": flt_s22_regime_gate,
    "S23": flt_s23_liquidity,
}


# 3. OVERLAYS / SIZING: Return size_multiplier: float
def ovr_s09_vol_target(state: MarketState) -> float:
    # S09: Vol-target sizing (target 15% vol)
    p = state.prices
    if len(p) < 20:
        return 1.0
    vol = math.sqrt(sum((p[i]/p[i-1] - 1.0) ** 2 for i in range(-19, 0)) / 19) * math.sqrt(250)
    if vol <= 0.01:
        return 1.0
    return min(1.2, max(0.5, 0.15 / vol))


def ovr_s24_bear_rotation(state: MarketState) -> float:
    # S24: Gross exposure x0.3 in bear regime
    if state.regime_label in ("BEAR_CREDIT_CRISIS", "SYSTEMIC_BLACK_SWAN"):
        return 0.3
    return 1.0


OVERLAYS: Dict[str, Callable[[MarketState], float]] = {
    "S09": ovr_s09_vol_target,
    "S24": ovr_s24_bear_rotation,
}


# =============================================================================
# BOT COMPOSER
# =============================================================================

class CompositeBot:
    """Dynamically evaluates strategy components for any bot in the 308-bot arena."""

    def __init__(
        self,
        bot_id: str,
        strategy_id: str,
        is_ai: bool = False,
        ai_role: str = "",
    ) -> None:
        self.bot_id = bot_id
        self.strategy_id = strategy_id
        self.tokens = strategy_id.split("+")
        self.is_ai = is_ai
        self.ai_role = ai_role

        # Classify tokens
        self.signal_id = self.tokens[0]
        self.filter_ids = [t for t in self.tokens[1:] if t in FILTERS]
        self.overlay_ids = [t for t in self.tokens[1:] if t in OVERLAYS]

    def decide(self, state: MarketState, portfolio: Portfolio) -> List[Order]:
        orders: List[Order] = []
        curr_price = state.prices[-1]

        # 1. Evaluate Signal
        sig_fn = SIGNALS.get(self.signal_id)
        if sig_fn is None:
            return orders

        should_buy, should_sell = sig_fn(state)

        # AI Twin Enhancement:
        # If AI model is attached, AI acts as an additional high-precision meta-labeling gate
        if self.is_ai:
            if "price" in self.ai_role:
                # Meta-labeling filter
                if should_buy and len(state.prices) >= 10:
                    ma10 = sum(state.prices[-10:]) / 10
                    if curr_price < ma10:
                        should_buy = False
            elif "news" in self.ai_role:
                # PhoBERT sentiment verification
                if should_buy and state.sentiment_score < 45.0:
                    should_buy = False
            elif "macro" in self.ai_role:
                if state.regime_label == "BEAR_CREDIT_CRISIS":
                    should_buy = False

        # 2. Check Holding & Exits
        has_pos = state.symbol in portfolio.positions and portfolio.positions[state.symbol].shares > 0
        holding_days = portfolio.get_holding_days(state.symbol, state.session_idx)
        asset_class = detect_asset_class(state.symbol)

        # Regulatory settlement lock: T+0 for Futures, T+1 for Bonds, T+2.5 (3 sessions) for Equities/ETFs/CW
        if asset_class in {AssetClass.INDEX_FUTURE, AssetClass.BOND_FUTURE}:
            req_hold = 0
        elif asset_class == AssetClass.CORP_BOND:
            req_hold = 1
        else:
            req_hold = 3

        # Profit target or stop loss exit rule for trading bots
        if has_pos and holding_days >= req_hold:
            pos = portfolio.positions[state.symbol]
            pnl_pct = (curr_price / pos.avg_price) - 1.0
            if pnl_pct >= 0.08 or pnl_pct <= -0.07 or should_sell:
                orders.append(
                    Order(
                        symbol=state.symbol,
                        side=OrderSide.SELL,
                        shares=pos.shares,
                        price=curr_price,
                        session_idx=state.session_idx,
                    )
                )
                return orders

        # 3. Evaluate Filters for Entry
        if should_buy and not has_pos:
            for fid in self.filter_ids:
                flt_fn = FILTERS.get(fid)
                if flt_fn and not flt_fn(state):
                    return orders  # Filter rejected entry

            # 4. Sizing with Overlays
            size_multiplier = 1.0
            for oid in self.overlay_ids:
                ovr_fn = OVERLAYS.get(oid)
                if ovr_fn:
                    size_multiplier *= ovr_fn(state)

            target_val = (portfolio.initial_cash * 0.20) * size_multiplier

            # Sizing according to asset class & 10M VND account constraints
            if asset_class == AssetClass.INDEX_FUTURE:
                # 1 contract margin is ~17% of index value
                margin_per_contract = curr_price * 100_000.0 * 0.17
                shares_to_buy = max(1, int(target_val // margin_per_contract)) if margin_per_contract > 0 else 1
            else:
                # Odd-lot support: 1 share minimum lot for retail 10M VND budget
                shares_to_buy = max(1, int(target_val // curr_price))

            orders.append(
                Order(
                    symbol=state.symbol,
                    side=OrderSide.BUY,
                    shares=shares_to_buy,
                    price=curr_price,
                    session_idx=state.session_idx,
                )
            )

        return orders
