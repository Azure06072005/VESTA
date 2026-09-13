# VESTA Closed-Loop Engineering Directory (`Harness/Loop`)

This directory embodies the **Closed-Loop Empirical Engineering (CLEE)** standard for the VESTA autonomous quantitative trading harness.

---

## 1. Directory Structure

```
d:/VESTA/Harness/Loop/
├── verification.md                    <-- Core Instruction: Loop Engineering Standard (English)
├── README.md                          <-- Master Index & Loop Architecture Map (This file)
└── features/                          <-- Dedicated Per-Feature Empirical Verification Loops
    ├── F000_bootstrap_loop.md
    ├── F001_dim_symbol_loop.md
    ├── F001b_dim_symbol_cafef_loop.md
    ├── F002_market_ohlcv_loop.md
    ├── F003_vnstock_news_loop.md
    ├── F004_cafef_news_loop.md
    ├── F004b_cafef_article_body_loop.md
    ├── F004c_cafef_category_news_loop.md
    ├── F005_fundamentals_suite_loop.md
    ├── F006_corporate_events_loop.md
    ├── F007_snapshots_loop.md
    ├── F008_retry_reconciliation_loop.md
    ├── F009_tier_checkpoint_loop.md
    ├── F050_market_index_daily_loop.md
    ├── F051_foreign_flow_loop.md
    ├── F052_cafef_bctc_enhancer_loop.md
    ├── F053_batch_equity_enhancer_loop.md
    ├── F054_stock_research_reports_loop.md
    ├── F055_macro_policy_loop.md
    ├── F056_to_F071_macro_backlog_loop.md
    ├── F072_tier_checkpoint_auxiliary_loop.md
    ├── F101_cross_dataset_validation_loop.md
    ├── F102_pit_join_loop.md
    ├── F103_data_quality_pipeline_loop.md
    ├── F104_ml_dataset_pipeline_loop.md
    ├── F201_sentiment_meanreversion_loop.md
    ├── F202_statistical_robustness_loop.md
    ├── F202b_dsr_pbo_loop.md
    ├── F203_regime_audit_loop.md       <-- CURRENT SOLE ACTIVE FEATURE (WIP=1)
    ├── F301_to_F303_nlp_models_loop.md
    ├── F401_to_F402_inference_feedback_loop.md
    └── F901_to_F902_execution_compliance_loop.md
```

---

## 2. Master Feature Loop Registry & Empirical State

| Feature ID | Feature Name | State | Key Invariant / Empirical Finding | Dedicated Loop File |
| :--- | :--- | :---: | :--- | :--- |
| **F000** | Environment & Schema Bootstrap | `passing` | DB initialized; 3 schemas (`staging`, `core`, `meta`) | [F000_bootstrap_loop.md](file:///d:/VESTA/Harness/Loop/features/F000_bootstrap_loop.md) |
| **F001** | Reference Crawler (dim_symbol) | `passing` | 3,446 symbols; master reference universe | [F001_dim_symbol_loop.md](file:///d:/VESTA/Harness/Loop/features/F001_dim_symbol_loop.md) |
| **F001b**| CafeF Directory Cross-Reference | `passing` | 984 OTC/unlisted equities; CenterId mapping | [F001b_dim_symbol_cafef_loop.md](file:///d:/VESTA/Harness/Loop/features/F001b_dim_symbol_cafef_loop.md) |
| **F002** | Market OHLCV Daily Crawler | `passing` | 5,178,766 daily bars up to 2026-09-11; volume > 0 filter | [F002_market_ohlcv_loop.md](file:///d:/VESTA/Harness/Loop/features/F002_market_ohlcv_loop.md) |
| **F003** | vnstock News Crawler | `passing` | Primary equity news; retry backoff | [F003_vnstock_news_loop.md](file:///d:/VESTA/Harness/Loop/features/F003_vnstock_news_loop.md) |
| **F004** | CafeF News Crawler | `passing` | 587k CafeF rows; 661k total news; midnight timestamp lag | [F004_cafef_news_loop.md](file:///d:/VESTA/Harness/Loop/features/F004_cafef_news_loop.md) |
| **F004b**| CafeF Article Body Enrichment | `passing` | 100% full Vietnamese body extraction (1.2k–8.4k chars) | [F004b_cafef_article_body_loop.md](file:///d:/VESTA/Harness/Loop/features/F004b_cafef_article_body_loop.md) |
| **F004c**| CafeF Category News Orchestrator | `passing` | 100% precision editorial crawl; zero false-positive acronyms | [F004c_cafef_category_news_loop.md](file:///d:/VESTA/Harness/Loop/features/F004c_cafef_category_news_loop.md) |
| **F005** | Fundamental Crawler Suite | `passing` | 30-day disclosure lag; balance sheet API gap accepted | [F005_fundamentals_suite_loop.md](file:///d:/VESTA/Harness/Loop/features/F005_fundamentals_suite_loop.md) |
| **F006** | Corporate Events Crawler | `passing` | Adjustments calculation; empty price_adjustment_events logged | [F006_corporate_events_loop.md](file:///d:/VESTA/Harness/Loop/features/F006_corporate_events_loop.md) |
| **F007** | Snapshot Crawlers | `passing` | Daily valuation snapshots; TCBS removal handled | [F007_snapshots_loop.md](file:///d:/VESTA/Harness/Loop/features/F007_snapshots_loop.md) |
| **F008** | Retry & Reconciliation Orchestrator | `passing` | `meta.crawl_progress` state tracking; idempotent retry | [F008_retry_reconciliation_loop.md](file:///d:/VESTA/Harness/Loop/features/F008_retry_reconciliation_loop.md) |
| **F009** | Tier Checkpoint (F0xx) | `passing` | Repo-wide verification; 4 cross-cutting modules | [F009_tier_checkpoint_loop.md](file:///d:/VESTA/Harness/Loop/features/F009_tier_checkpoint_loop.md) |
| **F050** | Market Index Daily Crawler | `passing` | 206,313 index bars; VNINDEX, VN30, HNX, VIX, DXY, TNX | [F050_market_index_daily_loop.md](file:///d:/VESTA/Harness/Loop/features/F050_market_index_daily_loop.md) |
| **F051** | Foreign Investor Flow Crawler | `passing` | Pure volume metrics; fabricated monetary columns eliminated | [F051_foreign_flow_loop.md](file:///d:/VESTA/Harness/Loop/features/F051_foreign_flow_loop.md) |
| **F052** | CafeF BCTC Enhancer | `blocked` | Raw Vietnamese dictionary schema requires mapping | [F052_cafef_bctc_enhancer_loop.md](file:///d:/VESTA/Harness/Loop/features/F052_cafef_bctc_enhancer_loop.md) |
| **F053** | Batch Equity Enhancer | `not_started`| Paused behind F203 per WIP=1 | [F053_batch_equity_enhancer_loop.md](file:///d:/VESTA/Harness/Loop/features/F053_batch_equity_enhancer_loop.md) |
| **F054** | Stock Research Reports Crawler | `not_started`| Broker consensus target prices; paused behind F203 | [F054_stock_research_reports_loop.md](file:///d:/VESTA/Harness/Loop/features/F054_stock_research_reports_loop.md) |
| **F055** | Macro Policy News Crawler & Audit | `not_started`| 477.7k articles: 91.3% pure macro vs 8.7% tickers; no physical merge | [F055_macro_policy_loop.md](file:///d:/VESTA/Harness/Loop/features/F055_macro_policy_loop.md) |
| **F056–F071** | Macro / Regulatory Backlog | `not_started`| 16 auxiliary crawlers paused behind F203 | [F056_to_F071_macro_backlog_loop.md](file:///d:/VESTA/Harness/Loop/features/F056_to_F071_macro_backlog_loop.md) |
| **F072** | Tier Checkpoint (F05x Auxiliary) | `not_started`| 7 staging DBs archived with 0 unmerged rows; macro audit | [F072_tier_checkpoint_auxiliary_loop.md](file:///d:/VESTA/Harness/Loop/features/F072_tier_checkpoint_auxiliary_loop.md) |
| **F101** | Cross-Dataset Validation Gate | `passing` | Referential integrity across 7 core tables; zero orphan tickers | [F101_cross_dataset_validation_loop.md](file:///d:/VESTA/Harness/Loop/features/F101_cross_dataset_validation_loop.md) |
| **F102** | Point-in-Time Join (pit_events) | `passing` | 658,182 events; 15:00 cutoff; 1,038 zero prices sanitized | [F102_pit_join_loop.md](file:///d:/VESTA/Harness/Loop/features/F102_pit_join_loop.md) |
| **F103** | Enterprise 11-Technique Quality | `passing` | 22/22 checks passed on canonical database | [F103_data_quality_pipeline_loop.md](file:///d:/VESTA/Harness/Loop/features/F103_data_quality_pipeline_loop.md) |
| **F104** | ML Feature Pipeline | `passing` | Zero forward contamination; chronological train/val/test splits | [F104_ml_dataset_pipeline_loop.md](file:///d:/VESTA/Harness/Loop/features/F104_ml_dataset_pipeline_loop.md) |
| **F201** | Sentiment Mean-Reversion Backtest| `passing` | Pooled mean diff +1.8745%, p=8.39e-12; sign flips detected | [F201_sentiment_meanreversion_loop.md](file:///d:/VESTA/Harness/Loop/features/F201_sentiment_meanreversion_loop.md) |
| **F202** | Statistical Robustness Controls | `passing` | Cluster bootstrap by firm and month; trial count bound | [F202_statistical_robustness_loop.md](file:///d:/VESTA/Harness/Loop/features/F202_statistical_robustness_loop.md) |
| **F202b**| Formal DSR & CSCV PBO | `passing` | Kurtosis 4,315 (XDC +3,021%); Winsorized DSR=0.9767; PBO=0.007 | [F202b_dsr_pbo_loop.md](file:///d:/VESTA/Harness/Loop/features/F202b_dsr_pbo_loop.md) |
| **F203** | Regime-Conditional Validity Audit| `passing` | 16 Regimes x 3 Exchanges; sign-flips confirmed; regime gate binding | [F203_regime_audit_loop.md](file:///d:/VESTA/Harness/Loop/features/F203_regime_audit_loop.md) |
| **F301–F303** | NLP Sentiment Models & Gate | `not_started`| PhoBERT fine-tuning; VRAM budget <= 5.5GB; HybridACD | [F301_to_F303_nlp_models_loop.md](file:///d:/VESTA/Harness/Loop/features/F301_to_F303_nlp_models_loop.md) |
| **F401–F402** | Inference Service & Feedback Log| `not_started`| Read-only FastAPI service; out-of-sample realized drift log | [F401_to_F402_inference_feedback_loop.md](file:///d:/VESTA/Harness/Loop/features/F401_to_F402_inference_feedback_loop.md) |
| **F901–F902** | Compliance & Paper Trading | `blocked` | Rule B1 Legal Gate: UBCKNN algorithmic order restrictions | [F901_to_F902_execution_compliance_loop.md](file:///d:/VESTA/Harness/Loop/features/F901_to_F902_execution_compliance_loop.md) |

---

## 3. How to Execute a Feature Loop

When working on any feature in this repository:
1. **Confirm WIP=1:** Verify in `feature_list.json` that only the target feature is in `active` state.
2. **Open the Feature Loop File:** Follow the step-by-step 5-gate checklist in `Harness/Loop/features/Fxxx_loop.md`.
3. **Execute Live Against Canonical DB:** Run the verification command against `d:/VESTA/db/vesta.duckdb`.
4. **Capture Verbatim Terminal Output:** Paste literal command and stdout into the loop file and `feature_list.json`.
5. **Log Architectural Decisions:** If the feature defines or modifies system behavior, record a dated entry in `DECISIONS.md`.
