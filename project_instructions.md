# Project Instructions — VN Autonomous Trading System
https://github.com/Azure06072005/VESTA

This file merges general LLM-coding discipline (behavioral guardrails) with
domain-specific rules for a financial trading system. Read this before writing
any code. Merge with `AGENTS.md`, `conventions.md`, `architecture.md` in the
project harness — this file is the philosophy; those are the mechanics.

**Tradeoff:** these guidelines bias toward caution over speed, because this is
a system that moves real money and interacts with real regulation. That
tradeoff is not negotiable here, even for tasks that feel trivial.

---

## Part A — General Coding Discipline

### A1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly before implementing. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when the request is
  overengineered.
- If something is unclear, stop. Name what's confusing. Ask before guessing.

**Finance-specific addition:** in this domain, "I assumed X" is not a minor
caveat — an assumption about settlement timing, order type, or fee structure
can silently corrupt a backtest or misroute an order. Any assumption that
touches money, timing, or risk must be flagged explicitly, not folded into
the diff.

### A2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If it could be 50 lines instead of 200, rewrite it.

**Finance-specific addition:** do not build the execution layer, the LAM,
WebSocket feeds, or FIX connectivity before the underlying signal has been
backtested and shown to have edge. Infrastructure built ahead of a validated
signal is speculative complexity — the most expensive kind, because it's easy
to mistake for progress. Order of build = order of proof.

### A3. Surgical Changes
Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that *your* change made unused; leave
  pre-existing dead code alone unless asked.

**Finance-specific addition:** never touch risk-control logic (position
sizing, circuit breakers, order throttling) as a side effect of an unrelated
change. If a change to signal generation or data ingestion would require
touching risk code, stop and flag it — that's a scope violation, not a
convenience.

### A4. Goal-Driven Execution
Define success criteria. Loop until verified.

- "Add validation" → "write tests for invalid inputs, then make them pass"
- "Fix the bug" → "write a test that reproduces it, then make it pass"
- "Refactor X" → "ensure tests pass before and after"

For multi-step tasks, state a brief plan first:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

**Finance-specific addition:** "the backtest ran" is not a success criterion.
"The backtest ran, reproduces the same result on a second run with the same
seed, and the Sharpe/return numbers are computed the same way as the
benchmark paper cites them" is. Weak criteria in this domain don't just cause
rework — they cause false confidence in a system that risks capital.

---

## Part B — Domain Guardrails (Finance / Data / Trading Workflow)

### B1. Compliance and Regulatory Gate — Build Order, Not an Afterthought
Before any execution-layer code is written (order placement, order
amendment, order cancellation), confirm in writing:
- Is autonomous/algorithmic trading currently permitted under the broker
  relationship being used, and under what registration or disclosure?
- Are there active regulatory restrictions (e.g. suspensions on unmonitored
  robotic trading) in effect right now?

This is a **legal blocker**, not an engineering task, and it does not get
resolved by writing more code. If this hasn't been confirmed, execution-layer
work does not start — say so and stop, don't build "just in case it's fine."

### B2. Signal Before Infrastructure
Sequence, strictly:
1. **Backtest the hypothesis** on historical data, no live connectivity
   involved. Kill or confirm the claimed edge cheaply.
2. **Paper trade** against a sandbox/test API if the backtest holds.
3. **Build the execution layer** (REST/WebSocket/order routing/risk rails)
   only after 1 and 2 hold up.

Do not build caching layers, fallback chains, or multi-provider redundancy
until there is a proven signal worth protecting the uptime of.

### B3. Numbers Need a Source
Any benchmark, accuracy, F1, Sharpe ratio, or backtest result that appears in
code, comments, docs, or reports must be traceable to:
- a specific run you executed and can reproduce, or
- a specific cited source (paper/dataset), not a paraphrase of a vague
  memory of one.

Never let a plausible-looking number stand in for a computed one. If a metric
can't be sourced or reproduced, mark it `TODO: verify` rather than presenting
it as fact — a stray fabricated number in a finance report is a different
category of mistake than a stray fabricated number in a blog post.

### B4. Data Pipeline Discipline
- Every data fetch (price, fundamentals, news) needs an explicit
  freshness/TTL policy and a defined failure behavior — never fail silently
  into stale or fabricated data. A `DataNotFoundError` that halts trading is
  correct; a silent fallback to last-known-good without flagging it is not.
- Look-ahead bias check: any backtest must confirm that no feature uses
  information not actually available at that point in time (e.g. same-day
  news sentiment must be timestamped and lagged correctly, not fed in
  same-bar).
- Log data provenance (which tier — cache/primary/fallback — served each
  data point actually used in a decision) so any bad trade can be traced back
  to the data that caused it.

### B5. Risk Rails Are Non-Negotiable and Testable
- Position sizing, circuit breakers, and order throttling are treated like
  security code: reviewed, tested, and never modified as a side effect of
  other work (see A3).
- Every risk rail needs its own test that proves it actually halts trading
  under the condition it's meant to catch — "the code looks like it would
  stop" is not verification (see verification.md, Principle 10: only
  full-pipeline verification counts).
- Circuit-breaker and throttle logic should fail closed (stop trading) on
  ambiguous or missing data, never fail open.

### B6. One Feature, One Proof
Each unit of work in `feature_list.json` should be a single verifiable claim
about the system — e.g. "sentiment mean-reversion backtest on VN30
2020–2025 produces a Sharpe > X" — not a bundle of "build the pipeline."
A feature only moves to `passing` when its own verification command
succeeds, consistent with the project harness's existing rule.

---

## Working Agreement

- If a request would skip B1 or B2 (e.g. "just wire up the order execution
  now"), say so explicitly and ask whether the compliance/backtest gate has
  already been cleared elsewhere — don't silently comply or silently refuse.
- If asked to add a feature that isn't backed by a verifiable signal or a
  passed compliance check, flag it as speculative before building it.
- Every session should be able to answer: what was proven today, with what
  command, and what's the next thing to prove — not just what was written.