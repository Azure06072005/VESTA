# Loop Verification: F002 — Market OHLCV Daily Crawler

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F002`
- **Feature Name:** Market OHLCV Daily Crawler
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Daily price bars per symbol from `core.dim_symbol`.
  - Schema: `symbol VARCHAR`, `time DATE`, `open DOUBLE`, `high DOUBLE`, `low DOUBLE`, `close DOUBLE`, `volume BIGINT`, `fetched_at TIMESTAMP`.
  - Candlestick Geometry Invariant:
    $$\min(open, close) \ge low \quad \land \quad \max(open, close) \le high \quad \land \quad close > 0$$
  - Idempotent upsert: Running multiple times on the same date range must not produce duplicate bars for `(symbol, time)`.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation & Update)
- **Table:** `core.market_ohlcv_daily` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** **5,178,766 daily bars**.
- **Freshness Update:** Updated to current date (Friday 2026-09-11), adding 5,799 stock bars.
- **Symbol Coverage:** 1,818+ symbols with historical coverage spanning 2000 to 2026.
- **Index Table:** `core.market_index_daily` contains 206,313 daily bars across domestic and global macro indices (VNINDEX, VN30, HNX-INDEX, `^VIX`, `DX-Y.NYB`, `^TNX`).

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_market_crawler.py -v` (7/7 pass).
- [x] **Gate 2 (Boundary):** Candlestick geometry invariant passes across 5.17M rows; zero NULL prices.
- [x] **Gate 3 (Temporal):** `time` is strictly session trading date; `fetched_at` >= session close.
- [x] **Gate 4 (Distribution):** Sane distribution across 26 years; accounts for historical price ranges.
- [x] **Gate 5 (Pipeline):** Live update script `scratch/runners/update_ohlcv_to_today.py` runs idempotently against `vesta.duckdb`.

## 4. Identified Defects & Remediation Log
- **Discovered Data Defect (2026-09-12 Audit):**
  - **29.10% of historical bars have `volume <= 0`**: These correspond to trading halts, illiquid trading days, or carried forward prices on inactive tickers.
  - **Downstream Remediation:** When computing trade returns or point-in-time joins in `F102`/`F201`/`F203`, a strict liquidity filter `volume > 0` must be enforced to eliminate artificial $0.00\%$ ties.

## 5. Verification Command & Evidence
```bash
python -c "import duckdb; con = duckdb.connect('db/vesta.duckdb', read_only=True); print('OHLCV Total Rows:', con.execute('SELECT COUNT(*) FROM core.market_ohlcv_daily').fetchone()[0]); print('Max Date:', con.execute('SELECT MAX(time) FROM core.market_ohlcv_daily').fetchone()[0])"
```
- **Evidence:**
  - `OHLCV Total Rows: 5178766`
  - `Max Date: 2026-09-11` (Friday before current date).
