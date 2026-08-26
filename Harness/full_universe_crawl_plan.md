# Full-Universe Crawl — Detailed Instructions

Companion to `AGENTS.md` / `verification.md`. This document covers crawling
**every symbol** in `core.dim_symbol` (3,446 confirmed live as of the
2026-08-25 pilot double-check, see `DECISIONS.md`), not the 30-symbol
`scratch/pilot_symbols.txt` subset used by `scratch/staged_pilot_run.py`.

**Read this before starting.** This is a multi-hour run against a rate-
limited external API. Getting the batch sizing wrong either wastes hours
retrying rate-limit failures, or (worse) risks the account/IP getting
temporarily locked out by vnstock's community-tier limit.

---

## 0. Prerequisites checklist

- [ ] F001 (`core.dim_symbol`) already crawled — **it has been** (3,446
      rows confirmed live). No separate export/discovery step needed;
      `scratch/full_universe_run.py` reads the symbol list directly from
      `core.dim_symbol`.
- [ ] `db/vesta.duckdb` exists and schema is bootstrapped (any prior
      session's DB is fine — the script calls
      `migrations.run_all_migrations()` itself, which is idempotent).
- [ ] `VNSTOCK_API_KEY` is set for this session (see Step 1).
- [ ] You have several uninterrupted hours available, OR you're
      comfortable relying on the script's resumability (see Step 4) to
      run it across multiple sessions.
- [ ] Disk space: OHLCV + fundamentals + events for ~3,446 symbols is
      still small relative to typical disk budgets (this repo's own
      `verification.md` already calls for a `df -h` check before large
      fetches) — confirm you have a few hundred MB free, to be safe.

---

## 1. Why this is a multi-hour run (rate-limit math)

`src/etl/batch_orchestrator.py`'s own docstring confirms vnstock's
community-tier limit: **60 requests/minute**. Per-symbol API call counts,
confirmed by reading each crawler directly:

| Dataset | API calls per symbol | Source |
|---|---|---|
| F002 (OHLCV) | 1 | `crawlers/market_ohlcv.py` — single `.ohlcv()` call |
| F005 (fundamentals) | **4** | `crawlers/fundamentals.py`'s `run()` loops over `REPORT_TYPES` (income_statement, cash_flow, ratio, balance_sheet) |
| F006 (corporate events) | 1 | `crawlers/corporate_events.py` — single `.events()` call |

At 3,446 symbols, that's:

| Dataset | Total requests | Minutes at full 60/min rate | Minutes at 80% (safety margin) |
|---|---|---|---|
| F002 | 3,446 | ~57 | ~72 (1.2h) |
| F005 | 13,784 | ~230 | ~287 (4.8h) |
| F006 | 3,446 | ~57 | ~72 (1.2h) |
| **Total (sequential)** | | | **~7+ hours** |

**This is a STATED ASSUMPTION**, not a measured real-world run of this
exact script — it's a back-of-envelope estimate from confirmed call
counts and the confirmed rate limit. Actual time will vary with network
latency, retries, and how close to the limit you actually run. Treat 7
hours as a floor, not a guarantee.

`scratch/full_universe_run.py` (see Step 3) is pre-sized to run at ~80%
of the rate limit (48 req/min) to leave headroom for retries without
constantly bumping into 429s:
- F002/F006: `batch_size=40, delay=50s` → 40 calls / 50s ≈ 48/min
- F005: `batch_size=10, delay=50s` → 10 symbols × 4 calls / 50s ≈ 48/min

If you see failures clustering in a pattern that looks like rate-limiting
(not genuine empty/delisted symbols), **widen the delay**, don't shrink
the batch further — shrinking batch size without adding delay doesn't
reduce the request rate, it just changes how often the delay fires.

---

## 2. What NOT to change: date-range does not help

Per the earlier crawl-strategy discussion already on record (see
`progress_graph.json`'s `strategy-crawl` node): **date-range does not
reduce crawl time** — `market_ohlcv.run()` and friends make one API call
per symbol regardless of the requested date range; the vnstock endpoint
returns the full history in that one call. The only lever that actually
reduces total crawl time is **symbol count**. If you want a faster first
pass, reduce the symbol list (e.g. run the existing 30-symbol
`scratch/staged_pilot_run.py` again, or hand-curate a mid-sized subset) —
don't try to save time by narrowing the OHLCV date range.

---

## 3. Running it

### Step 1 — set the API key for this session

```powershell
$key = (Get-Content "$HOME\.vnstock\api_key.json" | ConvertFrom-Json).api_key
$env:VNSTOCK_API_KEY = $key
$env:PYTHONPATH = "src"
$env:PYTHONUTF8 = "1"
```

### Step 2 — start the full-universe run

```powershell
.venv\Scripts\python.exe scratch/full_universe_run.py --run-backtest
```

This will, in order:
1. Load all 3,446 symbols from `core.dim_symbol`.
2. Launch F003 + F004 (news) **in the background**, over all 3,446
   symbols, as separate OS processes — these do **not** block the rest
   of the script and keep running after it exits.
3. Run F002 → F005 → F006 **synchronously**, in that order, at the
   rate-limit-safe batch sizes described above. This is the ~7+ hour
   part.
4. Run F101 (validation — raises loudly and stops if referential
   integrity is broken) then F102 (point-in-time join) over all 3,446
   symbols.
5. Run F201's real backtest and print an honest `n` / `p-value` /
   `status` summary (because `--run-backtest` was passed).

If you'd rather not chain the backtest immediately (e.g. because you know
news won't have accumulated much yet during a single run), drop
`--run-backtest` and just run:

```powershell
.venv\Scripts\python.exe scratch/full_universe_run.py
```

### Step 3 — re-check the backtest later, as news accumulates

Since F003/F004 keep running in the background (and per DECISIONS.md,
news depth only accumulates forward and cannot be backfilled), re-check
progress periodically without re-crawling anything else:

```powershell
.venv\Scripts\python.exe scratch/full_universe_run.py --backtest-only
```

---

## 4. Resumability — interrupting and restarting

**Safe to `Ctrl+C` at any point.** Every crawl call is routed through
`src/etl/batch_orchestrator.py`'s `run_batched()`, which checks
`meta.crawl_progress` before each symbol and skips anything already
marked `success` or `empty`. Re-running the same command later:

- Does **not** re-crawl symbols already done.
- Does **not** re-crawl the 30 pilot symbols if you already ran
  `scratch/staged_pilot_run.py` earlier over the same dataset — they'll
  already show `success` in `meta.crawl_progress` and get skipped here
  too.
- Picks up exactly where it left off, batch by batch.

If a symbol keeps failing after retries (default `max_retry=3` in
`batch_orchestrator.run_batched()`), it's marked `failed` and skipped on
future runs unless you explicitly reset it in `meta.crawl_progress` (not
covered by this script — a manual DB edit if you ever need it).

---

## 5. Monitoring progress while it runs

In a second terminal, check `meta.crawl_progress` directly:

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, 'src')
from etl import db
con = db.connect()
print(con.execute('SELECT dataset_name, status, COUNT(*) FROM meta.crawl_progress GROUP BY 1,2 ORDER BY 1,2').df())
"
```

This shows, per dataset (F002/F005/F006/F003/F004), how many symbols are
`success`, `failed`, or `empty` so far — useful for confirming the run is
actually progressing and roughly on the estimated timeline from Step 1,
without needing to watch the console output continuously.

---

## 6. After it finishes

1. Confirm `out/meanreversion_report.json` has a real (not
   `insufficient_data`) result, or a much larger `n` than the earlier
   single-symbol VIC test run (`total_events_loaded=4`).
2. If `status=insufficient_data` even at full-universe scale: this is
   still an honest result, not a failure — it means the accumulated real
   news volume (which can only grow forward from whenever each symbol
   was first crawled, per the F003/F004 structural limitation already on
   record) isn't there yet. Let the background F003/F004 crawls keep
   running and re-check periodically with `--backtest-only`.
3. If `status=ok` with a real `n`, `p_value`, and `cohens_d`: bring the
   full `out/meanreversion_report.json` back for a decision on whether
   F201 is ready to move to `passing` — per B6, that decision should be
   made from the actual reported numbers, not assumed just because a run
   completed.

---

## 7. Files this instruction set assumes exist

- `scratch/full_universe_run.py` — the orchestrator (new, provided
  alongside this document).
- `src/etl/batch_orchestrator.py`, `src/etl/migrations.py`,
  `src/pipeline/validate_crossref.py`, `src/pipeline/pit_join.py`,
  `src/pipeline/backtest_meanreversion.py` — all already in the repo,
  unmodified by this document.