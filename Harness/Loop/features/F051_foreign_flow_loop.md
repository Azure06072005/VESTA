# Loop Verification: F051 — Foreign Investor Flow Crawler

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F051`
- **Feature Name:** Foreign Investor Flow Crawler (`core.market_foreign_flow_daily`)
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Daily foreign investor activity per symbol: `buy_volume`, `sell_volume`, `net_volume`, `foreign_room`.
  - Invariant under Rule B3/B4: **Volume-only schema**.
  - Elimination of fabricated value columns (`buy_value`, `sell_value`, `net_value`) which cannot be directly sourced from CafeF exchange dumps.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.market_foreign_flow_daily` in `d:/VESTA/db/vesta.duckdb`.
- **Schema Enforcement:** Strict volume-only DDL integrated into `configs/duckdb_schema.sql`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_cafef_foreign_flow.py -x` (2/2 pass).
- [x] **Gate 2 (Boundary):** Zero fabricated monetary columns; volume non-negativity enforced.
- [x] **Gate 3 (Temporal):** Trading dates align with `core.market_ohlcv_daily`.
- [x] **Gate 4 (Distribution):** Sane foreign room and trading volume distributions.
- [x] **Gate 5 (Pipeline):** Integrated into canonical `vesta.duckdb`.

## 4. Identified Defects & Remediation Log
- **Discovered Defect:** Earlier crawlers attempted to synthesize buy/sell turnover values by multiplying volume with closing price, introducing false data provenance.
- **Remediation:** Purged synthesized monetary columns per Rule B3/B4; preserved pure volume metrics.

## 5. Verification Command & Evidence
```bash
pytest tests/test_cafef_foreign_flow.py -v
```
- **Evidence:** `2 passed in 1.15s; ruff clean; mypy clean`.
