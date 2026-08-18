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


## Data engineering patterns

- **Raw-payload-preserving crawlers**: any crawler whose source API has a
  wide, source-specific, or unstable column set (F005 fundamentals, F006
  corporate events, F007 realtime snapshot) stores the FULL raw fetched
  row as a JSON blob (`data_json`/`detail_json`) alongside a small set of
  typed columns needed for querying/joining. New fields appearing in a
  future API response do not require a backfill or a schema migration —
  they're already captured in the JSON blob; only the typed columns need
  extending, and that's additive, not destructive.
  Source: F009 item 7 (2026-08-16) — formalizes a pattern already used
  ad hoc by F005/F006/F007, adopted specifically to make future
  enrichment-data additions safe without restarting or breaking an
  already-running pipeline.
  Applicability: any crawler with a wide/unstable/source-controlled
  schema. Crawlers with a small, stable, well-understood schema (F001
  dim_symbol, F002 OHLCV) are not required to follow this — typed columns
  are fine when the schema is genuinely simple and unlikely to drift.
  Expiry: none.
- **Schema changes that touch a PRIMARY KEY require a migration, not just
  an updated `CREATE TABLE`**: DuckDB cannot `ALTER` a table's primary key
  in place. Any change of this shape needs an entry in
  `src/etl/migrations.py` (create the new-shaped table, copy existing data
  in with a row-count verification, drop the old table, rename) — never
  just edit `configs/duckdb_schema.sql` and assume `CREATE TABLE IF NOT
  EXISTS` will handle it, since that only applies to genuinely new
  databases and silently no-ops against an existing one, leaving the old
  (wrong) shape in place.
  Source: F009 item 3 (2026-08-16) — the fundamentals PRIMARY KEY fix
  would have required dropping real, multi-hour-crawled data without
  this. Additive changes (a new nullable column) don't need this — a
  plain `ALTER TABLE ADD COLUMN` is sufficient (see item 5's
  `duplicate_of` column).
  Applicability: `configs/duckdb_schema.sql`, `src/etl/migrations.py`.
  Expiry: none.