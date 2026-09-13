# Loop Engineering Verification Standard — VESTA
**Vietnamese Equity Sentiment-Triggered Agent (Autonomous Trading Harness)**  
*Document Version: 3.0.0 | Applicable Tiers: F0xx → F9xx | Methodology: Closed-Loop Empirical Engineering (CLEE)*

---

## 1. Executive Summary & Philosophy of Loop Engineering

In classical software engineering, verification is considered complete when static analysis passes and unit test suites exit with code `0`. **In quantitative finance, machine learning pipelines, and autonomous trading systems, this standard is dangerously inadequate.**

A financial data and algorithmic trading system can execute without syntax errors, type violations, or runtime exceptions while silently harboring catastrophic empirical defects:
1. **Look-Ahead Bias & Temporal Leakage:** Ingesting post-session news or articles with truncated midnight timestamps (`00:00:00`) against same-day market close prices, creating illusory alpha that evaporates in live execution.
2. **Distributional Optical Illusions (The Kurtosis Trap):** Generating an apparently attractive positive arithmetic mean return ($+1.87\%$) that masks a losing win-rate ($<45\%$) and a negative median ($-0.14\%$), driven entirely by extreme, un-tradable right-tail penny stock spikes (e.g., $+3,021\%$ on illiquid UPCOM tickers like `XDC`).
3. **Corporate Action Distortions:** Failing to populate dividend and split adjustments in `core.price_adjustment_events`, causing routine $2:1$ stock splits or bonus share issuances to appear as catastrophic $-50\%$ trading drawdowns.
4. **Illiquidity & Artificial Ties:** Anchoring trade signals to carrying prices from zero-volume trading days (`volume <= 0`), manufacturing artificial $0.00\%$ return ties that corrupt statistical significance.
5. **Regime Overfitting & Crisis Sign-Flips:** Calibrating models on bull-market liquidity bubbles (e.g., 2020–2021) while ignoring structural crisis regimes (2007, 2011, 2014, 2022, 2026), where mean-reversion signals completely invert into devastating momentum sell-offs.
6. **Database Fragmentation & Referential Pollution:** Scattering data across unmerged staging databases or forcing hundreds of thousands of non-equity macro articles into strict ticker tables, corrupting point-in-time joins.

**Loop Engineering** is the disciplined, cybernetic feedback methodology that replaces open-loop "code-then-test" development with a **closed-loop verification cycle**. In Loop Engineering:
- **No feature is a linear step; every feature is an empirical evaluation loop.**
- **Code is treated as an unverified hypothesis until its mathematical invariants, temporal causality, and statistical robustness are empirically confirmed against the canonical live database (`vesta.duckdb`).**
- **Downstream empirical discoveries trigger backward feedback loops into upstream data gates.**
- **The ledger state (`feature_list.json`) advances only upon pasting literal, bit-identical terminal execution output.**

---

## 2. The 3 Nested Loops of Loop Engineering

Loop Engineering operates across three nested cybernetic feedback levels:

```
===================================================================================
                       THE 3 NESTED CYBERNETIC LOOPS
===================================================================================

 [OUTER LOOP: Macro & Strategy Validation]
   - Deflated Sharpe Ratio (DSR) & Overfitting Probability (PBO < 0.10)
   - 16-Regime x 3-Exchange Cross-Validation & Macro Factor Controls (VIX, DXY, TNX)
   - Feedback Log & Realized Return Drift Tracking (F402)
   ^
   | (Downstream Anomaly Feedback)
   v
 [MESO LOOP: Tier Checkpoints, DB Topology & Reconciliation]
   - Referential Integrity & Universe Consistency (F009, F072, F101)
   - Storage Topology: 1 Main DB, 1 Backup DB, 1 Test DB, Isolated Backups
   - Macro vs. Equity News Decoupling & Atomic Staging Promotion
   ^
   | (Dataset Invariant Feedback)
   v
 [INNER LOOP: Per-Feature 5-Gate Micro Verification]
   - Gate 1: Static Code, Types & Unit Tests (ruff, mypy, pytest)
   - Gate 2: Domain Boundary & Candlestick Invariants (P > 0, V > 0, DDL)
   - Gate 3: Temporal Causality & Point-in-Time (15:00 Rule, Midnight Lag)
   - Gate 4: Distributional & Non-Parametric Rigor (Median, Win-Rate, Wilcoxon)
   - Gate 5: Live Canonical DB Integration & Bit-Identical Reproducibility
===================================================================================
```

1. **The Inner Loop (Micro / Feature Level):** The strict 5-Gate verification engine through which every single feature must pass before its state can transition to `passing`.
2. **The Meso Loop (Dataset & Storage Level):** The cross-dataset reconciliation layer that audits referential integrity across master dimensions, enforces atomic staging-to-core promotions, verifies backup parity, and prevents cross-domain schema pollution.
3. **The Outer Loop (Macro & Strategy Level):** The high-level statistical and econometric evaluation that stress-tests signals across historical market regimes, controls for global liquidity tightening, bounds multiple-testing snooping (DSR/PBO), and feeds anomalies back into upstream pipelines.

---

## 3. The 5 Core Axioms of Loop Engineering

```
+-----------------------------------------------------------------------------+
|                           THE 5 LOOP AXIOMS                                 |
|                                                                             |
|  [Axiom 1] Causality Dominates Code (Point-in-Time Temporal Gating)         |
|  [Axiom 2] Distributional Realism Over Averages (Median & Non-Parametric)   |
|  [Axiom 3] Physical Market Realism (Liquidity, Non-Zero Volume, Adjustments)|
|  [Axiom 4] Zero Speculative Complexity (WIP=1, Signal Before Infra)         |
|  [Axiom 5] Verbatim Empirical Evidence ("Confirmed Means Pasted Stdout")    |
+-----------------------------------------------------------------------------+
```

### Axiom 1: Causality Dominates Code (Point-in-Time Temporal Gating)
No signal, feature, or label may consume data that was not publicly knowable and actionable at the effective decision timestamp.
- **Timezone Reconciliation:** Timestamps must be explicitly harmonized between UTC fetch records and local market hours (UTC+7 for Vietnam: HOSE, HNX, UPCOM). A record where $T_{\text{published, UTC+7}} > T_{\text{fetched, UTC}} + 7\text{h}$ is an impossible future timestamp and must raise a validation failure.
- **Session Cutoff Rule (15:00):** Vietnam equity markets close trading at 15:00 local time. News published $\le 15:00$ anchors to that session's closing price $P_0$. News published $> 15:00$, or on weekends/market holidays, MUST anchor to the **next active trading session's close**.
- **Midnight Timestamp Quarantine (`00:00:00`):** News feeds with truncated midnight timestamps cannot prove whether they were published before 09:00, during trading hours, or late in the evening. In the presence of truncated hours, the engine must either enforce forward-lagging to the next session or audit against independent intraday feeds to prevent look-ahead bias.
- **Fundamental Disclosure Vintage:** Financial reports must query `get_as_of(symbol, period, decision_date)` where:
  $$T_{\text{available}} \le T_{\text{decision}} \quad \text{and} \quad T_{\text{fetched}} \le T_{\text{decision}}$$
  Retrospective audit restatements or subsequent quarter revisions must never leak into historical events.

### Axiom 2: Distributional Realism Over Averages (The Non-Parametric Mandate)
Financial returns exhibit extreme kurtosis ($\gamma_2 > 20$, and in emerging markets like Vietnam, $\gamma_2 > 4,000$ due to unconstrained UPCOM trading bands). In such environments, the arithmetic mean and Student-$t$ distribution are mathematically fragile and misleading.
- Every reported mean difference $\mu$ MUST be accompanied by the **Median difference**, **Win-Rate ($P(\text{gain} > \text{loss})$)**, **Loss-Rate**, and the non-parametric **Wilcoxon signed-rank test**.
- **The Outlier Trap:** If a positive mean ($\mu > 0$) coincides with a Win-Rate $< 50\%$ and a negative Median ($\text{Med} \le 0$), the effect is classified as a **spurious outlier artifact**, not an exploitable trading edge.
- **Multiverse Outlier Testing:** Analysis must be evaluated across multiple data subsets: raw sample, top outlier isolated, 0.5% and 1.0% winsorization, and liquid basket partitioning (HOSE vs. HNX vs. UPCOM).

### Axiom 3: Physical Market Realism (Friction, Liquidity, and Capital Changes)
Algorithms do not trade mathematical ideals; they trade physical order books.
- **Liquidity Gating (`volume > 0`):** OHLCV bars with zero volume represent carried forward prices during market halts or illiquid dead stocks. Returns computed against zero-volume bars must be filtered to prevent artificial $0.00\%$ ties.
- **Corporate Action Continuity:** Cash dividends, stock dividends, bonus shares, and rights issues artificially depress nominal price series. Raw closing prices must never be used directly for return calculations; prices must be processed through `core.price_adjustment_events`.
- **Exchange Microstructure Disaggregation:** HOSE ($\pm 7\%$), HNX ($\pm 10\%$), and UPCOM ($\pm 15\%$, with first-day swings up to $\pm 40\%$) have fundamentally different market regimes. Signals must never be pooled blindly across exchanges without exchange-level reporting.

### Axiom 4: Zero Speculative Complexity (WIP=1 & Signal Before Infrastructure)
- **Strict WIP=1 Invariant:** Exactly ONE feature across the entire project may reside in the `active` status at any moment. Work on secondary crawlers, execution systems, or auxiliary tooling is strictly paused until the active scientific gate is resolved.
- **Order of Build = Order of Proof:** The execution layer (`F9xx`), real-time order routing, WebSockets, or deep learning fine-tuning (`F301`) shall not be implemented until historical statistical edge (`F2xx`) is proven regime-stable.

### Axiom 5: Verbatim Empirical Evidence ("Confirmed Means Pasted Stdout")
- A feature never transitions to `passing` based on summary claims, assurances, or unit test passes in isolation.
- The `evidence` field in `feature_list.json` and the feature loop log MUST contain the **literal, unedited terminal CLI command and verbatim stdout** executed against the canonical production database (`vesta.duckdb`).

---

## 4. The 5-Gate Closed-Loop Verification Engine

Every feature must navigate the 5-Gate Loop sequentially. A failure at any gate halts execution and enters the remediation loop:

```
  [Feature Activated: WIP=1]
             |
             v
  [GATE 1: Static Code Gate] -----------> Fails -> [Surgical Refactor Loop]
             | Passes
             v
  [GATE 2: Domain Invariant Gate] -------> Fails -> [Schema & Sanitization Loop]
             | Passes
             v
  [GATE 3: Temporal Causality Gate] -----> Fails -> [Point-in-Time Offset Loop]
             | Passes
             v
  [GATE 4: Distributional Gate] ----------> Fails -> [Outlier & Robustness Loop]
             | Passes
             v
  [GATE 5: Full-Pipeline Gate] ----------> Fails -> [Idempotency & Reproducibility]
             | Passes
             v
  [Sign-Off & Verbatim Evidence Paste] --> State: passing (Irreversible)
```

### Gate 1: Static Code, Type Safety & Unit Regression Gate
* **Objective:** Ensure syntactic hygiene, zero dead code, strict type safety, and 100% unit regression pass.
* **Mandatory Protocol:**
  ```bash
  # 1. Lint and style conformance
  ruff check src tests
  
  # 2. Static type analysis across all modules
  mypy src tests --ignore-missing-imports
  
  # 3. Unit test suite execution (fail-fast)
  pytest tests/test_<feature_name>.py -x -v
  ```
* **Passing Threshold:** Zero linter warnings, zero type errors, all unit tests pass with exit code `0`.

### Gate 2: Domain Invariant & Data Geometry Gate
* **Objective:** Guarantee physical data sanity inside DuckDB before running financial calculations.
* **Mandatory Verification Checks:**
  1. **Strict Non-Zero Price Invariant:**
     $$\forall \text{ rows in } \text{core.market\_ohlcv\_daily}, \quad \min(open, high, low, close) > 0$$
     In event tables (`core.pit_events`), assert `price_at_publish > 0` to prevent division-by-zero crashes ($NaN$/$Inf$).
  2. **Candlestick Geometric Sanity:**
     $$Low \le Open \le High \quad \land \quad Low \le Close \le High$$
  3. **Volume Liquidity Invariant:**
     Bars with `volume <= 0` must be identified. In signal backtests, transactions anchored to un-traded bars must be flagged or filtered.
  4. **Referential Integrity:**
     Every stock symbol in event and price tables must resolve against master universe dimensions (`core.dim_symbol` union `core.dim_symbol_cafef`).

### Gate 3: Temporal Causality & Point-in-Time Gate
* **Objective:** Mathematically eliminate look-ahead bias and future information leakage.
* **Mandatory Verification Checks:**
  1. **Timezone Offset Normalization:**
     Validate that publication timestamps ($T_{\text{publish, UTC+7}}$) precede or equal fetch timestamps ($T_{\text{fetch, UTC}} + 7\text{h}$). Flag any future-dated articles.
  2. **The 15:00 Market Session Cutoff:**
     $$T_{\text{effective\_trading\_date}} = \begin{cases} T_{\text{date}}, & \text{if } T_{\text{time}} \le 15:00 \text{ and } T_{\text{date}} \in \text{TradingDays} \\ \text{NextTradingDay}(T_{\text{date}}), & \text{otherwise} \end{cases}$$
  3. **Midnight Timestamp Quarantine:**
     For articles with `published_at::TIME = '00:00:00'`, test sensitivity against next-day lagging to prevent look-ahead bias.
  4. **Fundamental Vintage Gating:**
     Querying financial reports must use point-in-time constraints:
     $$\text{available\_at} \le \text{published\_at} \quad \land \quad \text{fetched\_at} \le \text{published\_at}$$

### Gate 4: Distributional Integrity & Statistical Robustness Gate
* **Objective:** Eliminate p-hacking, statistical optical illusions, and outlier distortion.
* **Mandatory Reporting Matrix:**
  Every research or backtest feature must output the standardized 7-metric evaluation table:
  ```
  +-----------------------------------------------------------------------------------------+
  | N Events | Mean Diff | Median Diff | Win Rate (%) | Loss Rate (%) | Wilcoxon p | Cohen's d  |
  +-----------------------------------------------------------------------------------------+
  ```
* **Mandatory Verification Checks:**
  1. **Non-Parametric Wilcoxon Signed-Rank Test:**
     Compute the paired differences $D_i = R_{i, t+30} - R_{i, t+5}$. If Student-$t$ is significant ($p < 0.01$) but Wilcoxon is non-significant ($p > 0.05$) and Median Diff $\le 0$, the hypothesis is **REJECTED** as an outlier artifact.
  2. **Multiverse Outlier Decomposition:**
     Report performance under:
     - Raw unconstrained pool.
     - Top-1 outlier isolated (investigate ticker, news event, and market circumstances).
     - Standard 0.5% and 1.0% Winsorization.
     - Exchange disaggregation: HOSE vs. HNX vs. UPCOM.
  3. **Deflated Sharpe Ratio (DSR):**
     Compute the Bailey & López de Prado (2014) DSR adjusting for skewness ($\gamma_1$), kurtosis ($\gamma_2$), sample size ($N$), and the estimated number of independent trials ($K$):
     $$\text{DSR} = \Phi\left( \frac{(\widehat{SR} - SR^*) \sqrt{T-1}}{\sqrt{1 - \gamma_1 \widehat{SR} + \frac{\gamma_2 - 1}{4} \widehat{SR}^2}} \right)$$
     DSR must exceed $0.95$ for the chosen trial horizon.
  4. **Combinatorial Symmetric Cross-Validation (CSCV) PBO:**
     Compute Probability of Backtest Overfitting across $S \ge 16$ sub-blocks. PBO must satisfy $\text{PBO} < 0.10$ ($10\%$).

### Gate 5: Full-Pipeline Integration, Database Idempotency & Reproducibility Gate
* **Objective:** Prove that the pipeline executes deterministically and idempotently on the production database.
* **Mandatory Verification Checks:**
  1. **Live Canonical Execution:**
     The command must run against `d:/VESTA/db/vesta.duckdb` (not solely against small mock fixtures).
  2. **Bit-Identical Reproducibility:**
     Two consecutive executions using the same random seed must produce bit-identical output JSON artifacts:
     ```bash
     diff out/run1.json out/run2.json  # Must return empty
     ```
  3. **Database Idempotency:**
     Executing an ingestion or transformation script twice must produce identical aggregate row counts and zero duplicate primary keys.

---

## 5. Storage Topology & Database Consolidation Standard

To eliminate data fragmentation and guarantee transaction safety, `d:/VESTA/db` is strictly governed by the **4-Item Canonical Topology**:

```
d:/VESTA/db/
├── vesta.duckdb                    <-- 1. Sole Canonical Production DB (Read/Write)
├── vesta_backup.duckdb             <-- 2. Sole Main Backup DB (Cold Standby)
├── test_db/
│   └── vesta_test.duckdb           <-- 3. Dedicated Isolated Test DB
└── backups/
    ├── staging_dbs_merged/         <-- 4. Archived Staging DBs (0 unmerged records)
    └── historical_snapshots/       <--    Point-in-time database snapshots
```

### Ingestion & Promotion Protocol
1. **Never write raw crawler streams directly into `core` tables.** Ingest into temporary staging schemas or staging DuckDB files.
2. **Atomic Verification Before Promotion:** Validate schema types, NOT NULL constraints, and primary key uniqueness on staging tables.
3. **Atomic Promotion Query:** Use `INSERT OR IGNORE` or `INSERT OR REPLACE` transactions from staging into `core`.
4. **Post-Promotion Vacuuming & Checksumming:** Run `CHECKPOINT` and verify record count deltas before archiving staging files into `db/backups/staging_dbs_merged/`.

---

## 6. Macro Policy vs. Equity News Architectural Decoupling

During the 2026-09-12 data audit, full-text syntactic scanning of all 477,733 articles in `core.macro_policy` revealed:
- **435,988 articles (91.26%)** are pure macroeconomic, monetary policy, and general regulatory articles with zero stock ticker mentions.
- **41,745 articles (8.74%)** explicitly mention listed equity tickers (e.g., HPG 1,254, VIC 937, VNM 807).

### Architectural Standard: No Physical Merge into `core.news`
A naive physical merge of `core.macro_policy` into `core.news` is **STRICTLY FORBIDDEN** under Loop Engineering Axiom 1 and Axiom 3:
1. **Schema Invariant Breach:** `core.news` enforces `symbol VARCHAR NOT NULL`. Inserting 436k pure macro articles forces synthetic placeholder symbols (e.g., `VNINDEX` or `MACRO`), corrupting dimension foreign keys.
2. **Referential Integrity Crash:** `F101 validate_crossref` checks that every symbol in news exists in `core.dim_symbol`. Dummy tickers cause immediate validation failures.
3. **Event Join Dilution:** `F102 pit_join` constructs trading-day price horizons ($t+1, t+5, t+30$) per symbol. Merging 436k non-equity articles generates 436,000 null-price rows in `core.pit_events`, diluting backtest datasets with meaningless observations.

### Permitted Access Patterns:
1. **Unified Query Layer (Read-Only SQL View):**
   ```sql
   CREATE VIEW core.v_all_news AS
   SELECT symbol, published_at, headline, body, source_url, 'equity' AS news_tier FROM core.news
   UNION ALL
   SELECT NULL AS symbol, published_at, headline, body, source_url, 'macro' AS news_tier FROM core.macro_policy;
   ```
2. **Selective Promotion Pipeline:** Only macro articles passing strict syntactic equity whitelisting (with valid tickers resolved in `core.dim_symbol`) may be promoted into `core.news`.

---

## 7. Operational State Transitions in `feature_list.json`

Features transition strictly through an irreversible finite-state machine governed by the 5-Gate Loop:

```
                  +-----------------+
                  |   not_started   |
                  +-----------------+
                           |
                     (WIP=1 Picked)
                           v
                  +-----------------+
                  |     active      | <---+ (Surgical Edit Loop)
                  +-----------------+     |
                     /           \        |
       (All 5 Gates Pass)    (Unresolvable Blocker)
                   /               \      |
                  v                 v     |
         +-----------------+   +-----------------+
         |     passing     |   |     blocked     |
         +-----------------+   +-----------------+
           (Irreversible)       (Logged to DECISIONS.md)
```

1. **`not_started` $\rightarrow$ `active`:**
   - Permitted if and only if **all listed dependencies are in the `passing` state**.
   - Enforces **WIP=1**: Only one feature active project-wide.
2. **`active` $\rightarrow$ `passing`:**
   - Permitted ONLY when all 5 Gates pass cleanly.
   - The `evidence` field in `feature_list.json` must be populated with literal terminal execution output.
   - **Irreversible Rule:** A passing feature is never downgraded. If a regression is introduced by future work, a dedicated remediation feature is spawned in the backlog.
3. **`active` $\rightarrow$ `blocked`:**
   - Triggered when an unresolvable external, legal, or physical blocker is discovered (e.g., UBCKNN algorithmic trading suspension for `F901`, or API endpoint removal for `F052`).
   - A formal rationale must be logged in `DECISIONS.md`.

---

## 8. Per-Feature Loop Architecture (`Harness/Loop/features/`)

To guarantee that progress is continuously audited and never lost or misremembered, each feature in `feature_list.json` maintains its own dedicated Loop File in `d:/VESTA/Harness/Loop/features/Fxxx_loop.md`.

Every per-feature loop document follows this standardized structure:
1. **Feature Specification & Invariant Contract:** Exact claim being proven and invariants enforced.
2. **Retrospective Progress Audit:** Comprehensive accounting of tables modified, row counts verified, staging merges executed, and data anomalies identified.
3. **5-Gate Loop Verification Status:** Granular checklist detailing Gates 1 through 5.
4. **Data Defects & Remediation Log:** Specific data sanitization rules applied to that feature (e.g., non-zero price filters, zero-volume handling, timezone offsets).
5. **Verbatim CLI Verification Command:** Copy-pasteable terminal command.
6. **Execution Evidence & Ledger Sign-Off:** Verbatim stdout pasted from the terminal, confirming transition criteria.

---

*End of Standard. Loop until verified. Never guess.*
