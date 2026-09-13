# Loop Verification: F001 — Reference Crawler: dim_symbol Master Data

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F001`
- **Feature Name:** Reference Crawler: dim_symbol Master Data
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Complete equity universe across HOSE, HNX, UPCOM.
  - Mandatory columns: `symbol VARCHAR PRIMARY KEY`, `organ_name VARCHAR NOT NULL`, `exchange VARCHAR`, `industry VARCHAR`, `delisted_date DATE`, `fetched_at TIMESTAMP`.
  - Referential master: Any ticker referenced in downstream price, news, and event tables must exist in `core.dim_symbol`.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.dim_symbol` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** 3,446 symbols.
- **Data Completeness:**
  - HOSE, HNX, UPCOM active equities fully populated.
  - Zero NOT NULL violations on `organ_name`.
  - Delisted gap formally accepted in `DECISIONS.md` (2026-08-25).

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_dim_symbol.py -x` exits `0` (with accepted xfail).
- [x] **Gate 2 (Boundary):** `symbol` uniqueness enforced; `organ_name NOT NULL` passes.
- [x] **Gate 3 (Temporal):** `fetched_at` stored in ISO8601 UTC timestamp.
- [x] **Gate 4 (Distribution):** Sane distribution across exchanges (HOSE ~400, HNX ~300, UPCOM ~850+).
- [x] **Gate 5 (Pipeline):** Live query on `vesta.duckdb` returns 3,446 unique symbols without lock errors.

## 4. Identified Defects & Remediation Log
- **Identified Gap:** vnstock API delisted endpoint instability.
- **Remediation:** Formally accepted in `DECISIONS.md`; supplemented by `F001b` (CafeF company directory cross-reference).

## 5. Verification Command & Evidence
```bash
pytest tests/test_dim_symbol.py -v
```
- **Evidence:** `tests/test_dim_symbol.py ......x [100%] -- 6 passed, 1 xfailed`.
