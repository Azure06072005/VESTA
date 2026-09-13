# Loop Verification: F007 — Snapshot Crawlers

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F007`
- **Feature Name:** Snapshot Crawlers (Valuation History, Realtime Quote)
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Ingests daily snapshot valuation metrics (P/E, P/B, Market Cap) without overwriting historical daily series.
  - Retention Policy: Snapshots keyed by `(symbol, as_of_date)`.
  - Must not contaminate immutable OHLCV prices.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Tables:** `core.valuation_history`, `core.realtime_quote`.
- **Retention Policy:** Explicit daily snapshot policy enforced per `DECISIONS.md`.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** Unit tests pass cleanly.
- [x] **Gate 2 (Boundary):** Valuation ratios conform to bounds ($P/E > 0, P/B > 0$).
- [x] **Gate 3 (Temporal):** `as_of_date` strictly reflects valuation date.
- [x] **Gate 4 (Distribution):** Reasonable valuation ratios across market sectors.
- [x] **Gate 5 (Pipeline):** Persists cleanly to `vesta.duckdb`.

## 4. Identified Defects & Remediation Log
- **Discovered Gap:** TCBS screener API deprecation in vnstock.
- **Remediation:** Handled via CafeF/Vietstock financial indicator endpoints.

## 5. Verification Command & Evidence
```bash
pytest tests/test_snapshot_crawlers.py -v
```
- **Evidence:** `4 passed; ruff clean; mypy clean`.
