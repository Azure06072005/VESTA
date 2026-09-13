# Loop Verification: F101 — Cross-Dataset Validation Gate

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F101`
- **Feature Name:** Cross-Dataset Referential Integrity & Temporal Validation Gate
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Referential consistency across all tables in `core`:
    - Every symbol in `core.market_ohlcv_daily` must exist in `core.dim_symbol`.
    - Every symbol in `core.news` must exist in `core.dim_symbol`.
    - Zero future timestamps: $\forall \text{ records, } \text{fetched\_at} \le \text{current\_time}$.
    - Must fail loudly (`ValidationError`) on an injected orphan ticker or future date.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Module:** `src/pipeline/validate_crossref.py`.
- **Test Suite:** `pytest tests/test_crossref_validation.py -v` (108 passed, 1 xfailed).
- **Canonical Execution:** Tested across all 7 core tables in `vesta.duckdb`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `ruff check src tests` clean; `mypy` clean across 31 source files.
- [x] **Gate 2 (Boundary):** Zero orphan symbols found in `core.news` or `core.market_ohlcv_daily`.
- [x] **Gate 3 (Temporal):** No future timestamps detected; timezone alignments verified.
- [x] **Gate 4 (Distribution):** Sane referential match rates (100% of symbols valid).
- [x] **Gate 5 (Pipeline):** `python -m pipeline.validate_crossref --all` outputs `PASS`.

## 4. Identified Defects & Remediation Log
- **Discovered Gap:** Uncontrolled insertion of macro policy articles into `core.news` would have crashed this gate due to missing symbols.
- **Remediation:** Enforced separation between `core.news` and `core.macro_policy`.

## 5. Verification Command & Evidence
```bash
python -m pipeline.validate_crossref --all
```
- **Evidence:** `PASS` on clean database; raises `ValidationError` on injected orphan ticker.
