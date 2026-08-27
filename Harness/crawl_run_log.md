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


