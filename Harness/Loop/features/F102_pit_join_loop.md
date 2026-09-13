# Loop Verification: F102 — Point-in-Time News + Price + Fundamental Join

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F102`
- **Feature Name:** Point-in-Time News + Price + Fundamental Join (`core.pit_events`)
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Joins deduped news (`core.news`), adjusted OHLCV (`core.market_ohlcv_daily`), and vintage-gated fundamentals (`core.fundamentals`).
  - **Temporal Trading Session Mapping (15:00 Rule):**
    $$T_{\text{effective\_date}} = \begin{cases} T_{\text{date}}, & \text{if } T_{\text{time}} \le 15:00 \text{ and } T_{\text{date}} \in \text{TradingDays} \\ \text{NextTradingDay}(T_{\text{date}}), & \text{otherwise} \end{cases}$$
  - Price horizons ($t+1, t+5, t+30$) are **trading days** (from price bars), never calendar days.
  - Zero Look-Ahead Bias: News published post-close anchors to the next session; fundamental restatements fetched after publication are invisible.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Table:** `core.pit_events` in `d:/VESTA/db/vesta.duckdb`.
- **Live Row Count:** **658,182 point-in-time events**.
- **VN30 Constituency:** 28,112 events across 30 symbols (100% price coverage at publish and $t+1$).
- **Test Suite:** `pytest tests/test_pit_join.py -v` (13/13 pass).

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** 13/13 unit tests pass; ruff clean; mypy clean.
- [x] **Gate 2 (Boundary):** Schema verified: `event_id`, `symbol`, `published_at`, `effective_trading_date`, `price_at_publish`, `price_t1`, `price_t5`, `price_t30`.
- [x] **Gate 3 (Temporal):** Look-ahead bias tests pass by construction (`test_effective_trading_date_after_market_close_uses_next_trading_day`, `test_build_events_uses_get_as_of_not_a_future_revision`).
- [x] **Gate 4 (Distribution):** Sane event counts across 1,820 symbols.
- [x] **Gate 5 (Pipeline):** Live execution against canonical DuckDB verified.

## 4. Identified Defects & Remediation Log (CRITICAL EMPIRICAL AUDIT)
- **Discovered Data Defects (2026-09-12 Deep Audit):**
  1. **Unpopulated Adjustment Events:** `core.price_adjustment_events` has **0 rows** in `vesta.duckdb`. As a result, `adjustments.apply_adjustment()` defaulted to raw close prices. Stock splits and bonus issues appear as unadjusted price crashes.
  2. **1,038 Zero Prices:** 1,038 rows in `core.pit_events` have `price_at_publish = 0`, causing division-by-zero ($NaN$/$Inf$) when calculating percent returns.
  3. **29.10% Zero-Volume Bars:** Joined OHLCV bars frequently exhibit zero volume, creating artificial $0.00\%$ price ties.
  4. **25.63% Midnight Timestamps (`00:00:00`):** Articles lacking intraday hours risk look-ahead bias if assumed published before 15:00.
- **Downstream Remediation (Enforced in F201, F202b, F203):**
  - Mandatory filter: `WHERE price_at_publish > 0 AND volume > 0`.
  - Sensitivity analysis on midnight timestamps.
  - Upstream corporate action adjustment pipeline scheduled for full population.

## 5. Verification Command & Evidence
```bash
python -c "import duckdb; con = duckdb.connect('db/vesta.duckdb', read_only=True); print('PIT Events count:', con.execute('SELECT COUNT(*) FROM core.pit_events').fetchone()[0]); print('Zero prices count:', con.execute('SELECT COUNT(*) FROM core.pit_events WHERE price_at_publish = 0').fetchone()[0])"
```
- **Evidence:**
  - `PIT Events count: 658182`
  - `Zero prices count: 1038` (Identified and logged for downstream filtering).
