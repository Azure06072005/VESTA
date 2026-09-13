# Loop Verification: F006 — Corporate Events Crawler

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F006`
- **Feature Name:** Corporate Events Crawler (Dividends, Rights Issues, Splits, AGM)
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Events schema: `symbol VARCHAR`, `ex_date DATE NOT NULL`, `record_date DATE`, `event_type VARCHAR`, `ratio DOUBLE`, `cash_amount DOUBLE`.
  - Temporal Invariant: `ex_date` must be the effective trading date when price adjustments take effect.
  - Feeds into `core.price_adjustment_events` via adjustment factor calculation:
    $$P_{\text{adj}} = \frac{P_{\text{raw}} - \text{cash\_amount}}{1 + \text{ratio}}$$

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.corporate_events` in `d:/VESTA/db/vesta.duckdb`.
- **Downstream Adjustment Table:** `core.price_adjustment_events`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_corporate_events_crawler.py -v` passes.
- [x] **Gate 2 (Boundary):** Valid event schema; types correctly parsed.
- [x] **Gate 3 (Temporal):** `ex_date` precedes or equals `record_date`.
- [x] **Gate 4 (Distribution):** Sane dividend yields and split ratios.
- [x] **Gate 5 (Pipeline):** Integrated into pipeline.

## 4. Identified Defects & Remediation Log
- **CRITICAL DATA DEFECT IDENTIFIED (2026-09-12 Audit):**
  - **`core.price_adjustment_events` is currently EMPTY (0 rows)** in `vesta.duckdb`.
  - **Downstream Impact:** When `F102` calls `adjustments.apply_adjustment()`, because the adjustment events table has 0 rows, the join silently defaults to **raw unadjusted close prices**!
  - Consequently, any historical stock split or major bonus issue in `core.pit_events` appears as an artificial price collapse (e.g. -50%), inflating negative-sentiment returns.
  - **Remediation Plan:** A full run of `src/etl/adjustments.py` must populate `core.price_adjustment_events` from `core.corporate_events` before production live trading.

## 5. Verification Command & Evidence
```bash
python -c "import duckdb; con = duckdb.connect('db/vesta.duckdb', read_only=True); print('Adjustment events count:', con.execute('SELECT COUNT(*) FROM core.price_adjustment_events').fetchone()[0])"
```
- **Evidence:** `Adjustment events count: 0` -> Logged as critical retrospective finding.
