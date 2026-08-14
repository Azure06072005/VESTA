# Design Decisions — VESTA

Newest at the top. Don't reverse any of these without a new, stated reason.

## 2026-08-11: Accept delisted symbol gap in F001 (core.dim_symbol)
- Reason: The `vnstock` Unified API does not natively expose delisted symbols. Attempting to scrape alternative sources introduces speculative complexity and brittle network dependencies (e.g., VNDirect API timeouts) that violate the "Simplicity First" and "Signal Before Infrastructure" guardrails.
- Accepted Limitation: `delisted_date` will remain `NULL` in `core.dim_symbol`. The F001 verification rule encoding this survivorship bias check remains as an intentional `xfail`. F001 will be marked `passing` despite the gap to unblock downstream development. We will reconsider building a scraper only if F201 validation indicates that survivorship bias significantly inflates the backtest results.
- Constraint: The test `test_delisted_symbol_has_non_null_delisted_date` retains its `xfail` status to explicitly track this accepted limitation.

## 2026-08-11: Build order within not_started backlog — F001/F002/F005 before F003/F004
- Reason: an unverified testing report (from another agent/session, not
  independently confirmed) flagged that vnstock's Company.news endpoint
  returns intermittent HTTP 500s from the underlying provider, while the
  Reference/Market/Fundamental endpoints used by F001/F002/F005 were
  confirmed live and stable via direct package introspection
  (vnstock==4.0.5) in this session. Building the stable crawlers first
  avoids blocking early pipeline progress on a source known to be flaky.
- Verified independently in this session: `Reference.equity.list()`,
  `Reference.equity.list_by_exchange()`, `Reference.industry.sectors()`,
  `Market.equity(symbol).ohlcv(...)`, and
  `Fundamental.equity(symbol).income_statement/balance_sheet/cash_flow/ratio(...)`
  all exist as real callables in the installed package.
- NOT verified, do not treat as fact until confirmed by a live call: the
  reported `Insights.ranking.gainer()` call for F007 -- no `Insights` class
  exists anywhere in the installed vnstock package (checked via
  `pkgutil.walk_packages`, no module or class matching
  insight/ranking/screener/gainer/loser found). F007 stays `not_started`
  and must not move to `active` until this is confirmed against a real
  API call, per PROJECT_INSTRUCTIONS.md B3 (numbers/claims need a source).
- Rejected: taking the report's row/column shapes and sample data as fact
  and writing them into feature schemas -- rejected because they could not
  be reproduced or verified from this session's environment (network
  sandbox blocks vnstock's API domain).
- Constraint: this does not change the dependency graph (F003/F004 still
  only depend on F001) -- it is a build-order preference, not a state
  change. Re-run `discover_vnstock_schema.py` against a live key before
  either F003/F004 or F007 move to `active`.
- Reason: "Vietnamese Equity Sentiment-Triggered Agent" is legible in a repo
  name/README and doesn't overclaim (no "autonomous," no "LAM").
- Rejected: PHOALPHA (too playful for a repo that may get external review),
  MERA (good philosophy-encoding name, kept as an alternate/internal
  codename for the "signal-before-execution" discipline if useful later).
- Constraint: none — naming only.

## 2026-08-09: Dual news source — vnstock News AND cafef.vn, as separate crawlers
- Reason: different failure modes (API vs scrape) and different legal/ToS
  obligations; bundling them would let one break silently drag the other's
  pipeline state down with it.
- Rejected: single unified "news crawler" module — rejected because schema
  agreement doesn't imply operational agreement (rate limits, robots.txt,
  auth all differ).
- Constraint: both crawlers must emit the same output schema so downstream
  `pit_join.py` can union them without source-specific branching.

## 2026-08-09: Sequencing — cheap rule-based sentiment scorer before PhoBERT fine-tune
- Reason: F201 (rule-based backtest) must show a statistically significant
  effect before F301 (PhoBERT fine-tune) is allowed to start. If the cheap
  scorer shows nothing, fine-tuning a better scorer for the same signal is
  wasted work.
- Rejected: fine-tune PhoBERT first "since it'll be more accurate anyway" —
  rejected because accuracy of the scorer is irrelevant if the underlying
  mean-reversion effect doesn't exist in the data.
- Constraint: F301 may not move to `active` while F201 is not `passing`.

## 2026-08-09: PhoBERT-base, not PhoBERT-large, for local fine-tuning
- Reason: target hardware is an RTX 3060 with 6GB VRAM. PhoBERT-base (110M
  params) fine-tunes comfortably at fp16; PhoBERT-large (335M) is feasible
  only with aggressive gradient accumulation, adding fragility for uncertain
  benefit until base is proven to be the bottleneck.
- Rejected: PhoBERT-large from the start — rejected on hardware-fit grounds,
  not accuracy grounds; revisit only if F301/F302 shows base is capacity-
  limited (i.e. underfitting, not just noisy).
- Constraint: any future move to `-large` needs its own DECISIONS.md entry
  with the underfitting evidence attached.

## 2026-08-09: Execution layer (F901/F902) is `blocked`, not `not_started`
- Reason: autonomous order placement in the Vietnamese market has an
  unresolved compliance question (regulators have previously suspended
  unmonitored robotic trading activity) — this is a legal gate, not an
  engineering one, and no amount of code progress resolves it.
- Rejected: building execution code in parallel "to save time later" —
  rejected because code built against an unconfirmed compliance assumption
  is a liability, not a head start.
- Constraint: F902 (and anything under `execution/`) may not move to
  `active` until F901 is `passing`, and F901's evidence must be a real
  document/correspondence, not a code artifact.

## 2026-08-09: Data lake format — Parquet, not CSV, for `data/`
- Reason: partitioned Parquet is far cheaper to query incrementally under a
  16GB RAM budget than loading large CSVs into memory; CSV is kept only for
  small human-readable reports in `out/`.
- Rejected: SQLite/Postgres — rejected for now as unnecessary operational
  overhead for a single-machine, single-user local pipeline; revisit if
  concurrent access or multi-user querying becomes a real need.
- Constraint: any new crawler must write Parquet by default.

## 2026-08-09: Agent division of labor
- Reason: Gemini (chat) is used for primary AI research (literature,
  statistical design, interpretation); Gemini Antigravity is the primary
  coding agent implementing `feature_list.json`; Claude is used for harness
  upkeep, documentation, and cross-checking decisions.
- Rejected: single-agent workflow — rejected because research and
  implementation benefit from different strengths, and keeping progress
  logs separate (`claude-progress.md` / `gemini-progress.md`) avoids one
  agent silently overwriting another's session notes.
- Constraint: both progress files must be read at the start of any session,
  regardless of which agent is running it.

## 2026-08-12: F005 balance_sheet API gap — accepted as real, not a bug
- Reason: `Fundamental().equity(symbol).balance_sheet(period='quarter')`
  returned a completely empty DataFrame against a live key
  (discover_fundamentals_schema.py run, 2026-08-12). income_statement,
  cash_flow, and ratio all returned real pivoted data for the same
  symbol/call pattern -- this looks like a genuine gap in vnstock's
  balance_sheet endpoint, not a parameter or auth mistake on our side.
- Decision: treat this as an accepted, real API limitation. F005's
  balance_sheet crawl continues to fail loudly (ValueError on empty
  fetch) per conventions.md's error-handling pattern -- this is correct
  behavior, not something to catch and paper over. income_statement,
  cash_flow, and ratio are unaffected and can proceed to `passing`
  independently of this gap.
- Rejected: silently returning an empty/synthetic balance_sheet result to
  let the crawler "succeed" -- rejected per B4 (never fail silently into
  fabricated data).
- Constraint: if a future session finds balance_sheet works for other
  symbols/args, log that as its own DECISIONS.md entry with the working
  call shape -- don't just quietly change the code.

## 2026-08-12: F005 DISCLOSURE_LAG_DAYS=45 — NOT yet accepted, blocking
- Status: still an open placeholder guess in
  src/crawlers/fundamentals.py, not backed by any source. Explicitly
  declined to rubber-stamp this without real research (Vietnamese
  disclosure-deadline regulations for quarterly financial statements,
  ideally cross-checked against a few real period_end -> actual
  publish-date pairs from cafef.vn or a similar source).
- Constraint: F005 cannot move to `passing` until this is resolved with
  a sourced number (or a stated methodology for computing it per-symbol
  rather than a single constant). This directly affects F102's
  look-ahead-bias join correctness -- an under-estimated lag would leak
  future information into the backtest.
## 2026-08-12: F005 DISCLOSURE_LAG_DAYS resolved — 30 days, sourced
- Reason: Circular 96/2020/TT-BTC requires quarterly financial reports
  submitted within 20 days of quarter-end. Real-world compliance
  regularly lags this: HOSE has received dozens of extension requests in
  a single year (191 companies requesting annual-filing extensions per
  SSC data), with a documented case (REE) requesting its Q4 filing
  deadline pushed to 30 days. 30 days = the 20-day regulatory floor plus
  a buffer covering the commonly observed extension pattern.
- Sources: Circular 96/2020/TT-BTC (quarterly disclosure deadline);
  VietnamPlus reporting on HOSE extension-request volume and the REE
  case; Circular 200/2014/TT-BTC (used only to confirm this 30-day figure
  is specific to quarterly filings, not the separate 90-day annual-report
  deadline, which does not apply here).
- Rejected: the original 45-day placeholder — that number was actually
  closer to the semi-annual disclosure deadline (5 days after auditor
  review, capped at 45 days from half-year end), which does not apply to
  quarterly filings and was never sourced in the first place.
- Rejected: the strict 20-day regulatory deadline with no buffer —
  rejected because extension requests are common enough in practice
  (documented, not rare) that 20 days would systematically underestimate
  real availability for a meaningful fraction of filings, and
  underestimating this lag is the more dangerous failure mode for F102's
  look-ahead-bias join (leaks future data) versus overestimating it
  (discards a few real data points).
- Constraint: this is still a single constant applied uniformly across
  symbols and periods, not a real per-filing disclosure date. If F102 or
  F201 results look sensitive to this assumption, revisit with
  per-symbol/per-period data before trusting backtest conclusions built
  on it.

## 2026-08-13: F004 accepts page-1-only cafef.vn crawl (~28 recent items/run)
- Reason: cafef.vn's per-symbol news page server-renders only the first
  page of articles; further items load via `javascript:LoadNext()`
  (client-side AJAX). Reverse-engineering that endpoint was rejected on
  ToS grounds -- robots.txt disallows /Ajax/, and the underlying endpoint
  is very likely under that path.
- Decision: F004 crawls page 1 only, per run. Full history is not a
  one-shot backfill -- it accumulates over repeated scheduled runs via
  the same idempotent dedup-by-source_url pattern F003 uses.
- Also logged: the URL cafef.vn/du-lieu/hose/{ticker}-tin-tuc.chn looks
  like a per-symbol news page but is JS/AJAX-rendered and returns no
  articles to a plain HTTP GET -- the working URL is
  cafef.vn/du-lieu/tin-doanh-nghiep/{ticker}/Event.chn.
- Constraint: article body text is NOT fetched by F004 (would require a
  second request per article) -- core.news.body is NULL for cafef-sourced
  rows. If body text becomes necessary for sentiment scoring, that's a
  separate feature, not a silent scope-creep into F004.