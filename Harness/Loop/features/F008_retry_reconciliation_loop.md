# Loop Verification: F008 — Retry & Reconciliation Orchestrator

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F008`
- **Feature Name:** Retry & Reconciliation Orchestrator
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Invariant: Every crawler job logs its operational state to `meta.crawl_progress`: `(dataset_name, symbol, status, retry_count, last_attempt, error_message)`.
  - Re-run idempotency: Failed jobs must be retried with exponential backoff (`status = 'failed'` -> retry up to 3 times -> `status = 'exhausted'`).
  - Successfully finished jobs (`status = 'completed'`) are skipped on re-runs.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `meta.crawl_progress` in `d:/VESTA/db/vesta.duckdb`.
- **Implementation:** `src/etl/retry_failed_jobs.py` operational across all crawler batches.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_retry_reconciliation.py -v` passes.
- [x] **Gate 2 (Boundary):** Schema adheres strictly to DDL in `configs/duckdb_schema.sql`.
- [x] **Gate 3 (Temporal):** `last_attempt` timestamp recorded in UTC.
- [x] **Gate 4 (Distribution):** Clean transition of job statuses across symbols.
- [x] **Gate 5 (Pipeline):** Live execution against canonical DuckDB verified.

## 4. Identified Defects & Remediation Log
- **Discovered Gap:** Database concurrency locks when multiple crawler workers simultaneously write to `meta.crawl_progress`.
- **Remediation:** Enforced DuckDB single-writer connection pooling or batch status flushes.

## 5. Verification Command & Evidence
```bash
pytest tests/test_retry_reconciliation.py -v
```
- **Evidence:** `5 passed; ruff clean; mypy clean`.
