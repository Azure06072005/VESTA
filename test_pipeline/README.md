# VESTA Modular Test Pipeline (`test_pipeline`)

This directory provides the high-performance testing, verification, and benchmarking environment for VESTA's analytical pipelines, running against the dedicated test database (`db/test_db/vesta_test.duckdb` or `db/vesta_test.duckdb`).

---

## 1. Directory Structure

```
d:/VESTA/test_pipeline/
├── README.md                          <-- Architecture & Usage Guide (This file)
├── f1xx_enrichment/                   <-- Tier F1xx Test Runners (Validation & PIT Joins)
│   ├── __init__.py
│   ├── test_f101_crossref_runner.py   <-- F101: Referential Integrity & Orphan Symbol Audit
│   ├── test_f102_pit_join_runner.py   <-- F102: PIT Event Invariants, Zero Prices & 15:00 Cutoff
│   ├── test_f103_data_quality_runner.py <-- F103: 11-Technique Data Quality Audit
│   └── test_f104_ml_features_runner.py <-- F104: Vectorized ML Features & Non-Overlapping Splits
├── f2xx_validation/                   <-- Tier F2xx Test Runners (Statistical Proof & Auditing)
│   ├── __init__.py
│   ├── test_f201_meanreversion_runner.py <-- F201: Quantitative Mean-Reversion Backtest
│   ├── test_f202_robustness_runner.py <-- F202: Multi-Cluster Bootstrap (Symbol/Month)
│   ├── test_f202b_dsr_pbo_runner.py   <-- F202b: Formal Deflated Sharpe Ratio & CSCV PBO
│   └── test_f203_regime_audit_runner.py <-- F203: 16-Regime x 3-Exchange Matrix & Macro Controls
├── runners/
│   ├── __init__.py
│   └── run_test_pipeline.py           <-- Unified Multi-Tier Orchestrator
├── scripts/
│   └── run_test_pipeline.py           <-- Backward-Compatible CLI Forwarding Shim
└── out/                               <-- Benchmark reports and output Parquet artifacts
```

---

## 2. Execution Commands

### Run Full Test Pipeline (All Tiers, All Features)
```bash
python test_pipeline/runners/run_test_pipeline.py
```

### Run by Specific Tier
```bash
# Execute only Tier F1xx (Data Validation & Enrichment)
python test_pipeline/runners/run_test_pipeline.py --tier f1xx

# Execute only Tier F2xx (Statistical Backtesting & Robustness)
python test_pipeline/runners/run_test_pipeline.py --tier f2xx
```

### Run a Specific Feature Test Runner
```bash
# Run F101 (Referential Integrity Check)
python test_pipeline/f1xx_enrichment/test_f101_crossref_runner.py

# Run F102 (PIT Join & Look-Ahead Audit)
python test_pipeline/f1xx_enrichment/test_f102_pit_join_runner.py

# Run F103 (11-Technique Data Quality Pipeline)
python test_pipeline/f1xx_enrichment/test_f103_data_quality_runner.py

# Run F104 (ML Feature Extraction)
python test_pipeline/f1xx_enrichment/test_f104_ml_features_runner.py

# Run F201 (Mean-Reversion Backtest)
python test_pipeline/f2xx_validation/test_f201_meanreversion_runner.py

# Run F202 (Statistical Bootstrap)
python test_pipeline/f2xx_validation/test_f202_robustness_runner.py

# Run F202b (Deflated Sharpe Ratio & CSCV PBO)
python test_pipeline/f2xx_validation/test_f202b_dsr_pbo_runner.py

# Run F203 (16-Regime x 3-Exchange Audit)
python test_pipeline/f2xx_validation/test_f203_regime_audit_runner.py
```

### Run via Unified Runner with Target Database
```bash
python test_pipeline/runners/run_test_pipeline.py --db-path db/test_db/vesta_test.duckdb --feature f203
```
