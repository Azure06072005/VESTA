# Conventions — VESTA

Only rules with a source (why), applicability (when), and expiry (when to
remove) belong here. Audit each entry when its expiry condition is met.

## Naming
- Modules named after what they produce, not how (`vnstock_market.py`, not
  `fetch_data_v2.py`).
  Source: readability for future sessions picking a module cold.
  Applicability: all files under `crawlers/`, `pipeline/`, `models/`.
  Expiry: revisit if module count exceeds ~15 and a sub-package split is
  needed.
- Feature IDs follow `F0xx` crawlers, `F1xx` validation/join, `F2xx` proof
  backtests, `F3xx` model layer, `F4xx` deployment, `F9xx` execution
  (blocked tier).
  Source: `feature_list.json` design (see chat history / DECISIONS.md).
  Applicability: `feature_list.json` only.
  Expiry: none — this is the permanent numbering scheme.

## File/folder layout rules
- One crawler = one data source = one file. Never merge two sources into one
  module even if their output schema matches (e.g. F004 vnstock News and
  F005 cafef stay separate).
  Source: they fail independently (API vs scrape) and carry different
  legal/ToS obligations.
  Applicability: `crawlers/`.
  Expiry: none.
- `data/` and `out/` (except fixtures) are gitignored. Never commit Parquet
  or model checkpoints to the repo.
  Source: repo size + local-only hardware workflow.
  Applicability: whole repo.
  Expiry: none, unless a remote artifact store is introduced later
  (log that as a DECISIONS.md entry if it happens).

## Error handling pattern
- Data-layer failures (crawler timeout, schema violation, missing period)
  fail loudly — raise, log, non-zero exit. Never silently substitute stale
  or synthetic data in `crawlers/` or `pipeline/validate.py`.
  Source: a silently-substituted bad data point corrupts a backtest
  invisibly; loud failure is cheaper to debug than a wrong Sharpe ratio.
  Applicability: `crawlers/`, `pipeline/`.
  Expiry: none.
- `execution/` (once unblocked) must fail **closed** — any ambiguous state
  halts trading, never defaults to "proceed."
  Source: risk-rail requirement, see `PROJECT_INSTRUCTIONS.md` B5.
  Applicability: `execution/` only.
  Expiry: none.

## Testing pattern
- Tests live in `tests/`, mirroring the source tree 1:1
  (`crawlers/vnstock_market.py` → `tests/test_vnstock_market.py`).
  Source: keeps "what covers this file" a lookup, not a search.
  Applicability: whole repo.
  Expiry: none.
- Every crawler test includes at least one idempotency assertion (re-run on
  same range produces identical output) and one schema assertion.
  Source: crawlers are the most common source of silent drift in a data
  pipeline; idempotency is cheap to test and catches most of it.
  Applicability: `tests/test_*crawler*.py`.
  Expiry: none.
- Statistical/backtest code (`pipeline/backtest_meanreversion.py`) tests for
  **reproducibility** (same input → bit-identical output), not just "runs
  without error."
  Source: PROJECT_INSTRUCTIONS.md B3 — numbers need a source and must be
  reproducible, not just plausible.
  Applicability: `pipeline/`, `models/evaluate.py`.
  Expiry: none.
