"""src/arena/bot_registry.py

F501 bot registry: botID | strategyID | strategy details | AImodel.
Spec-only, no order logic (Rule B1 strictly compliant).
"""
from __future__ import annotations

import csv
import pathlib
from typing import Dict, List, Tuple

# id: (role, tier, name, details). Tiers: price=F002, news=F003/F004, fund=F005/F006, macro=F203/F007, base=baseline
S: Dict[str, Tuple[str, str, str, str]] = {
    "S01": ("SIGNAL", "price", "TSMOM 12-1", "ENTRY: buy top-decile 12m-minus-1m return (Jegadeesh-Titman 1993); rebalance monthly; exit when rank leaves top 30%"),
    "S02": ("SIGNAL", "price", "ST reversal 5d", "ENTRY: buy bottom-decile 5-day return (De Bondt-Thaler / Lehmann); exit t+10 or +5% target"),
    "S03": ("SIGNAL", "price", "SMA 50/200 trend", "ENTRY: close>SMA200 and SMA50>SMA200 (Faber 2007); exit on close<SMA200"),
    "S04": ("SIGNAL", "price", "Donchian 20d breakout", "ENTRY: close>20d high; exit close<10d low"),
    "S05": ("SIGNAL", "price", "RSI(14) oversold", "ENTRY: RSI14<30 and close>SMA200; exit RSI14>55"),
    "S06": ("SIGNAL", "price", "Bollinger reversion", "ENTRY: close<lower band(20,2); exit at middle band"),
    "S07": ("SIGNAL", "price", "Low volatility", "ENTRY: lowest-quintile 60d realized vol (Ang et al 2006); monthly rebalance"),
    "S08": ("SIGNAL", "price", "Volume surge breakout", "ENTRY: volume>3x 20d avg and close up>2%; exit trailing 7% stop"),
    "S10": ("SIGNAL", "price", "Limit-down rebound", "ENTRY: after >=1 floor-hit session (-7% HOSE) with volume dry-up; exit t+5. Must respect T+2.5 lock"),
    "S11": ("SIGNAL", "news", "Negative-sentiment dip buy", "ENTRY: sentiment<-z1.5 then t+5 dip; hold to t+30 (VESTA F201 hypothesis)"),
    "S12": ("SIGNAL", "news", "Positive-sentiment momentum", "ENTRY: sentiment>+z1.5 with price confirmation; exit t+10"),
    "S13": ("SIGNAL", "news", "Sentiment-shock fade", "ENTRY: fade |sentiment z|>2 overreaction after 1 session; exit t+5"),
    "S17": ("SIGNAL", "fund", "Magic Formula", "ENTRY: rank earnings yield + return on capital (Greenblatt); annual rebalance; uses get_as_reported()"),
    "S18": ("SIGNAL", "fund", "PEAD", "ENTRY: top-quintile earnings surprise at available_at (Bernard-Thomas 1989); hold 40 sessions"),
    "S19": ("SIGNAL", "fund", "Dividend ex-date run-up", "ENTRY: buy 10 sessions before F006 ex-right date for cash-dividend events; exit before ex-date"),
    "S20": ("SIGNAL", "fund", "Share issue/bonus drift", "ENTRY: F006 share-issue/bonus announcement; exit t+20; use adjusted prices only"),
    "S21": ("SIGNAL", "fund", "Insider trade follow", "ENTRY: net insider buying (F006 MAJOR_SHAREHOLDER_TRADING); exit t+30"),
    "S14": ("FILTER", "news", "Attention-spike filter", "FILTER: skip names with news count>3x 30d average (Barber-Odean attention effect)"),
    "S15": ("FILTER", "news", "Rumor gate", "FILTER: require source weight W>=0.70 and inconsistency V<=0.35 (HybridACD gate)"),
    "S16": ("FILTER", "fund", "Piotroski quality", "FILTER: Piotroski F-score>=7 (Piotroski 2000) from F005 income/cash-flow/ratio"),
    "S22": ("FILTER", "macro", "Regime gate", "FILTER: trade only in risk-on regime per F203; else flat"),
    "S23": ("FILTER", "macro", "Liquidity filter", "FILTER: min 20d avg traded value; F007 quotes used only for spread sanity (history accumulates forward)"),
    "S09": ("OVERLAY", "price", "Vol-target sizing", "SIZE: target 15% annual vol via ATR sizing (Moreira-Muir 2017); cap 25% NAV per symbol"),
    "S24": ("OVERLAY", "macro", "Bear-regime cash rotation", "SIZE: gross exposure x0.3 in bear regime"),
    "S25": ("BASELINE", "base", "Equal-weight 1/N", "BASELINE: equal-weight VN30, monthly rebalance"),
    "S26": ("BASELINE", "base", "Buy-and-hold VN30", "BASELINE: buy-and-hold VN30 constituents"),
}

AI_ROLE: Dict[str, str] = {
    "price": "Meta-labeling GBM on F002 features gates each entry (Lopez de Prado 2018)",
    "news": "PhoBERT-base sentiment (F301) replaces rule-based scorer; blocked until F201 passing",
    "fund": "Classifier on F005 line items predicts t+60 relative return; trade top decile",
    "macro": "Markov-switching/HMM regime probability (F203) replaces threshold gate",
}

COMMON: str = " || COMMON: long-only, T+2.5 sell lock, +/-7% HOSE limit, 25% NAV cap, fees+tax+slippage per F501"


def ids(role: str) -> List[str]:
    return [k for k, v in S.items() if v[0] == role]


def combos() -> List[Tuple[str, ...]]:
    sig, base = ids("SIGNAL"), ids("BASELINE")
    out: List[Tuple[str, ...]] = [(s,) for s in sig + base]
    out += [(s, f) for s in sig for f in ids("FILTER")]
    out += [(s, f, "S09") for s in sig for f in ("S15", "S16", "S22")]
    return out


def details(c: Tuple[str, ...]) -> str:
    return " | AND | ".join(f"{S[k][2]}: {S[k][3]}" for k in c) + COMMON


def ai_text(c: Tuple[str, ...]) -> str:
    tier = S[c[0]][1]
    t = AI_ROLE[tier]
    return t + ("; + HybridACD V-score filter" if "S15" in c else "")


def build() -> List[Tuple[str, str, str, str, str]]:
    cs = combos()
    rows: List[Tuple[str, str, str, str, str]] = []
    # 1. Non-AI bots
    for i, c in enumerate(cs, 1):
        rows.append((f"BOT-N{i:03d}", "+".join(c), details(c), "no", ""))
    # 2. AI Twins
    n = 0
    for c in cs:
        if S[c[0]][0] == "BASELINE":
            continue
        n += 1
        rows.append((f"BOT-A{n:03d}", "+".join(c), details(c), "yes", ai_text(c)))
    return rows


def export_registry_csv(output_path: str = "out/f501_bot_registry.csv") -> int:
    p = pathlib.Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = build()
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["botID", "strategyID", "strategy_details", "AImodel", "ai_role"])
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    count = export_registry_csv("out/f501_bot_registry.csv")
    print(f"{count} bots written to out/f501_bot_registry.csv")
