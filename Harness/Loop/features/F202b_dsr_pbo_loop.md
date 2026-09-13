# Loop Verification: F202b — Formal Deflated Sharpe Ratio & PBO

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F202b`
- **Feature Name:** Formal Deflated Sharpe Ratio / Probability of Backtest Overfitting Calculation
- **Target State:** `passing`
- **Mathematical / Architectural Invariant:**
  - Implements the exact Bailey & López de Prado (2014, SSRN 2460551) Deflated Sharpe Ratio (DSR):
    $$\text{DSR} = \Phi\left( \frac{(\widehat{SR} - SR^*) \sqrt{T-1}}{\sqrt{1 - \gamma_1 \widehat{SR} + \frac{\gamma_2 - 1}{4} \widehat{SR}^2}} \right)$$
  - Adjusts for skewness ($\gamma_1$), kurtosis ($\gamma_2$), sample length ($T$), and estimated independent trials ($N \in [1, 2, 3]$).
  - Implements Combinatorial Symmetric Cross-Validation (CSCV) for Probability of Backtest Overfitting (PBO):
    $$\text{PBO} = \frac{1}{M} \sum_{m=1}^M \mathbb{I}(\text{SR}_{m, \text{test}} < 0) < 0.10 \text{ (Passing Threshold)}$$

## 2. Retrospective Progress Audit & Deep Outlier Analysis (2026-09-12 Consolidation)
- **Module:** `src/pipeline/f202b_dsr_pbo.py`.
- **Test Suite:** `pytest tests/test_f202b_dsr.py` (4/4 pass).
- **Execution on Canonical Database:** Ran against `db/vesta.duckdb`.
- **CRITICAL EMPIRICAL DISCOVERIES:**
  1. **Extreme Kurtosis & Outlier Decomposition:**
     - Raw excess kurtosis across all 15,081 events was astronomical: **$\gamma_2 = 4,315.77$**.
     - Top outlier: Ticker `XDC` (+3,021% return difference on UPCOM) alone accounted for **97% of excess kurtosis**!
     - Zero outliers originated from HOSE (where Kurtosis was naturally 18.48).
  2. **Winsorization Multiverse:**
     - Under standard 0.5% winsorization: Kurtosis drops to $10.84$, skewness to $1.72$, and Cohen's $d$ rises from $0.0557$ to **$0.0729$**.
     - Pooled sample passes DSR across all trial horizons $N \in [1, 2, 3]$:
       - $N=1$: $\text{DSR} = 0.9981$ (PASS)
       - $N=2$: $\text{DSR} = 0.9914$ (PASS)
       - $N=3$: $\text{DSR} = 0.9767$ (PASS)
  3. **Exchange-Level Divergence:**
     - **HOSE-only fails DSR at $N \ge 2$**:
       - $N=1$: $\text{DSR} = 0.980$ (PASS)
       - $N=2$: $\text{DSR} = 0.935$ (FAIL $< 0.95$)
       - $N=3$: $\text{DSR} = 0.878$ (FAIL $< 0.95$)
     - Proves that the raw statistical effect is heavily concentrated in illiquid UPCOM/HNX small caps, necessitating exchange-level conditioning in `F203`.
  4. **CSCV Overfitting Probability (PBO):**
     - Combinatorial split across $S=16$ equal-event blocks produced **$\text{PBO} = 0.007$ (0.7%)**, vastly below the 10% danger threshold (PASS), with mean logit $= +6.14$.

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** 4/4 unit tests pass; ruff clean; mypy clean.
- [x] **Gate 2 (Boundary):** DSR and PBO formulas mathematically bounded ($[0, 1]$).
- [x] **Gate 3 (Temporal):** CSCV blocks partitioned preserving temporal integrity.
- [x] **Gate 4 (Distribution):** Formal DSR and PBO computed and reported.
- [x] **Gate 5 (Pipeline):** Integrated on live database; report output to `out/f202b_dsr_pbo_report.json`.

## 4. Identified Defects & Remediation Log
- **Remediation Completed:** Formally exposed the UPCOM outlier distortion and proved PBO safety. Handed off exchange conditioning to `F203`.

## 5. Verification Command & Evidence
```bash
python src/pipeline/f202b_dsr_pbo.py --report out/f202b_dsr_pbo_report.json && python -m pytest tests/test_f202b_dsr.py -x
```
- **Evidence:** `4/4 passed; Raw Kurtosis=4315.77; Winsorized Kurtosis=10.84; Pooled DSR(N=3)=0.9767; CSCV PBO=0.007`.
