# Loop Verification: F005 — Fundamental Crawler Suite

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F005`
- **Feature Name:** Fundamental Crawler Suite (Balance Sheet, Income, Cash Flow, Ratios)
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - 4 quarterly datasets keyed by `(symbol, period, report_type)`.
  - Point-in-Time Disclosure Lag Invariant:
    $$\text{available\_at} = \text{period\_end} + 30\text{ days (Circular 96/2020/TT-BTC)}$$
  - Must never use `period_end` as the decision timestamp (prevents forward leakage).
  - Balance sheet API gap formally accepted in `DECISIONS.md` (fails loudly by design).

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.fundamentals` in `d:/VESTA/db/vesta.duckdb`.
- **Live State:** Populated across `income_statement`, `cash_flow`, and `ratio`.
- **Pivoted Schema:** Normalized JSON metrics blob per `(symbol, period)`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_fundamental_crawler.py -v` (10/10 pass).
- [x] **Gate 2 (Boundary):** Valid schema; empty response on `balance_sheet` caught and handled explicitly.
- [x] **Gate 3 (Temporal):** `available_at` enforced with 30-day disclosure lag.
- [x] **Gate 4 (Distribution):** Valid financial metric ranges.
- [x] **Gate 5 (Pipeline):** Integrated into canonical `vesta.duckdb`.

## 4. Identified Defects & Remediation Log
- **Identified Gap:** vnstock API `Fundamental().equity().balance_sheet()` returns empty.
- **Remediation:** Gap logged in `DECISIONS.md` (2026-08-12); targeted by `F052` (CafeF BCTC enhancer).

## 5. Verification Command & Evidence
```bash
pytest tests/test_fundamental_crawler.py -v
```
- **Evidence:** `10 passed in 2.10s; ruff check: clean; mypy --strict: Success`.
