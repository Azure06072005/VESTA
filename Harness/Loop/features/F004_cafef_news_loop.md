# Loop Verification: F004 — CafeF News Crawler (Secondary Source)

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F004`
- **Feature Name:** CafeF News Crawler
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Secondary news stream scraped politely from CafeF's paginated AJAX endpoint.
  - Strict compliance with `robots.txt`; rate-limited fetching.
  - Target Schema: Identical to `F003` to allow seamless UNION in `core.news`.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.news` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** Contributes 587,957 historical rows across 1,818 symbols.
- **Combined Table Size:** 661,194 total rows in `core.news`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_cafef_crawler.py -v` (8/8 pass).
- [x] **Gate 2 (Boundary):** Schema identical to F003; `symbol` matches `core.dim_symbol`.
- [x] **Gate 3 (Temporal):** `published_at` parsed from Vietnamese string format (`dd/mm/yyyy hh:mm` or `dd/mm/yyyy`).
- [x] **Gate 4 (Distribution):** Covers broad cross-section of Vietnamese equities over 15+ years.
- [x] **Gate 5 (Pipeline):** Live DuckDB backfill verified across 1,818 symbols.

## 4. Identified Defects & Remediation Log
- **Discovered Defect (2026-09-12 Audit):**
  - **25.63% of articles have midnight timestamps (`00:00:00`)**: CafeF historical archives often store only the calendar date without hours/minutes.
  - **Remediation:** In `F102 pit_join`, these articles must be forward-lagged to the next session if publication cannot be confirmed before 15:00 close.

## 5. Verification Command & Evidence
```bash
python -c "import duckdb; con = duckdb.connect('db/vesta.duckdb', read_only=True); print('Total news rows:', con.execute('SELECT COUNT(*) FROM core.news').fetchone()[0])"
```
- **Evidence:** `Total news rows: 661194`.
