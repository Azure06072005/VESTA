# Loop Verification: F001b — dim_symbol Supplement: CafeF Directory Cross-Reference

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F001b`
- **Feature Name:** dim_symbol Supplement: CafeF Directory Cross-Reference
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Cross-references 3,016 CafeF directory entries against `core.dim_symbol`.
  - Distinguishes OTC equities from listed exchange tickers via `CenterId` mapping:
    - `CenterId=1` -> HOSE
    - `CenterId=2` -> HASTC (HNX)
    - `CenterId=8` -> OTC
    - `CenterId=9` -> UPCOM
  - Zero duplicate symbols; table `core.dim_symbol_cafef` captures unlisted OTC companies.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.dim_symbol_cafef` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** 984 rows (750 real OTC equities + 234 unlisted non-OTC equities).
- **Instrument Categorization:** 2,734 equities, 144 covered warrants, 79 bonds, 46 funds, 9 indices, 4 unknown.
- **VN30 Alignment:** 30/30 exact matches on VN30 constituents.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_cafef_symbol_directory.py -v` passes (34/34).
- [x] **Gate 2 (Boundary):** Schema verified: `symbol`, `organ_name`, `exchange`, `is_vn30`, `is_hnx30`, `redirect_slug`.
- [x] **Gate 3 (Temporal):** Directory snapshot stamped with ingestion date.
- [x] **Gate 4 (Distribution):** Clean partitioning of listed vs. OTC universe.
- [x] **Gate 5 (Pipeline):** Persisted into canonical DuckDB without table conflicts.

## 4. Identified Defects & Remediation Log
- **Discovered Anomaly:** HNX legacy folder internally named `hastc`, not `hnx`. Mapping hardcoded to prevent silent defaulting.

## 5. Verification Command & Evidence
```bash
pytest tests/test_cafef_symbol_directory.py -v
```
- **Evidence:** `34 passed in 1.42s; ruff check src tests: clean; mypy: clean`.
