## Project Overview

**Name (working):** Autonomous Trading System for the Vietnamese Equity Market — SLM + LAM Architecture

**One-line description:** A research-to-production pipeline that reads Vietnamese-language financial news and disclosures, cross-checks that signal against company fundamentals and macro data, and — if and only if the edge is proven — autonomously routes trades through Vietnamese brokerage APIs (DNSE, SSI), inside hard-coded risk limits.

### The core idea

Vietnam's stock market (HOSE + HNX) is retail-dominated and inefficient enough that news sentiment measurably moves prices in the short term — often overshooting and then reverting. Most of that signal is locked in Vietnamese-language text (news, disclosures, SBV announcements), which generic English-trained models handle poorly. The project's bet is that a **small, domain-tuned Vietnamese language model** (PhoBERT, fine-tuned on financial text) can extract that signal cheaply and accurately, and that an **agentic execution layer** can turn validated signal into disciplined, risk-bounded trades — rather than a human manually reading news and reacting emotionally.

### The three layers

1. **Signal layer (SLM)** — PhoBERT-based sentiment/topic classification on Vietnamese financial news, tuned on domain corpora (e.g. ViFinClass). Output: a sentiment vector per company/topic, not a trade decision.

2. **Validation layer (fundamentals + macro)** — Before acting on sentiment, the system pulls the company's actual financial health via `vnstock` (balance sheet, P/E, P/B, debt ratios) and macro context (interest rates, credit growth limits, FX). This is the layer that decides whether negative news is a real problem or a fadeable overreaction, and whether the macro backdrop supports the trade at all.

3. **Decision + execution layer (LAM)** — An agent that combines sentiment + fundamentals (optionally through an LSTM or similar model for price forecasting) into a "buy / sell / hold" intent, sizes the position against portfolio risk (VaR, available cash, foreign-ownership room), and — only after all of that — places, monitors, amends, or cancels orders via broker REST/WebSocket APIs (OAuth2/PKCE-secured).

### What makes this hard, specifically in Vietnam

- **Regulatory sensitivity**: Vietnamese regulators have actively restricted unmonitored "robotic" trading before; whether and how autonomous execution is permitted for your specific account/broker relationship is a live legal question, not a technical one.
- **Matching engine quirks**: the newer exchange infrastructure changed how ATO/ATC orders are prioritized and how "foreign room" is calculated in real time — get this wrong and orders get rejected or the room math desyncs.
- **Thin liquidity**: outside the top ~50 HOSE names, naive market orders can move the price against you — this pushes toward VWAP/TWAP-style order slicing rather than simple market orders.
- **Data reliability**: no single Vietnamese data provider is bulletproof, so the pipeline needs caching + fallback (scraper → archive DB) rather than a single point of failure.

### How the project is meant to be *built* (per the project instructions)

Not signal-and-execution-at-once. The build order is deliberately sequential and gated:

1. **Prove the signal exists** — backtest the sentiment/mean-reversion hypothesis on historical VN30 data with no live connectivity at all. If there's no measurable edge here, nothing downstream matters.
2. **Paper trade** — validate the same logic against a sandbox/test broker API before touching real capital.
3. **Confirm compliance** — explicitly resolve whether autonomous execution is permitted under your broker/registration before writing any order-placement code.
4. **Build execution + risk rails last** — order routing, circuit breakers, position throttling — as tested, untouchable infrastructure, not as the first thing built.

### Current state

Right now this is a **research report**, not a working system — the harness files in your project (`feature_list.json`, `AGENTS.md`, `verification.md`, etc.) are still scaffolding with `TODO`s. The most defensible first real feature to implement would be **Feature 1: backtest the news-sentiment mean-reversion hypothesis on historical VN30 data**, since every later architectural decision (whether to build the LAM at all) depends on whether that comes back positive.

Want me to draft that first feature's spec into `feature_list.json` so the harness has a concrete, verifiable starting point?
