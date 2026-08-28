# Live Crawl Run Log

Tracks live crawl execution status, evidence queries, and per-dataset decisions.
Separate from `claude-progress.md` / `gemini-progress.md` and `feature_list.json`.

## F001 — dim_symbol — 2026-08-27
- Symbols attempted: N/A (single-shot reference crawl, not per-symbol loop)
- Live run stdout:
    Authentication successful: Kiệt Trần Anh (silver)
    F001 dim_symbol: wrote 1751 rows to core.dim_symbol
- Post-run verification:
    core.dim_symbol count(*) = 1751
    Sample rows confirmed real (Vietnamese organ_name/exchange/industry_name, not placeholder)
    meta.crawl_progress: empty (expected — F001 doesn't write per-symbol progress rows)
- Code changes this session: none
- Note: symbol count (1751) is higher than the ~1525 recorded at F001's original 2026-08-11 verification — plausible listing drift, not investigated further; not blocking.
- Decision: continue to F002 (market_ohlcv_daily)

## F002 — market_ohlcv_daily (Full 2000–2026) — 2026-08-27
- Symbols attempted: 1751
- SQL result (pasted verbatim):
  dataset_name   status     n
0         F002    empty    33
1         F002  success  1718
- Core row count: 4,807,126 rows across 1,718 symbols (earliest: 2000-07-28, latest: 2026-08-27)
- Code changes this session: `src/crawlers/market_ohlcv.py` updated to fetch full historical depth via VCI source with fallback
- Decision: continue to F003 (vnstock_news)

## F003 — vnstock_news — 2026-08-28
- Symbols attempted: 1751
- Status: Completed using Sponsor tier (vnstock_news / vnstock_data).
- SQL result (pasted verbatim):
  dataset_name   status     n
0         F003    empty   201
1         F003  success  1550
- Core row count: 73,566 news rows across 1,550 symbols.
- Note: vnstock_news returns the most recent 50 articles per symbol.
- Decision: continue to F005 (fundamentals)

## F005 — fundamentals (Balance Sheet, Income Statement, Cash Flow, Ratio) — 2026-08-28
- Symbols attempted: 1751 (Full universe from core.dim_symbol)
- Status: Completed 100% using vnstock_data (Silver Sponsor package, tier verified live: Kiệt Trần Anh).
- SQL result (pasted verbatim):
  dataset_name   status     n
0         F005    empty    13
1         F005  success  1738
- Core row count: 156,337 total records in core.fundamentals:
  - balance_sheet: 39,018 rows (1,387 symbols)
  - income_statement: 39,061 rows (1,343 symbols)
  - cash_flow: 38,275 rows (1,330 symbols)
  - ratio: 39,983 rows (1,730 symbols)
- Historical Depth: 34 quarters (2018-Q1 to 2026-Q2) — confirmed maximum structured depth from vnstock_data upstream.
- Code changes this session:
  - `src/etl/db.py`: added `load_env()` helper for automatic .env loading.
  - `src/crawlers/fundamentals.py`: upgraded `melt_pivoted_statement()` to support both pivoted and melted schemas, handled non-equity EmptyResultError.
  - Updated all crawlers to use `db.load_env()` in `_authenticate()`.
  - Full test suite: 137 passed, 1 xfailed (138 collected); ruff and mypy clean.
- Next dataset / session: F006 (corporate_events) or F101/F102 (validation & point-in-time join).

