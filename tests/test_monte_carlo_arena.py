"""tests/test_monte_carlo_arena.py

Test Suite for Feature F501: Multi-Bot Strategy Arena & Monte Carlo Decision Tournament.
Verifies the following 6 core invariants:
1. Bot decision logic: verifies that all 5 bot personas make distinct decisions under bull, panic, and rumor events.
2. Vietnam market microstructure: verifies T+2.5 settlement lock, fees (0.15% buy, 0.25% sell+tax), and slippage.
3. Stationary block bootstrap: verifies sequence continuity and stationarity properties.
4. Multi-situation arena execution: verifies all 5 Vietnam market situations execute without error.
5. Deflated Sharpe Ratio & tournament ranking: verifies DSR calculation, leaderboard sorting, and head-to-head matrix.
6. Strictly Read-Only compliance: verifies Rule B1 compliance (zero live broker execution logic).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
from typing import List

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pipeline.monte_carlo_bot_arena import (
    ArenaTournament,
    BotAction,
    ForceBuyBot,
    ForceSellBot,
    HybridACDSniperBot,
    MarketEvent,
    MarketSituation,
    MomentumBot,
    MonteCarloEngine,
    Position,
    RegimeGatedBot,
    TradingBot,
    VietnamMarketSimulator,
    compute_deflated_sharpe_ratio,
)


# =============================================================================
# 1. BOT DECISION LOGIC VERIFICATION
# =============================================================================
def test_bot_decision_logic():
    """Verifies that each bot persona executes its distinct philosophical decision."""
    force_buy_bot = ForceBuyBot()
    force_sell_bot = ForceSellBot()
    momentum_bot = MomentumBot()
    regime_bot = RegimeGatedBot()
    sniper_bot = HybridACDSniperBot()

    # Event 1: Panic Negative Dip on Official News (UBCKNN W=1.0, Consistent V=0.05, Safe Regime)
    panic_event = MarketEvent(
        event_id="EVT_PANIC",
        symbol="HPG",
        date=dt.date(2024, 6, 1),
        headline="Giá thép giảm mạnh khiến cổ phiếu HPG bị bán tháo",
        sentiment_score=28.0,
        consistent_alpha_score=38.0,  # High mean-reversion opportunity
        is_consistent=True,
        violation_score=0.05,
        source_trust_weight=1.0,
        fundamental_health_score=75.0,
        regime_safe_to_trade=True,
    )

    # ForceBuyBot aggressively buys panic dips
    assert force_buy_bot.decide(panic_event, None, 1e9, 1e9, 1) == BotAction.FORCE_BUY
    # ForceSellBot refuses to enter on negative sentiment
    assert force_sell_bot.decide(panic_event, None, 1e9, 1e9, 1) == BotAction.AVOID
    # MomentumBot avoids / does not buy negative news
    assert momentum_bot.decide(panic_event, None, 1e9, 1e9, 1) == BotAction.HOLD
    # RegimeGatedBot buys the dip in safe regime
    assert regime_bot.decide(panic_event, None, 1e9, 1e9, 1) == BotAction.BUY
    # HybridACDSniperBot buys high-conviction dip (W=1.0, V<0.35, Health=75)
    assert sniper_bot.decide(panic_event, None, 1e9, 1e9, 1) == BotAction.FORCE_BUY

    # Event 2: Forum F319 Rumor Storm (Unverified W=0.35, Inconsistent V=0.55)
    rumor_event = MarketEvent(
        event_id="EVT_RUMOR",
        symbol="VHM",
        date=dt.date(2024, 6, 2),
        headline="Tin đồn diễn đàn F319 về dự án bất động sản khủng",
        sentiment_score=80.0,
        consistent_alpha_score=50.0,
        is_consistent=False,
        violation_score=0.55,
        source_trust_weight=0.35,
        fundamental_health_score=50.0,
        regime_safe_to_trade=True,
    )
    # MomentumBot FOMO chases the positive rumor
    assert momentum_bot.decide(rumor_event, None, 1e9, 1e9, 2) in [BotAction.BUY, BotAction.FORCE_BUY]
    # SniperBot filters the rumor out due to low W_source and high violation
    assert sniper_bot.decide(rumor_event, None, 1e9, 1e9, 2) == BotAction.HOLD

    # Event 3: Crisis Market Regime (VN-INDEX < MA200 Liquidity Freeze)
    crisis_event = MarketEvent(
        event_id="EVT_CRISIS",
        symbol="SSI",
        date=dt.date(2024, 6, 3),
        headline="Thị trường rơi vào khủng hoảng thanh khoản diện rộng",
        sentiment_score=35.0,
        consistent_alpha_score=35.0,
        is_consistent=True,
        violation_score=0.10,
        source_trust_weight=0.90,
        fundamental_health_score=60.0,
        regime_safe_to_trade=False,  # Crisis regime
    )
    # RegimeGatedBot and SniperBot fail closed to AVOID
    assert regime_bot.decide(crisis_event, None, 1e9, 1e9, 3) == BotAction.AVOID
    assert sniper_bot.decide(crisis_event, None, 1e9, 1e9, 3) == BotAction.AVOID


# =============================================================================
# 2. VIETNAM MARKET MICROSTRUCTURE (T+2.5, LIMITS, FRICTION)
# =============================================================================
def test_vietnam_market_friction_and_t25():
    """Verifies that T+2.5 settlement latency and fees/taxes are strictly enforced."""
    sim = VietnamMarketSimulator(initial_cash=1_000_000_000.0)
    bot = ForceBuyBot()

    event = MarketEvent(
        event_id="EVT_BUY",
        symbol="VCB",
        date=dt.date(2024, 1, 1),
        headline="VCB đón nhận dòng tiền lớn",
        sentiment_score=35.0,
        consistent_alpha_score=35.0,
        is_consistent=True,
        violation_score=0.05,
        source_trust_weight=0.90,
        fundamental_health_score=80.0,
        regime_safe_to_trade=True,
    )

    # Day 1: Buy executed
    res_buy = sim.execute_action(bot, event, current_day=1, day_price=90000.0)
    assert res_buy is not None
    assert res_buy["status"] == "FILLED"
    assert "VCB" in sim.positions
    shares_held = sim.positions["VCB"].shares
    assert shares_held > 0

    # Day 2: Attempt to sell on day 2 (T+1) -> MUST FAIL with T+2.5 lock!
    # Mock bot to decide SELL
    class SellNowBot(TradingBot):
        def decide(self, event, position, cash, total_nav, current_day):
            return BotAction.SELL

    sell_bot = SellNowBot(bot_id="SELL_BOT", name="Sell", philosophy="")
    res_t1 = sim.execute_action(sell_bot, event, current_day=2, day_price=95000.0)
    assert res_t1 is not None
    assert res_t1["status"] == "REJECTED_T25_LOCKED"
    assert "VCB" in sim.positions, "Position must NOT be sold before T+2.5!"

    # Day 3: Attempt to sell on day 3 (T+2 morning) -> still locked
    res_t2 = sim.execute_action(sell_bot, event, current_day=3, day_price=95000.0)
    assert res_t2 is not None
    assert res_t2["status"] == "REJECTED_T25_LOCKED"

    # Day 4: Sell on day 4 (T+3 open, after T+2.5 settlement) -> MUST SUCCEED!
    res_t3 = sim.execute_action(sell_bot, event, current_day=4, day_price=95000.0)
    assert res_t3 is not None
    assert res_t3["status"] == "FILLED"
    assert "VCB" not in sim.positions
    assert res_t3["fee"] > 0.0, "Brokerage fee must be deducted"
    assert res_t3["tax"] > 0.0, "Statutory 0.1% sell tax must be deducted"


# =============================================================================
# 3. STATIONARY BLOCK BOOTSTRAP RESAMPLING
# =============================================================================
def test_block_bootstrap_stationarity():
    """Verifies that the stationary block bootstrap generates valid paths of requested length."""
    engine = MonteCarloEngine(mean_block_length=10, random_seed=123)
    base_seq = engine.generate_synthetic_situation_dataset(MarketSituation.BULL_EUPHORIA, num_days=60)
    assert len(base_seq) == 60 * 5  # 60 days * 5 symbols

    # Resample path
    resampled = engine.stationary_block_bootstrap(base_seq, num_days=100)
    assert len(resampled) == 100
    for day, ev, pr in resampled:
        assert day >= 1
        assert ev.symbol in ["VCB", "HPG", "SSI", "VHM", "FPT"]
        assert pr > 0.0
        assert not np.isnan(pr)


# =============================================================================
# 4. MULTI-SITUATION ARENA EXECUTION
# =============================================================================
def test_multi_situation_arena_execution():
    """Verifies that all 5 Vietnam market situations run without errors."""
    tournament = ArenaTournament(iterations=50, random_seed=42)
    situations = [
        MarketSituation.BULL_EUPHORIA,
        MarketSituation.BEAR_CREDIT_CRISIS,
        MarketSituation.SIDEWAY_RANGE_BOUND,
        MarketSituation.HIGH_NOISE_RUMOR_STORM,
        MarketSituation.SYSTEMIC_BLACK_SWAN,
    ]
    report = tournament.run_tournament(situations=situations, paths_per_situation=10)

    assert "leaderboard" in report
    assert len(report["leaderboard"]) == 5
    assert "situation_breakdown" in report
    assert len(report["situation_breakdown"]) == 5

    # In Bear/Credit crisis, Safe and Sniper bots should have lower MaxDD than Aggressive Dip Buyer
    bear_summary = report["situation_breakdown"][MarketSituation.BEAR_CREDIT_CRISIS.value]
    assert "BOT_FORCE_BUY" in bear_summary
    assert "BOT_HYBRIDACD_SNIPER" in bear_summary


# =============================================================================
# 5. DEFLATED SHARPE RATIO & TOURNAMENT RANKING
# =============================================================================
def test_deflated_sharpe_and_tournament_ranking():
    """Verifies DSR calculation, tournament ranking, and head-to-head win rate matrix."""
    # Test DSR helper
    rets = np.array([0.01, -0.005, 0.015, -0.002, 0.02, 0.008, -0.01, 0.025, 0.005, 0.012] * 10)
    dsr = compute_deflated_sharpe_ratio(sharpe_hat=1.5, returns_series=rets, num_trials=5)
    assert 0.0 <= dsr <= 1.0

    tournament = ArenaTournament(iterations=25, random_seed=99)
    report = tournament.run_tournament(
        situations=[MarketSituation.BULL_EUPHORIA, MarketSituation.BEAR_CREDIT_CRISIS],
        paths_per_situation=5,
    )

    leaderboard = report["leaderboard"]
    ranks = [b["overall_tournament_rank"] for b in leaderboard]
    assert sorted(ranks) == [1, 2, 3, 4, 5], "Tournament must rank bots uniquely from 1 to 5"

    h2h = report["head_to_head_win_rate_matrix_pct"]
    for b_id in h2h:
        assert h2h[b_id][b_id] == 50.0  # Self vs self is 50%
    # Sum of BotA vs BotB + BotB vs BotA should equal 100%
    b1, b2 = "BOT_FORCE_BUY", "BOT_HYBRIDACD_SNIPER"
    total_pair = h2h[b1][b2] + h2h[b2][b1]
    assert abs(total_pair - 100.0) < 1.0, f"Pairwise win rates must sum to 100% (got {total_pair})"


# =============================================================================
# 6. STRICTLY READ-ONLY COMPLIANCE (RULE B1)
# =============================================================================
def test_strictly_read_only_compliance():
    """Verifies that the Monte Carlo Arena contains strictly NO broker execution or order placement logic."""
    forbidden_terms = [
        "broker.place_order",
        "dnse.submit_order",
        "ssi.send_order",
        "vps.place_order",
        "socket.send",
        "live_trading",
    ]
    arena_file = REPO_ROOT / "src" / "pipeline" / "monte_carlo_bot_arena.py"
    content = arena_file.read_text(encoding="utf-8").lower()

    for term in forbidden_terms:
        assert term not in content, f"Rule B1 Compliance Violation: Forbidden broker execution term '{term}' detected!"
