# Loop Verification: F003 — vnstock News Crawler

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F003`
- **Feature Name:** vnstock News Crawler
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Ingests equity news per symbol into `staging.news` then promotes to `core.news`.
  - Schema: `symbol VARCHAR NOT NULL`, `published_at TIMESTAMP NOT NULL`, `headline VARCHAR NOT NULL`, `body VARCHAR`, `source_url VARCHAR UNIQUE`, `available_at TIMESTAMP`, `fetched_at TIMESTAMP`.
  - Temporal Invariant: $T_{\text{published}} \le T_{\text{fetched}} + 7\text{h}$ (normalizing UTC+7 vs UTC).
  - Uniqueness: Deduped by `source_url`.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.news` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** Contributes to the 661,194 total rows in `core.news`.
- **Deduplication:** Dedup logic (`F009 news_dedup`) flags duplicates using `duplicate_of` without destroying provenance.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_vnstock_news_crawler.py -v` (8/8 pass).
- [x] **Gate 2 (Boundary):** `symbol NOT NULL` enforced; URL uniqueness verified.
- [x] **Gate 3 (Temporal):** `available_at` assigned to `published_at`; timezone parsed cleanly.
- [x] **Gate 4 (Distribution):** Sane distribution of news articles across symbols.
- [x] **Gate 5 (Pipeline):** Integrated into canonical `vesta.duckdb`.

## 4. Identified Defects & Remediation Log
- **Discovered Anomaly:** vnstock API news endpoint intermittent 500 errors.
- **Remediation:** Orchestrated under `F008` retry logic with exponential backoff and supplemented by CafeF news (`F004`).

## 5. Verification Command & Evidence
```bash
pytest tests/test_vnstock_news_crawler.py -v
```
- **Evidence:** `8 passed in 1.85s; ruff check src tests: clean; mypy: clean`.
