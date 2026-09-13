# Loop Verification: F056 to F071 — Macro / Regulatory Crawler Backlog

## 1. Invariant & Hypothesis Contract
- **Feature Range:** `F056` through `F071`
- **Features Included:**
  - `F056`: World Bank Macro Indicator Crawler
  - `F057`: SBV (State Bank of Vietnam) Monetary Policy Crawler
  - `F058`: MoF (Ministry of Finance) Fiscal Policy Crawler
  - `F059`: GSO (General Statistics Office) Macro Indicators Crawler
  - `F060`: MPI (Ministry of Planning and Investment) Crawler
  - `F061`: Bao Dau Tu Financial News Crawler
  - `F062`: Thoi Bao Ngan Hang Banking News Crawler
  - `F063`: Tien Phong Economic News Crawler
  - `F064`: VnEconomy Financial & Policy News Crawler
  - `F065`: Tuoi Tre Kinh Te Economic News Crawler
  - `F066`: Thanh Nien Tai Chinh Financial News Crawler
  - `F067`: TNCK (Tap Chi Chung Khoan) SSC Policy Crawler
  - `F068`: Luat Vietnam Legal Normative Acts Crawler
  - `F069`: Thu Vien Phap Luat Legal Acts Crawler
  - `F070`: MoC (Ministry of Construction) Real Estate Policy Crawler
  - `F071`: HoREA Real Estate Association Regulatory Crawler
- **Target State:** `not_started` (Paused per WIP=1)
- **Architectural Invariant:** Strict serialization under Rule A2/B2 (Signal Before Infrastructure). Zero crawler expansion while `F203` regime-stability gate is unresolved.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Status:** **ALL PAUSED (not_started)**.
- **WIP=1 Rule Enforcement:** All 16 features paused behind `F203`.
- **Pre-Crawled Staging Consolidation:** Raw test dumps and staging files previously collected were audited and consolidated into `vesta.duckdb` or archived to `db/backups/staging_dbs_merged/`.

## 3. 5-Gate Loop Verification Status
- [ ] **Gate 1 to Gate 5:** Paused pending completion of `F203`.

## 4. Verification & Resumption Conditions
- Must not be activated until `F203` reaches an empirical decision in `DECISIONS.md`.
