# Loop Verification: F203 — Regime-Conditional Validity Audit

## 1. Invariant & Hypothesis Contract
- **Feature ID:** `F203`
- **Feature Name:** Regime-Conditional Validity Audit — Is Mean-Reversion a General Effect or a Bull-Liquidity Artifact?
- **Target State:** `passing` (COMPLETED 2026-09-12)
- **Mathematical / Architectural Invariant:**
  - Audits whether the $+1.87\%$ negative-sentiment mean-reversion effect is robust across market cycles or inverts during liquidity shocks.
  - **Mandatory Data Sanitization Invariants:**
    1. $\text{price\_at\_publish} > 0$ (filters 1,038 zero-price division-by-zero defects).
    2. $\text{volume} > 0$ (filters illiquid trading days to prevent artificial 0.00% ties).
  - **2D Evaluation Grid:** 16 Historical Regimes $\times$ 3 Exchanges (HOSE, HNX, UPCOM).
  - **Dual Metric Evaluation:** Must report both parametric (mean diff, cluster-robust CI) and non-parametric statistics (median diff, win-rate %, loss-rate %, Wilcoxon signed-rank test).
  - **Global Macro Covariate Regression:** Regress returns on global liquidity proxies (`^VIX`, `DX-Y.NYB`, `^TNX`) to determine whether regime sign-flips track dollar liquidity tightening.
  - **Binding Architectural Exit Criterion:** Must record an explicit decision in `DECISIONS.md` choosing one of three paths for PhoBERT training (`F301`):
    - Path A: Full pool with outlier clipping.
    - Path B: Structural crisis exclusion.
    - Path C: Regime-conditioned feature input (SELECTED & BINDING).

## 2. Retrospective Progress Audit (2026-09-12 Audit Findings)
- **The Distributional Trap Exposed:**
  - While arithmetic mean diff is $+1.8745\%$, **the pooled win-rate is only 44.10%** (loss-rate is $48.28\%$, tie-rate is $7.62\%$).
  - **HOSE-only median difference is negative ($-0.1404\%$)**, confirming that on the main exchange, more than half of bad-news events continue to drop or underperform!
  - The positive mean is driven by extreme right-tail skewness in unconstrained UPCOM penny stocks (Kurtosis 4,314).
- **Historical Regime Sign-Flips:**
  - Bear/Crisis regimes invert into negative momentum:
    - 2007 Global Financial Crisis: $-12.95\%$
    - 2011 Tightening/Inflation Crisis: $-3.52\%$
    - 2014 Oil Shock: $-3.91\%$
    - 2022 Real Estate / Bond Crisis: $-4.39\%$
    - 2026 High Valuation Correction: $-1.26\%$
  - Bull regimes show massive rebounds:
    - COVID recovery rally: $+6.74\%$
    - 2016–2017 Pre-frontier rally: $+3.82\%$

## 3. 5-Gate Loop Verification Status
- [x] **Gate 1 (Static):** Linting and type-checking `src/pipeline/f2xx_validation/f203_regime_audit.py` and `tests/test_f203_regime_audit.py`.
- [x] **Gate 2 (Boundary):** Assert $\text{price\_at\_publish} > 0$ and $\text{volume} > 0$ filters strictly applied (zero prices eliminated).
- [x] **Gate 3 (Temporal):** 16 Regimes cleanly partitioned without temporal overlap.
- [x] **Gate 4 (Distribution):** Complete 16x3 matrix with Wilcoxon tests, Median diffs, and Macro interaction.
- [x] **Gate 5 (Pipeline):** Live execution on canonical `vesta.duckdb`; report generated at `out/f203_regime_report.json`; DECISIONS.md entry logged.

## 4. Identified Defects & Remediation Log
- **Remediation Underway:** `src/pipeline/f203_regime_audit.py` designed to execute the full 2D evaluation grid and macro controls.

## 5. Verification Command & Transition Criteria
```bash
python -m pipeline.f203_regime_audit --report out/f203_regime_report.json && pytest tests/test_f203_regime_audit.py -x
```
- **Exit Condition for `passing`:**
  1. CLI command exits `0`.
  2. Report confirms data sanitization applied.
  3. Non-parametric Wilcoxon and median statistics documented for all 16 regimes.
  4. Global macro regression coefficients reported for VIX, DXY, TNX.
  5. Dated entry recorded in `DECISIONS.md`.
  6. Literal terminal output pasted into `feature_list.json` evidence field.
