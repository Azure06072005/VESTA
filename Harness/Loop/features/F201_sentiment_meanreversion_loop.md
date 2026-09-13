# Loop Verification: F201 — Sentiment Mean-Reversion Hypothesis Backtest

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F201`
- **Feature Name:** Sentiment Mean-Reversion Hypothesis Backtest
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Tests whether extreme negative sentiment events exhibit subsequent mean-reversion in Vietnamese equities:
    $$\Delta R_i = R_{i, t+30} - R_{i, t+5} > 0$$
  - Hypothesis: Bad news causes initial over-reaction; by $t+30$, prices rebound relative to post-news immediate impact ($t+5$).
  - Evaluated on negative-sentiment events filtered from `core.pit_events`.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Module:** `src/pipeline/f201_robustness_check.py`.
- **Test Sample:** 15,081 negative-sentiment events across 1,437 symbols and 214 calendar months in `db/vesta.duckdb`.
- **Parametric Results:**
  - Pooled Arithmetic Mean Difference: **$+1.8745\%$**
  - Naive Standard Error: $0.00274$
  - Student-$t$ statistic: $t = 6.8371, p = 8.39 \times 10^{-12}$
  - Cohen's $d$: $0.0557$ (small economic effect size)
- **Bootstrap Validation:**
  - Cluster bootstrap by symbol (1,437 clusters, 2000 iterations): $\text{SE} = 0.003135$, $95\% \text{ CI} = [0.01327, 0.02518]$, $z = 5.98, p = 2.25 \times 10^{-9}$.
  - Block bootstrap by month (214 clusters): $\text{SE} = 0.006018$, $95\% \text{ CI} = [0.00695, 0.03049]$, $z = 3.12, p = 0.00184$.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** `pytest tests/test_f201_robustness.py -v` (5/5 pass).
- [x] **Gate 2 (Boundary):** Handled non-null returns.
- [x] **Gate 3 (Temporal):** Zero look-ahead: $t+5$ and $t+30$ offsets anchored to effective trading dates.
- [x] **Gate 4 (Distribution):** Cluster and block bootstrap confirm statistical significance of the mean.
- [x] **Gate 5 (Pipeline):** Live execution against production database completed; report output to `out/f201_robustness_report.json`.

## 4. Identified Defects & Remediation Log (CRITICAL ANOMALY DETECTED)
- **Regime Heterogeneity Confirmed (`sign_flip_detected = True`):**
  - While mean reversion is strongly positive in bull markets (COVID recovery rally $+6.74\%$, COVID crash $+4.15\%$), **it severely inverts into negative momentum during liquidity crises**:
    - 2022 Real Estate / Corporate Bond Crisis: **$-5.14\%$** (prices continue falling)
    - FTSE correction: **$-2.47\%$**
- **Conclusion:** A general pooled mean is dangerous and misleading without regime conditioning. Triggered `F202b` and `F203`.

## 5. Verification Command & Evidence
```bash
python src/pipeline/f201_robustness_check.py --report out/f201_robustness_report.json && pytest tests/test_f201_robustness.py -x
```
- **Evidence:** `5/5 unit tests passed; pooled mean diff = +1.8745%, p = 8.39e-12; sign_flip_detected = True`.
