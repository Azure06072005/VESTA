# Progress Log (Claude sessions)

Update this at the end of every session (Principle 5 & 12). This is what the
next session reads to avoid starting from zero.

## Session 1 — 2026-08-09
- Completed: harness fully specified (no application code yet). Wrote
  `PROJECT_INSTRUCTIONS.md` (Karpathy-style coding discipline merged with
  finance/data domain guardrails — compliance gate, signal-before-
  infrastructure ordering, sourced-numbers rule, risk-rail testing rule).
  Wrote detailed `feature_list.json` (F001-F005 crawlers, F101-F102
  validation/join, F201/F302 proof backtests, F301 model fine-tune,
  F401/F402 deployment, F901/F902 blocked execution tier). Filled in
  `architecture.md` (system description, full folder tree with per-file
  descriptions, agent-role notes), `conventions.md` (naming, layout, error
  handling, testing rules — each sourced/scoped/expiring), `verification.md`
  (concrete pip/pytest/ruff/mypy commands + GPU VRAM budget check),
  `DECISIONS.md` (7 entries logging naming, dual news source, sequencing,
  model size choice, execution-layer blocking, data format, agent division
  of labor).
- In progress: none — this was documentation/harness work only.
- Blocked: F901 (broker compliance confirmation) — unresolved, blocks all of
  the F9xx execution tier. Not blocking current work (F001-F402 don't
  depend on it).
- Next session should: run `./init.sh` once dependencies are chosen and
  pinned in `requirements.txt` (not yet written), then implement F001
  (vnstock market data crawler) end-to-end with its own test file per
  `verification.md`, and stop there — do not start F002 in the same
  session per WIP=1 (AGENTS.md Hard Constraints).

## Session 3 — 2026-08-11
- Completed: F000 (env/schema bootstrap) — passing. init.sh: pytest 3/3,
  ruff clean, mypy --strict clean. Real user API key handling established
  (env var only, never hardcoded/committed) after two live keys were
  accidentally pasted into chat — both flagged for rotation.
- In progress: F001 (dim_symbol) — implemented against schema confirmed
  live by the user running discover_vnstock_schema.py against
  vnstock==4.0.5 with a real key: `Reference().equity.list_by_exchange()`
  joined with `Reference().industry.sectors()` on `symbol`. 9 tests pass,
  1 test (delisted_date non-null) is `xfail(strict=True)` — vnstock's
  unified API does not expose delisted symbols at all (3 call shapes
  tried live, all failed; see DECISIONS.md). F001 is `active`, not
  `passing`, until a real delisted-symbol source is found and logged.
  Also corrected: an unverified prior "testing report" claimed an
  `Insights.ranking.gainer()` call for F007 and specific row/column
  shapes for F001/F002/F005 — cross-checked everything against the
  installed package; F001/F002/F005 method names were real, `Insights`
  was hallucinated (confirmed absent, `"Insights" in dir(vnstock) ==
  False`, live). F007 stays `not_started`.
- Blocked: F001's delisted_date gap (needs a decision + alternative
  source, e.g. a scraped delisted registry — not yet chosen). F901 (broker
  compliance) — unrelated, still open, doesn't block current work.
- Next session should: decide + implement an alternative delisted-symbol
  source for F001 (own DECISIONS.md entry), OR move to F002 (Market OHLCV)
  if the delisted gap is accepted as a documented known-limitation for now
  — confirm with Tran Dieu before choosing. Per WIP=1, do not start F002
  code until F001's open question is explicitly resolved one way or the
  other in DECISIONS.md.

## Session 4 — 2026-08-12
- Completed: F001 delisted_date gap formally accepted by Tran Dieu
  (DECISIONS.md entry: no external scraper, "Simplicity First" guardrail,
  revisit only if F201 shows survivorship bias skews the backtest).
  F000 and F001 moved to `passing` in feature_list.json — legitimate under
  conventions.md's "encode gaps honestly" principle, since the gap is
  still enforced via `xfail(strict=True)`, not silently dropped.
- Completed: F002 (Market OHLCV) implemented — `Market().equity(symbol)
  .ohlcv(...)` confirmed as a real method; column-name assumption
  (`time/open/high/low/close/volume`) flagged as UNCONFIRMED pending a
  live discovery run, not silently trusted. 6 tests written, all passing
  against synthetic data; ruff/mypy clean.
  - CORRECTION: gemini-progress.md Session 1 claimed F002's schema was
    "verified against live API," but the "Data Testing Samples" shown
    were byte-for-byte identical to this session's synthetic test
    fixtures (_sample_raw_df) — not a real discover_ohlcv_schema.py run.
    Flagged to Tran Dieu; recommended F002 be reverted to `active` in
    feature_list.json until a genuine live discovery run happens.
- Completed: F005 rewritten from scratch after a genuine live discovery
  run (this one real, output pasted back by Tran Dieu) revealed the
  original column-alias assumption was wrong — vnstock returns a PIVOTED
  frame (rows=line items, columns=period labels like '2026-Q1'), not
  one-row-per-period. New melt_pivoted_statement() handles this
  correctly: 10/10 tests pass, ruff clean, mypy --strict clean.
- Resolved: balance_sheet's live empty-response issue — formally accepted
  by Tran Dieu as a real API gap (DECISIONS.md), not a bug; crawler
  correctly fails loudly rather than silently substituting data.
- Still blocked: DISCLOSURE_LAG_DAYS=45 remains an unsourced placeholder.
  Tran Dieu explicitly declined to accept it without real research into
  Vietnamese quarterly disclosure-deadline norms. F005 stays `active`,
  not `passing`, until this is resolved with a sourced number.
- Next session should: either (a) research DISCLOSURE_LAG_DAYS with a
  real source (Vietnamese quarterly disclosure-deadline regulations,
  cross-checked against real period_end -> publish-date pairs) and close
  out F005, or (b) move to F006/other unblocked work and leave F005 open
  — confirm with Tran Dieu. Also outstanding: confirm whether F002 was
  reverted to `active` per the correction above. Per WIP=1, don't start
  new feature code until the F005 path is decided one way or the other.

- Resolved: F002 verification. Live run of discover_ohlcv_schema.py confirmed the vnstock .ohlcv() endpoint returns exactly ['time', 'open', 'high', 'low', 'close', 'volume']. RAW_COLUMN_ALIASES works correctly, assumption removed, F002 marked as passing.

- Resolved: F006 (Corporate events crawler) marked passing after live discovery script verified schema and tests cleanly pass.

- Resolved: F008 (Retry/reconciliation module) marked passing after test suite passed.

- Resolved: F003 (vnstock news crawler) marked passing after test suite passed and schema was verified live.

## Session 5 — 2026-08-25
- Completed (harness audit): re-verified F001/F005/F006 against a fresh
  clone of the pushed repo after a Gemini session claimed these three had
  failed a live pilot double-check. Confirmed crawler code was
  byte-for-byte unchanged between the failing and passing
  scratch/double_check_summary.json runs -- root cause was a stale
  committed test artifact (an earlier double_check_runner.py version
  querying a nonexistent event_title column), not a real crawler bug.
  DECISIONS.md and feature_list.json evidence updated accordingly (see
  2026-08-25 DECISIONS.md entry). requirements.txt gap found and fixed
  (missing requests/beautifulsoup4/types-requests for F004).
- In progress: F201 (PROOF: sentiment mean-reversion backtest). Resolved
  both previously-open design questions (f201-open1 scoring rule,
  f201-open2 sample-size sufficiency) via explicit clarifying questions
  before writing code, per this project's stated preference. Implemented
  src/pipeline/sentiment_lexicon.py (hand-built VN financial keyword
  lexicon, explicitly flagged as an unsourced stated assumption after a
  web search found no citable existing VN finance-specific lexicon) and
  src/pipeline/backtest_meanreversion.py (paired t-test on return_t30 vs
  return_t5, per-regime breakdown, Cohen's d, MIN_SAMPLE_SIZE=10 honesty
  gate that reports status="insufficient_data" instead of computing a
  statistic on too few events). tests/test_meanreversion_stats.py: 16
  tests against synthetic fixtures -- an engineered-effect fixture (must
  detect p<0.05) AND a null-effect control fixture (must NOT detect an
  effect), small-sample insufficient_data guard, NULL-price exclusion
  (not imputation), and bit-identical-report-on-rerun reproducibility.
  Full suite: 137 passed, 1 xfailed (up from 121+1); ruff check src
  tests: All checks passed; mypy src tests --ignore-missing-imports:
  Success on 36 source files. CLI --dry-run verified end-to-end.
- Blocked: F201 is `active`, not `passing` -- the pipeline is proven
  correct on synthetic data but has NOT yet been run against real
  crawled core.pit_events data (per B6, a feature needs its actual real
  proof, not just a working pipeline). Real news volume is currently
  thin (scratch/vic_crawl_report.json shows ~1-4 items/symbol/crawl) --
  a meaningful real run likely needs either more pilot-universe crawl
  cycles to accumulate news, or the full ~1800-symbol crawl, before a
  real n large enough to trust shows up.
- Next session should: run `python -m pipeline.backtest_meanreversion
  --report out/meanreversion_report.json` (no --dry-run) against
  whatever real core.pit_events data exists, report the actual n/p-value/
  effect-size honestly (including if it's "insufficient_data" still),
  and only move F201 to `passing` once a real result -- of any kind -- is
  reported. If n is still too thin, consider running the pilot crawl
  again or expanding the pilot symbol list to accumulate more real news
  before re-attempting.

<!--
Template for future entries:

## Session N — YYYY-MM-DD
- Completed: F0xx (name) — all tests passing, evidence: commit <hash>
- In progress: F0yy (name) — what's done, what's left
- Blocked: (dependency / decision needed, or "none")
- Next session should: <one concrete next action>
-->