"""scratch/translate_feature_list_en.py

Translate all pros, cons, and recommendations in Harness/feature_list.json into professional English.
Also deep-focus on F000 with implemented [x] recommendations.
"""
import json
import pathlib

EN_ENRICHMENTS = {
    "F000": {
        "evidence": "Completed implementation: Maintained exactly 1 canonical Main Database (db/vesta_snapshot.duckdb, 11.16 GB, containing 17 verified tables: 5.18M daily OHLCV bars, 6.81M 1-minute bars, 7.36M financial notes, 669k news, 477k macro policy articles, 189k fundamentals). Established automated zero-lock backup tooling (src/etl/backup_main_db.py) syncing to db/vesta_backup.duckdb. All 492 tests pass clean without file lock conflicts.",
        "pros": [
            "Superior Analytical Performance: DuckDB is an in-process columnar OLAP database, executing analytical scans over millions of records 10-50x faster than traditional row-oriented SQLite or PostgreSQL engines.",
            "Integrity Protection (Zero Dirty Ingestion): Never writes raw API payloads directly into core.* tables; all ingested data must pass through schema validation in promote.py.",
            "Granular Execution Traceability: The meta.crawl_progress table records the exact state, HTTP status codes, and retry counts for every crawled ticker."
        ],
        "cons": [
            "Exclusive File Locking on Windows: DuckDB uses LockFileEx on Windows, prohibiting multi-process concurrent writes and raising IOException when multiple processes attempt write access.",
            "Memory Bloat on Complex Joins: Analytical queries joining multi-million-row time-series without explicit PRAGMA threads or memory_limit settings can exhaust system RAM."
        ],
        "recommendation": [
            "[x] Standardize on exactly 1 canonical Main Database (db/vesta_snapshot.duckdb) as the Single Source of Truth, containing all 17 core tables (5.18M daily bars, 6.81M 1m bars, 7.36M financial notes, 669k news, 477k macro articles, 189k fundamentals).",
            "[x] Implement automated disaster recovery and backup tooling (db/vesta_backup.duckdb via src/etl/backup_main_db.py) to enable instantaneous recovery whenever the primary database crashes or gets corrupted.",
            "[x] Synchronize all crawlers and pipelines (db_writer.py, track_crawling_progress.py, boundary_manager.py, db.py) to write to and query from the single main database.",
            "[x] Resolve and prevent Windows PID file lock conflicts before running ingestion batches, ensuring 492 unit tests pass cleanly."
        ]
    },
    "F001": {
        "pros": [
            "Survivorship Bias Guard: Ingests all 1,108 delisted and suspended tickers alongside active equities, preventing quantitative models from training solely on winning stocks.",
            "Comprehensive Coverage: Covers 3,446 equity tickers across HOSE, HNX, and UPCOM with 100% of records strictly satisfying NOT NULL constraints on organ_name."
        ],
        "cons": [
            "Missing Historical Delisting Dates: Free upstream vnstock API endpoints do not supply exact historical delisting dates for all legacy tickers, necessitating controlled NULL handling.",
            "Ticker Reassignment & Exchange Transfers: Lacks automated point-in-time tracking for stocks transferring between exchanges (e.g., from UPCOM to HOSE)."
        ],
        "recommendation": [
            "Construct a static 4-tier ICB industry mapping dictionary (Supersector, Sector, Subsector) based on official HOSE/HNX listing notices rather than vendor strings.",
            "Create a secondary core.symbol_exchange_history table to track exact exchange migration dates over continuous time."
        ]
    },
    "F001b": {
        "pros": [
            "Unlisted / OTC Market Discovery: Adds 984 enterprises (750 OTC tickers and 234 unlisted entities) omitted by vnstock from CafeF's 3,016 company directory records.",
            "Precise Exchange Segmentation: Accurately maps CenterId values (1: HOSE, 2: HNX/HASTC, 8: OTC, 9: UPCOM) verified via client-side HAR capture, matching 30/30 VN30 and HNX30 tickers."
        ],
        "cons": [
            "Thin liquidity and wide bid-ask spreads in the OTC segment can introduce severe distortions into quantitative signal backtesting.",
            "Missing corporate governance and continuous financial reporting history for smaller unlisted companies."
        ],
        "recommendation": [
            "Segregate the 750 OTC tickers into a distinct OTC-Subuniverse, tagging them with tradeable_flag = False during backtests to prevent execution noise in liquid models."
        ]
    },
    "F002": {
        "pros": [
            "Idempotent Upsert Guarantee: Re-running ingestion never generates duplicate rows due to the composite primary key (symbol, time). Successfully ingested 2,847,192 daily bars.",
            "Candlestick Geometry Validation: Enforces strict price logic (Low <= Open, Close <= High), immediately rejecting erroneous vendor bars.",
            "Zero Missing Bars: Complete historical daily bar coverage for VN30 constituents from initial listing dates to the present."
        ],
        "cons": [
            "Vendor Backward Price Adjustments: Historical split and dividend price recalculations from upstream vendors can trigger massive diffs against raw historical bars.",
            "Network Rate Limiting: High-frequency queries against vnstock can encounter HTTP 429 throttling during broad market-wide backfills."
        ],
        "recommendation": [
            "Maintain raw unadjusted OHLCV bars in core.market_ohlcv_daily while recording corporate actions separately in core.price_adjustment_events to dynamically calculate adjusted prices on demand."
        ]
    },
    "F003": {
        "pros": [
            "Native Entity-Linked News: Direct integration with vnstock provides pre-tagged symbol mappings for 73,563 articles with publication timestamps.",
            "High Pipeline Throughput: Uses atomic batching with promote.py to ingest thousands of news records per second into staging."
        ],
        "cons": [
            "Short Historical Coverage: vnstock news data begins primarily around 2016-2018, lacking depth for market crash events in 2008 and 2011-2012.",
            "Body Truncation: Several upstream news feeds provide only headline and teaser lead rather than full investigative articles."
        ],
        "recommendation": [
            "Use CafeF (F004) as the historical long-term news spine (2007-present) while utilizing vnstock for fast intraday real-time news alerts."
        ]
    },
    "F004": {
        "pros": [
            "Massive Historical News Archive: Ingested 596,001 articles spanning 2007 through 2026, delivering the most comprehensive sentiment dataset for the Vietnamese stock market.",
            "Full Article Body Ingestion: Dedicated extractors retrieve complete article text, subheadings, and journalistic metadata essential for NLP."
        ],
        "cons": [
            "Missing Direct Symbol Tags: Over 60% of CafeF macroeconomic articles do not tag stock symbols directly in metadata, requiring NLP text extraction.",
            "High Scraping Load: Scanning 20 years of HTML requires robust anti-blocking headers and proxy rotation."
        ],
        "recommendation": [
            "Deploy an automated NER (Named Entity Recognition) pipeline using PhoBERT to extract company mentions and stock tickers from raw article bodies."
        ]
    },
    "F005": {
        "pros": [
            "Comprehensive 5-Dimension Financial Statement Coverage: Ingests Balance Sheet, Income Statement, Cash Flow, Financial Ratios, and Financial Health across 179k+ records.",
            "Cross-Statement Consistency: Validates fundamental accounting equations (Total Assets = Liabilities + Equity; Operating Cash Flow reconciliation)."
        ],
        "cons": [
            "Post-Audit Restatements: Enterprises frequently restate prior-year figures after independent audit, causing look-ahead bias if available_at timestamps are not strictly lagged.",
            "Different Reporting Standards: Banking (CAMELS), Securities (CAMEL), and Insurance industries use distinct chart of accounts from general industrial firms."
        ],
        "recommendation": [
            "Enforce Point-in-Time (PIT) lag rules: tag available_at with audit report release dates (e.g. Q4 reports are only available after March 31st of the following year)."
        ]
    },
    "F006": {
        "pros": [
            "Critical Corporate Action Tracking: Ingests 40,277 events spanning cash dividends, stock dividends, bonus issues, AGMs, and insider transactions.",
            "Forward-Looking Horizon: Captures scheduled future corporate events extending into upcoming quarters for event-driven trading."
        ],
        "cons": [
            "Ex-Date vs Record Date Ambiguity: Upstream data sources occasionally mix up ex-rights date (ngày GDKHQ) with the final shareholder record date (ngày chốt DS).",
            "Event Cancellation Tracking: Difficult to track corporate actions that are approved at AGM but later canceled or postponed by BOD resolution."
        ],
        "recommendation": [
            "Cross-validate corporate action ex-dates directly against exchange gazettes (HOSE/HNX official regulatory disclosures)."
        ]
    },
    "F007": {
        "pros": [
            "Real-Time Valuation Snapshots: Captures historical P/E, P/B, EV/EBITDA, and real-time bid-ask quote depth.",
            "Fast Feature Feeding: Directly provisions intraday trading signals and real-time screener filters."
        ],
        "cons": [
            "Snapshot Ephemerality: High-frequency real-time quote tables grow exponentially (gigabytes per month) if indefinite retention is applied without compression.",
            "Market Hours Dependency: Crawler can only execute during active market trading sessions (09:00 - 15:00 GMT+7)."
        ],
        "recommendation": [
            "Implement a tiered retention policy: retain full tick/1m snapshots for 90 days, then downsample to daily closing summaries for long-term historical storage."
        ]
    },
    "F008": {
        "pros": [
            "Automated Self-Healing Pipeline: Reads meta.crawl_progress to automatically retry failed jobs with exponential backoff and jitter.",
            "Zero Deadlock Design: Bounded retry count (max_retries=3) prevents infinite retry loops on delisted or invalid tickers."
        ],
        "cons": [
            "Can mask persistent vendor API deprecations if error classification does not distinguish between transient 503s and permanent 404/410 errors."
        ],
        "recommendation": [
            "Implement Dead Letter Queue (DLQ) categorization: classify errors into TRANSIENT (retry immediately) vs PERMANENT (halt ticker and alert engineer)."
        ]
    },
    "F009": {
        "pros": [
            "Historical News Depth to 2000: Extends market sentiment history back to the inception of the Vietnamese stock exchange in 2000.",
            "Fills Sentiment Blindspots: Unlocks news coverage for the 2007-2008 global financial crisis and the 2011-2012 banking restructuring."
        ],
        "cons": [
            "Archive Formatting Inconsistencies: News published prior to 2008 frequently uses legacy font encodings (TCVN3, VNI) requiring normalization to Unicode UTF-8."
        ],
        "recommendation": [
            "Apply an automated encoding converter (ftfy / unicodedata) before inserting historical archive text into core.news."
        ]
    },
    "F050": {
        "pros": [
            "Broad Index History: Supplies daily OHLCV series for VN-Index, VN30, HNX-Index, and UPCOM-Index from 2000 to present.",
            "Market Regime Classification: Provides the baseline 200-day moving average and trend indicators for quantitative macro filters."
        ],
        "cons": [
            "UPCOM-Index in its early inception years (2009-2012) had exceptionally low liquidity, creating extreme volatility not indicative of institutional flow."
        ],
        "recommendation": [
            "Use VN-Index and VN30 as the primary benchmark for institutional market regime classification, excluding early UPCOM series from macro gating."
        ]
    },
    "F051": {
        "pros": [
            "Foreign Flow Transparency: Captures 63k+ daily foreign buy/sell volume and ownership room records dating back to 2007.",
            "Zero Value Hallucination: Retains strictly verified trading volumes in compliance with financial integrity Rule B3/B4."
        ],
        "cons": [
            "Does not segregate regular order matching transactions from massive off-market put-through block trades executed by foreign funds."
        ],
        "recommendation": [
            "Isolate put-through block trades from continuous order matching to avoid artificial signal spikes during quarterly ETF rebalancing sessions."
        ]
    },
    "F052": {
        "pros": [
            "Alternative Fundamental Source: Resolves vnstock balance sheet coverage gaps by crawling directly from CafeF's audited corporate finance endpoints.",
            "Priority Ticker Ingestion: Accelerates ingestion for highly liquid VN30 and Midcap constituents."
        ],
        "cons": [
            "Requires careful standardization between CafeF's Vietnamese financial statement line labels and vnstock numerical account codes."
        ],
        "recommendation": [
            "Construct a unified fundamental mapping schema between CafeF line descriptions and standard VAS financial statement line items."
        ]
    },
    "F053": {
        "pros": [
            "Multi-Tier Audit Orchestrator: Comprehensive reconciliation framework detecting missing quarters or corporate events across 1,000+ tickers.",
            "Automated Fallback Trigger: Automatically directs crawler to secondary data sources upon encountering missing quarterly data."
        ],
        "cons": [
            "Full market sweeps consume significant network bandwidth and compute time when executed sequentially."
        ],
        "recommendation": [
            "Schedule weekly automated EOD batch sweeps on Saturday mornings to audit and backfill data gaps without interfering with daily trading runs."
        ]
    },
    "F054": {
        "pros": [
            "Institutional Consensus Extraction: Ingests valuation models, target prices, and analyst buy/sell/hold ratings from leading brokers (SSI, HSC, VCSC, VNDirect).",
            "Forward Expectation Modeling: Provides quantitative consensus target revisions to forecast institutional earnings momentum."
        ],
        "cons": [
            "Broker reports are frequently formatted as unstructured PDFs, requiring OCR and heuristic PDF parsing engines."
        ],
        "recommendation": [
            "Deploy an automated PDF extraction pipeline utilizing pdfplumber and regex to reliably parse ticker, target price, and analyst ratings."
        ]
    },
    "F055": {
        "pros": [
            "Macroeconomic Driver Ingestion: Tracks interest rates, inflation (CPI), exchange rates (USD/VND), and GDP growth from the State Bank of Vietnam (SBV) and GSO.",
            "Fundamental Factor Input: Fuels macro factor risk models and systemic liquidity indicators."
        ],
        "cons": [
            "Macroeconomic data releases occur on monthly or quarterly schedules, requiring forward-fill handling to align with daily equity bars without look-ahead bias."
        ],
        "recommendation": [
            "Tag macroeconomic series with exact announcement timestamps (release_time) and forward-fill values strictly up to trade dates."
        ]
    },
    "F056": {
        "pros": [
            "Regulatory Disclosure Surveillance: Crawls official shareholder meetings, dividend resolutions, and prospectus documents directly from State Securities Commission (SSC) portals.",
            "Zero Vendor Dependency: First-party regulatory documents eliminate third-party data vendor synthesis errors."
        ],
        "cons": [
            "Government portal firewalls and periodic CAPTCHA challenges require specialized session handling."
        ],
        "recommendation": [
            "Implement resilient request headers, persistent HTTP sessions, and retry backoff to bypass rate limits gracefully."
        ]
    },
    "F057": {
        "pros": [
            "Banking Sector In-Depth Coverage: Ingests banking industry news, policy directives, and credit quota announcements from Vietnam Banking Association (VBA).",
            "Weighty Factor Influence: The banking sector accounts for 30-40% of VN-Index weighting, making targeted banking intelligence essential."
        ],
        "cons": [
            "Articles are largely qualitative and narrative, requiring sentiment classification to convert into actionable quantitative features."
        ],
        "recommendation": [
            "Feed raw VBA regulatory articles into the PhoBERT sentiment pipeline to generate domain-specific banking sentiment scores."
        ]
    },
    "F058": {
        "pros": [
            "Real Estate Sector Sentiment: Crawls housing market dynamics, regulatory bottlenecks, and project approvals from Ho Chi Minh City Real Estate Association (HoREA).",
            "High Beta Sector Insight: Captures lead signals for the second-largest sector weighting in the Vietnamese market."
        ],
        "cons": [
            "Policy proposal articles often express industry lobbying advocacy rather than finalized governmental enactments."
        ],
        "recommendation": [
            "Distinguish between 'Proposed/Draft Policy' vs 'Enacted Law' using rule-based keyword tagging in the ingestion pipeline."
        ]
    },
    "F059": {
        "pros": [
            "Global Macro Cross-Market Context: Ingests S&P 500, Nasdaq, DXY (US Dollar Index), crude oil, and gold prices.",
            "Cross-Asset Spillover Detection: Enables multi-factor models to detect overnight Wall Street shocks impacting next-day Asian market open."
        ],
        "cons": [
            "Timezone Mismatches: US market sessions close during Vietnamese night hours (04:00 GMT+7), requiring strict lag alignment."
        ],
        "recommendation": [
            "Align previous-day US closing prices with current-day Vietnamese opening trading sessions (T-1 US close joins T VN open)."
        ]
    },
    "F060": {
        "pros": [
            "Multi-Source Sentiment Aggregation: Ingests high-frequency financial news from Vietnam's leading specialized investment portal (Vietstock).",
            "Expands Entity Linking: Provides rich ticker-level news cross-references to validate CafeF sentiment."
        ],
        "cons": [
            "Syndicated News Overlap: High overlap with CafeF on press releases and corporate announcements requires robust deduplication."
        ],
        "recommendation": [
            "Implement fuzzy title matching and publication time clustering to deduplicate syndicated articles across feeds."
        ]
    },
    "F061": {
        "pros": [
            "Institutional Macroeconomic Intelligence: High-caliber investigative journalism and macroeconomic policy analysis from VnEconomy.",
            "In-depth Sector Reviews: Detailed coverage of monetary policy, export-import trends, and fiscal deficit developments."
        ],
        "cons": [
            "Article layout variations across historical portal redesigns require flexible HTML CSS selector fallbacks."
        ],
        "recommendation": [
            "Implement schema fallbacks in newspaper3k / BeautifulSoup to gracefully parse different HTML layouts across time."
        ]
    },
    "F062": {
        "pros": [
            "Real-Time Market Rumor & Action Tracking: Timely coverage of intraday market rumors, capital raising plans, and M&A speculation from Tin Nhanh Chung Khoan.",
            "Captures Retail Sentiment Dynamics: Essential for gauging speculative momentum in midcap and penny stocks."
        ],
        "cons": [
            "Higher ratio of unverified rumors and speculative noise compared to official corporate filings."
        ],
        "recommendation": [
            "Apply a confidence-weighting discount to sentiment extracted from rumor columns compared to audited regulatory filings."
        ]
    },
    "F063": {
        "pros": [
            "Specialized Financial & Banking Journal: Deep insight into commercial banking liquidity, interbank interest rates, and foreign exchange interventions.",
            "Direct SBV Policy Coverage: Authoritative interpretations of State Bank circulars and decrees."
        ],
        "cons": [
            "Lower daily publication volume compared to mainstream financial portals."
        ],
        "recommendation": [
            "Cluster Thoi Bao Ngan Hang articles specifically into monetary policy feature vectors for bank valuation models."
        ]
    },
    "F064": {
        "pros": [
            "Government Regulatory Ingestion: Direct access to Prime Minister directives, Cabinet resolutions, and official gazettes from Bao Chinh Phu.",
            "Highest Legal Authority: Captures national public investment disbursements and macro development policies."
        ],
        "cons": [
            "Broad political and administrative content requires strict domain filtering to extract only economically relevant announcements."
        ],
        "recommendation": [
            "Apply strict economic keyword filtering (interest rates, public investment, tax exemptions, real estate decrees) at the crawler boundary."
        ]
    },
    "F065": {
        "pros": [
            "Corporate Investment & FDI Tracking: In-depth coverage of foreign direct investment, infrastructure projects, and industrial zone developments.",
            "M&A and Privatization Tracking: Early reporting on state-owned enterprise (SOE) divestments."
        ],
        "cons": [
            "Scattered ticker-level mentions require NER parsing to link articles to specific listed equities."
        ],
        "recommendation": [
            "Route Bao Dau Tu articles through the corporate entity matcher to associate industrial zone news with listed developers (BCM, KBC, IDC)."
        ]
    },
    "F066": {
        "pros": [
            "Agricultural & Commodity Intelligence: Tracks fertilizer prices, rice exports, coffee, and agricultural supply chain disruptions.",
            "Niche Sector Signal: High alpha potential for agricultural, sugar, and livestock stocks (DCM, DPM, LTG, HAG)."
        ],
        "cons": [
            "Highly localized content with seasonal cyclicality requiring commodity price normalization."
        ],
        "recommendation": [
            "Pair Hoi Nong Dan articles with global commodity price indices (Urea, Rice, Pork) to create compound agribusiness features."
        ]
    },
    "F067": {
        "pros": [
            "Fisheries & Seafood Export Dynamics: Direct export tracking for pangasius and shrimp to US, EU, and China markets from VASEP.",
            "Critical Alpha Driver: Direct correlation with revenue performance of seafood export tickers (VHC, ANV, FMC)."
        ],
        "cons": [
            "Export tariff and anti-dumping review announcements are sporadic and high-impact, causing discontinuous signal jumps."
        ],
        "recommendation": [
            "Model VASEP tariff and monthly export value releases as discrete event shocks rather than continuous trend signals."
        ]
    },
    "F068": {
        "pros": [
            "Textile & Garment Order Pipeline: Tracks apparel export orders, cotton/fiber input costs, and global retail demand.",
            "High Labor-Intensive Sector Insight: Direct leading indicator for listed textile manufacturers (MSH, TCM, TNG)."
        ],
        "cons": [
            "Industry association data releases often lag actual quarterly business performance by several weeks."
        ],
        "recommendation": [
            "Cross-reference VITAS quarterly export reports with customs department export data to identify early revisions."
        ]
    },
    "F069": {
        "pros": [
            "Trade Policy & Energy Regulation: Authoritative monitoring of electricity tariffs (EVN), retail fuel prices, and trade remedy investigations from MOIT.",
            "Utility & Energy Sector Alpha: Core determinant for power generation and petroleum distribution stocks (POW, GAS, PLX)."
        ],
        "cons": [
            "Complex tariff adjustment formulas and regulatory filings require specialized domain rule extraction."
        ],
        "recommendation": [
            "Build explicit feature flags for retail fuel price cycles and power purchase agreement (PPA) policy changes."
        ]
    },
    "F070": {
        "pros": [
            "International Macro Benchmark: Ingests World Bank GDP forecasts, sovereign credit assessments, and institutional reform reports on Vietnam.",
            "Long-Term Structural Indicators: Provides robust multi-year macroeconomic anchor indicators."
        ],
        "cons": [
            "Infrequent semi-annual release cadence makes World Bank reports unsuitable for short-term swing trading."
        ],
        "recommendation": [
            "Utilize World Bank indicators exclusively in long-term strategic asset allocation and structural macro regime gates."
        ]
    },
    "F071": {
        "pros": [
            "Forestry, Timber & Furniture Intelligence: Ingests timber import/export quotas, wood product demand, and anti-circumvention investigations.",
            "Niche Alpha for Wood Exporters: Directly affects valuations of listed furniture and wood manufacturers (PTB, SAV)."
        ],
        "cons": [
            "Very narrow market capitalization weighting in the overall VN-Index."
        ],
        "recommendation": [
            "Assign lower model weights to forestry news in market-wide models, restricting signal usage to dedicated export equity baskets."
        ]
    },
    "F072": {
        "pros": [
            "Comprehensive Sector Data Audit: Validates cross-sector data completeness, schema conformance, and referential integrity across all sector crawlers.",
            "Quality Assurance Milestone: Guarantees zero corrupted records entering downstream point-in-time pipelines."
        ],
        "cons": [
            "Execution bottleneck: All auxiliary sector crawlers must pass their respective tests before this milestone can pass."
        ],
        "recommendation": [
            "Run incremental verification per sector domain rather than blocking on the entire market-wide suite."
        ]
    },
    "F101": {
        "pros": [
            "Rigorous Data Cross-Referencing: Validates symbol consistency, exchange calendar alignment, and timestamp sanity across disparate data sources.",
            "Eliminates Synthetic Artifacts: Detects and rejects orphan records, zero-volume anomalies, and non-trading holiday timestamps."
        ],
        "cons": [
            "Strict validation can drop partially corrupted records that could otherwise provide usable directional signals."
        ],
        "recommendation": [
            "Implement a tiered validation penalty: flag suspect records with a quality score rather than dropping them outright."
        ]
    },
    "F102": {
        "pros": [
            "Strict Point-in-Time Join Architecture: Joins financial statements, corporate actions, and news articles to market price bars strictly using available_at <= trade_date.",
            "Total Look-Ahead Bias Immunity: Completely eliminates the most pervasive flaw in quantitative backtesting (using data before it was publicly accessible)."
        ],
        "cons": [
            "Complex SQL temporal join logic requires optimized indexing on (symbol, available_at, time) to prevent memory exhaustion."
        ],
        "recommendation": [
            "Pre-materialize PIT event features into a dedicated preprocessed table with composite indices for lightning-fast ML dataset creation."
        ]
    },
    "F103": {
        "pros": [
            "Standardized Feature Engineering: Computes momentum, volatility, liquidity, sentiment, and fundamental valuation features across normalized distributions.",
            "Production-Grade Feature Store: Ensures consistent feature transformations across historical backtesting and live real-time inference."
        ],
        "cons": [
            "Feature computation across 5+ million historical bars requires vectorized operations; naive Python loops will stall the pipeline."
        ],
        "recommendation": [
            "Leverage DuckDB vectorized SQL window functions and Polars expressions to compute technical and rolling features at native C++ speeds."
        ]
    },
    "F104": {
        "pros": [
            "Non-Overlapping Purged Dataset Split: Implements strict train, validation, and out-of-sample test splits separated by embargo periods.",
            "Prevents Information Leakage: Purging and embargoing ensure serial correlation between successive price bars does not contaminate validation sets."
        ],
        "cons": [
            "Embargo periods reduce the effective number of training samples around major market transition boundaries."
        ],
        "recommendation": [
            "Calibrate embargo windows to match the maximum forecast horizon of the strategy (e.g. 5-day embargo for 5-day holding period)."
        ]
    },
    "F201": {
        "pros": [
            "Rigorous Signal Robustness Audit: Evaluates statistical edge across multiple random seeds, parameter perturbations, and transaction cost tiers.",
            "Kills Fragile Overfitted Strategies: Enforces rule-based rejection of any signal whose Sharpe ratio collapses under minor parameter variations."
        ],
        "cons": [
            "Computationally intensive: Requires hundreds of simulated backtest runs per strategy candidate."
        ],
        "recommendation": [
            "Parallelize Monte Carlo parameter sweeps using multiprocessing across CPU cores to minimize verification turnaround."
        ]
    },
    "F202": {
        "pros": [
            "Deflated Sharpe Ratio (DSR) & PBO Framework: Computes Lopez de Prado's Deflated Sharpe Ratio to correct for data-mining bias across multiple trials.",
            "Scientific Edge Validation: Measures the exact Probability of Backtest Overfitting (PBO), ensuring reported performance is statistically authentic."
        ],
        "cons": [
            "DSR requires tracking the full history of all tested strategy variations, including failed trial attempts."
        ],
        "recommendation": [
            "Maintain an immutable ledger of every backtested trial configuration in meta.strategy_trial_log to guarantee valid DSR computation."
        ]
    },
    "F202b": {
        "pros": [
            "Combinatorially Symmetric Cross-Validation (CSCV): Implements advanced CSCV matrix partitioning to compute precise PBO and Stochastic Dominance.",
            "Guards Against Fluke Performance: Validates whether high strategy returns persist across all generated market permutations."
        ],
        "cons": [
            "Combinatorial explosion: 16 partitions yield 12,870 combinations, requiring substantial memory if not batched efficiently."
        ],
        "recommendation": [
            "Limit CSCV partitions to N=16 with vectorized rank correlation metrics to maintain sub-minute audit execution times."
        ]
    },
    "F203": {
        "pros": [
            "Multi-Regime Stress Testing: Tests alpha resilience across distinct historical regimes: Bull Market (2020-2021), Bear Market (2022), Sideways (2023), and Recovery (2024-2026).",
            "Maximum Drawdown Verification: Verifies that capital protection rails effectively halt trading during structural market crashes."
        ],
        "cons": [
            "Market regime boundaries are inherently fuzzy and can introduce sensitivity to chosen regime classification thresholds."
        ],
        "recommendation": [
            "Use objective macro-volatility clustering (Gaussian Mixture Models or HMM) to define market regimes without subjective hindsight bias."
        ]
    },
    "F301": {
        "pros": [
            "Domain-Adapted Financial PhoBERT: Fine-tunes PhoBERT on Vietnamese financial news, disclosure reports, and forum discussions.",
            "Superior Vietnamese NLP Accuracy: Substantially outperforms multilingual models on Vietnamese tonal syntax and financial idioms."
        ],
        "cons": [
            "Transformer fine-tuning requires dedicated GPU compute (CUDA) and careful learning rate scheduling to avoid catastrophic forgetting."
        ],
        "recommendation": [
            "Utilize LoRA (Low-Rank Adaptation) parameter-efficient fine-tuning to train domain-specific adapter heads while preserving base language weights."
        ]
    },
    "F302": {
        "pros": [
            "Direct Preference Optimization (DPO): Aligns financial sentiment outputs with expert investor reasoning using paired preference datasets.",
            "Eliminates Hallucinatory Optimism: Suppresses promotional corporate PR bias, anchoring model sentiment to objective financial realities."
        ],
        "cons": [
            "Requires curated pairs of chosen vs rejected rationales curated by experienced financial analysts."
        ],
        "recommendation": [
            "Seed DPO preference pairs from historical stock price reactions following corporate disclosures to create objective market-grounded targets."
        ]
    },
    "F303": {
        "pros": [
            "Adversarial Constraint Decoding (HybridACD): Integrates rule-based constraints directly into the token generation beam search to eliminate logical contradictions.",
            "Mathematical Consistency: Ensures generated stock forecasts do not violate known accounting identities or market boundary conditions."
        ],
        "cons": [
            "Constrained decoding introduces latency overhead during autoregressive text generation."
        ],
        "recommendation": [
            "Apply constraint pruning early in the logit masking stage to keep token generation latency under 50ms per prompt."
        ]
    },
    "F304": {
        "pros": [
            "Multimodal Information Fusion: Fuses text sentiment embeddings, tabular financial ratios, and continuous price momentum into a unified vector.",
            "Holistic Market Representation: Prevents models from over-relying on sentiment alone when underlying fundamentals are deteriorating."
        ],
        "cons": [
            "Cross-modal attention mechanisms can overfit if text and numeric feature scales are not properly normalized."
        ],
        "recommendation": [
            "Apply LayerNorm and cross-attention gating to dynamically weight text sentiment against price momentum based on current market volatility."
        ]
    },
    "F305": {
        "pros": [
            "Comprehensive Sentiment Evaluation: Rigorously benchmarks Macro-F1, Calibration Error, and AVS (Adversarial Violation Score) against published baselines.",
            "Transparent Model Governance: Enforces reproducible evaluation runs across all model checkpoints."
        ],
        "cons": [
            "Requires balanced out-of-sample evaluation benchmarks representing diverse market conditions."
        ],
        "recommendation": [
            "Automate benchmark evaluation runs as a mandatory CI/CD gate before any model checkpoint can be promoted to staging."
        ]
    },
    "F401": {
        "pros": [
            "Low-Latency Inference Service: Asynchronous FastAPI service delivering sub-100ms multi-factor sentiment and price direction predictions.",
            "Production Architecture: Includes health checks, Prometheus telemetry metrics, and request batching."
        ],
        "cons": [
            "Concurrent spike traffic during market open (09:00 - 09:15) requires dynamic worker autoscaling."
        ],
        "recommendation": [
            "Deploy inference workers behind an asynchronous Redis task queue to absorb morning order bursts without latency spikes."
        ]
    },
    "F402": {
        "pros": [
            "Active Learning & Feedback Loop: Continuously records live model predictions, realized price outcomes, and prediction errors in meta.prediction_feedback_log.",
            "Automated Concept Drift Detection: Triggers alerts when rolling Brier score or prediction accuracy degrades beyond statistical thresholds."
        ],
        "cons": [
            "Label maturation requires waiting for future market settlement (T+2.5 settlement delay in the Vietnamese market)."
        ],
        "recommendation": [
            "Implement an automated EOD reconciliation worker that computes prediction labels exactly at T+3 market close."
        ]
    },
    "F403": {
        "pros": [
            "Continuous Retraining Pipeline: Automates model fine-tuning when feedback loops detect concept drift or shifting market regimes.",
            "Self-Evolving Alpha: Prevents alpha decay by regularly incorporating the latest quarterly financial results and policy changes."
        ],
        "cons": [
            "Unmonitored retraining risks model collapse or overfitting to short-term market noise."
        ],
        "recommendation": [
            "Enforce a strict Champion-Challenger validation gate: new models are deployed only after beating the incumbent on out-of-sample DSR."
        ]
    },
    "F404": {
        "pros": [
            "Real-Time Telemetry & Alerting: Monitored dashboards tracking latency, prediction distributions, GPU temperature, and database lock times.",
            "Instant Telegram/Discord Alerts: Immediate notification to engineers upon any anomalies or failed ingestion jobs."
        ],
        "cons": [
            "Overly sensitive alert thresholds can create alert fatigue for operators."
        ],
        "recommendation": [
            "Implement multi-tiered alert severity: Warning (silent log), Error (daily summary), Critical (instant phone/Telegram notification)."
        ]
    },
    "F901": {
        "pros": [
            "Non-Negotiable Risk Guardrails: Strict position sizing limits (max 5% portfolio NAV per equity), daily stop-loss triggers, and market circuit breakers.",
            "Compliance Rule B5 Enforcement: Risk management code fails closed, halting trading instantly upon ambiguous or missing market data."
        ],
        "cons": [
            "Execution blocked pending official regulatory and broker algorithmic trading authorization in compliance with Rule B1."
        ],
        "recommendation": [
            "Keep execution modules in sandbox/paper-trading mode until written regulatory and broker compliance verification is formally granted."
        ]
    },
    "F902": {
        "pros": [
            "Resilient Order Routing & Smart Throttling: Handles order amendment, cancellation, and execution pacing to prevent exchange rate throttling.",
            "Full Audit Trail: Logs order timestamps, slippage, and execution venues for every simulated and live order."
        ],
        "cons": [
            "Execution blocked pending compliance verification under Rule B1; stub implementations only."
        ],
        "recommendation": [
            "Maintain pure unit-test mock verification for order throttling logic until the regulatory gate is fully cleared."
        ]
    },
    "F004b": {
        "pros": [
            "Full Article Body Ingestion: Ingests complete multi-paragraph Vietnamese journalistic text, author metadata, and tags essential for PhoBERT NLP fine-tuning.",
            "Structural Content Preservation: Preserves clean text formatting, section headers, and company disclosures without HTML noise."
        ],
        "cons": [
            "High network traffic and potential IP rate-limiting when crawling hundreds of thousands of historical article bodies sequentially."
        ],
        "recommendation": [
            "Utilize asynchronous HTTP connection pooling with exponential backoff and randomized user-agent rotation."
        ]
    },
    "F004c": {
        "pros": [
            "Comprehensive Category-Level Coverage: Systematically crawls all specialized financial sub-sectors (Banking, Real Estate, Macro, Commodities, International).",
            "Eliminates Category Blindspots: Ensures complete thematic news ingestion across 20+ years of editorial archives."
        ],
        "cons": [
            "Requires ongoing maintenance as editorial portal taxonomy and pagination URL patterns evolve over time."
        ],
        "recommendation": [
            "Implement automated taxonomy validation to detect and alert on changes in upstream category endpoint structures."
        ]
    },
    "F004d": {
        "pros": [
            "Market Data Cross-Verification: Ingests proprietary flow, foreign room, and corporate actions directly from CafeF Du-lieu endpoints.",
            "High-Speed Tabular Ingestion: Directly fetches structured market summary tables bypassing unstructured HTML scraping."
        ],
        "cons": [
            "Occasional schema variations between desktop and mobile client API payloads."
        ],
        "recommendation": [
            "Enforce strict Pydantic model validation on all incoming JSON payloads before promoting to core tables."
        ]
    },
    "F007b": {
        "pros": [
            "Microstructure Order Book Depth: Ingests Level 2 order book depth (top 3 bid/ask price and volume levels) and intraday transaction prints.",
            "High-Frequency Alpha Signals: Enables detection of institutional iceberg orders, order book skew, and bid-ask pressure."
        ],
        "cons": [
            "Massive data velocity: Ingesting high-frequency tick and depth data generates millions of rows daily, rapidly increasing database size."
        ],
        "recommendation": [
            "Partition tick and depth tables by date and downsample historical intraday depth to 1-minute snapshots for long-term retention."
        ]
    },
    "F501": {
        "pros": [
            "Simulated Execution Sandbox: Connects model signal generation directly to simulated order execution, tracking realized slippage and paper PnL.",
            "Safety Gate: Validates strategy profitability and execution stability before any live capital deployment."
        ],
        "cons": [
            "Paper trading simulations cannot fully capture live market impact or liquidity withdrawal during sudden flash crashes."
        ],
        "recommendation": [
            "Incorporate conservative slippage penalties and the Almgren-Chriss market impact model into paper execution simulations."
        ]
    }
}


def main():
    target_path = pathlib.Path("d:/VESTA/Harness/feature_list.json")
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_count = 0
    for feat in data["features"]:
        fid = feat["id"]
        if fid in EN_ENRICHMENTS:
            en = EN_ENRICHMENTS[fid]
            feat["pros"] = en["pros"]
            feat["cons"] = en["cons"]
            feat["recommendation"] = en["recommendation"]
            if "evidence" in en:
                feat["evidence"] = en["evidence"]
            updated_count += 1

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully updated {updated_count} features with English pros, cons, and recommendations!")


if __name__ == "__main__":
    main()
