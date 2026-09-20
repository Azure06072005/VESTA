-- F000: Environment & schema bootstrap
-- Three schemas: staging (raw crawler output, pre-validation),
-- core (validated, promoted data), meta (pipeline bookkeeping).
-- This file is idempotent: safe to re-run against an existing database.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS meta;

-- meta.crawl_progress: created here (F000), queried/written by F008's
-- retry module and by every crawler from F002 onward. Do not rename
-- columns without updating F008 in the same change.
CREATE TABLE IF NOT EXISTS meta.crawl_progress (
    dataset_name  VARCHAR NOT NULL,
    symbol        VARCHAR NOT NULL,
    status        VARCHAR NOT NULL,   -- e.g. 'pending' | 'success' | 'failed' | 'empty'
    retry_count   INTEGER NOT NULL DEFAULT 0,
    last_attempt  TIMESTAMP,
    PRIMARY KEY (dataset_name, symbol)
);

-- core.dim_symbol (F001): symbol master data. delisted_date is nullable
-- and, as of 2026-08-11, will be NULL for every row -- vnstock's unified
-- API does not expose delisted symbols (confirmed via live discovery call,
-- see DECISIONS.md). Do not backfill this with a guess; it stays NULL
-- until an alternative source is decided and logged as its own
-- DECISIONS.md entry.
CREATE TABLE IF NOT EXISTS core.dim_symbol (
    symbol         VARCHAR NOT NULL,
    organ_name     VARCHAR NOT NULL,
    en_organ_name  VARCHAR,
    exchange       VARCHAR,
    industry_code  VARCHAR,
    industry_name  VARCHAR,
    delisted_date  DATE,              -- always NULL for now, see note above
    is_delisted    BOOLEAN,           -- derived from exchange == 'DELISTED' (F001 delisted fix 2026-08-31)
    fetched_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol)
);

-- core.dim_symbol_cafef (F001b): CafeF company directory cross-reference source.
-- Covers OTC equities and unlisted historical tickers not present in vnstock's dim_symbol.
CREATE TABLE IF NOT EXISTS core.dim_symbol_cafef (
    symbol       VARCHAR NOT NULL PRIMARY KEY,
    org_name     VARCHAR NOT NULL,
    exchange     VARCHAR NOT NULL,
    center_id    INTEGER NOT NULL,
    is_vn30      BOOLEAN NOT NULL,
    is_hnx30     BOOLEAN NOT NULL,
    slug_base    VARCHAR NOT NULL,
    source       VARCHAR NOT NULL DEFAULT 'cafef',
    fetched_at   TIMESTAMP NOT NULL,
    raw_json     VARCHAR NOT NULL
);

-- F004d: Sector master & news signal tables
CREATE TABLE IF NOT EXISTS core.dim_sector (
    sector_id        INTEGER NOT NULL PRIMARY KEY,
    sector_name      VARCHAR NOT NULL,
    english_name     VARCHAR,
    gics_sector_code VARCHAR,
    url_slug         VARCHAR,
    keywords_json    VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_symbol_sector (
    symbol           VARCHAR NOT NULL PRIMARY KEY,
    sector_id        INTEGER NOT NULL,
    sector_name      VARCHAR NOT NULL,
    source           VARCHAR NOT NULL,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.sector_news_signal (
    source_url       VARCHAR NOT NULL,
    sector_id        INTEGER NOT NULL,
    sector_name      VARCHAR NOT NULL,
    matched_keyword  VARCHAR NOT NULL,
    match_tier       VARCHAR NOT NULL,
    market_anchor    VARCHAR NOT NULL,
    fetched_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (source_url, sector_id)
);

-- staging/core.market_ohlcv_daily (F002): daily OHLCV per symbol.
-- staging holds raw fetched rows pre-validation; core is validated +
-- promoted, deduped on (symbol, date). Column names for the source fetch
-- are UNCONFIRMED against a live call as of 2026-08-11 -- see DECISIONS.md
-- and src/crawlers/market_ohlcv.py module docstring.
CREATE TABLE IF NOT EXISTS staging.market_ohlcv_daily (
    symbol      VARCHAR NOT NULL,
    date        DATE NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    fetched_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
    symbol      VARCHAR NOT NULL,
    date        DATE NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    fetched_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- staging/core.fundamentals (F005): APPEND-ONLY revision history, one row
-- per (symbol, report_type, period_end, fetched_at) -- NOT deduped down to
-- one row per (symbol, report_type, period_end). Financial statements get
-- restated after initial filing (common after audits); the original
-- three-column PRIMARY KEY meant a restated quarter silently overwrote its
-- original value on the next crawl, which is a real look-ahead-bias leak
-- (see DECISIONS.md 2026-08-16 F009 item 3 entry) -- any backtest querying
-- "what was known as of date X" would see the revised figure even for
-- dates before the revision happened. Fixed 2026-08-16: crawls now INSERT
-- a new revision row only when data_json actually changed for that period
-- (see src/crawlers/fundamentals.py write_statements()); nothing is ever
-- deleted. Point-in-time queries pick a specific vintage explicitly --
-- see get_as_reported()/get_as_of() in fundamentals.py, not a raw SELECT.
--
-- Each report type (income_statement/balance_sheet/cash_flow/ratio) has a
-- very different, wide column set (28-156+ cols per the feature spec), so
-- raw fields are stored as a JSON blob (data_json) rather than exploded
-- into one column per financial-statement line item -- keeps the table
-- schema stable across report types.
-- available_at is an ASSUMED approximation (period_end + a fixed lag),
-- NOT a real disclosure date -- vnstock doesn't expose one. See
-- src/crawlers/fundamentals.py module docstring and DECISIONS.md.
CREATE TABLE IF NOT EXISTS staging.fundamentals ( 
    symbol         VARCHAR NOT NULL,
    report_type    VARCHAR NOT NULL, 
    period_end     DATE NOT NULL,
    available_at   DATE NOT NULL, 
    data_json      VARCHAR NOT NULL,
    fetched_at     TIMESTAMP NOT NULL,
    source         VARCHAR NOT NULL DEFAULT 'vnstock_data'
);

CREATE TABLE IF NOT EXISTS core.fundamentals (
    symbol       VARCHAR NOT NULL,
    report_type  VARCHAR NOT NULL,
    period_end   DATE NOT NULL,
    available_at DATE NOT NULL,
    data_json    VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    source       VARCHAR NOT NULL DEFAULT 'vnstock_data',
    -- Added 2026-09-06: distinguishes vnstock_data's English BS_*/IS_*/CF_*/RT_*
    -- key schema from cafef's raw Vietnamese line-item schema. get_as_reported()
    -- deliberately ignores this for ordering (chronological only, to avoid
    -- reintroducing look-ahead bias); get_as_of() uses it via preferred_source.
    -- DEFAULT 'vnstock_data' matches the real historical backfill (all rows
    -- before 2026-09-06 are vnstock_data) -- new callers must pass their own
    -- source explicitly rather than relying on the default going forward.
    PRIMARY KEY (symbol, report_type, period_end, fetched_at)
);

-- staging/core.corporate_events (F006): event calendar per symbol.
-- Confirmed live 2026-08-13: Company(source='VCI', symbol=symbol).events()
-- is the real per-symbol method (not Reference().events.calendar(), which
-- is market-wide). Actual column names and the closed set of event_type
-- values are UNCONFIRMED as of this schema -- see
-- src/crawlers/corporate_events.py module docstring. detail_json holds
-- the full raw row for later event-embedding use (per F006 spec).
CREATE TABLE IF NOT EXISTS staging.corporate_events (
    symbol       VARCHAR NOT NULL,
    event_id     VARCHAR NOT NULL,
    event_type   VARCHAR NOT NULL,
    event_date   DATE,
    detail_json  VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.corporate_events (
    symbol       VARCHAR NOT NULL,
    event_id     VARCHAR NOT NULL,
    event_type   VARCHAR NOT NULL,
    event_date   DATE,
    detail_json  VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, event_id)
);

-- staging/core.news (F003/F004): shared schema so vnstock News (F003) and
-- cafef.vn (F004) can be unioned without source-specific branching (see
-- DECISIONS.md "Dual news source" entry). available_at = published_at for
-- news (no separate disclosure-lag concept, unlike F005's fundamentals).
-- Column names for the F003 vnstock source are UNCONFIRMED as of this
-- schema -- see src/crawlers/vnstock_news.py module docstring.
CREATE TABLE IF NOT EXISTS staging.news (
    symbol       VARCHAR NOT NULL,
    source       VARCHAR NOT NULL,  -- 'vnstock' (F003) or 'cafef' (F004)
    published_at TIMESTAMP NOT NULL,
    available_at TIMESTAMP NOT NULL,
    headline     VARCHAR NOT NULL,
    body         VARCHAR,
    source_url   VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    duplicate_of VARCHAR            -- nullable; set by etl.news_dedup, added in F009
);

CREATE TABLE IF NOT EXISTS core.news (
    symbol       VARCHAR NOT NULL,
    source       VARCHAR NOT NULL,
    published_at TIMESTAMP NOT NULL,
    available_at TIMESTAMP NOT NULL,
    headline     VARCHAR NOT NULL,
    body         VARCHAR,
    source_url   VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    duplicate_of VARCHAR,           -- nullable; set by etl.news_dedup, added in F009
    PRIMARY KEY (source_url)
);

-- staging/core.realtime_quote_snapshot (F007, SHRUNK SCOPE -- see
-- DECISIONS.md 2026-08-14): F007 was originally scoped as 4 sub-features
-- (valuation history, technical/flow screener, gainer/loser/volume
-- rankings, realtime quote). Only realtime quote has a confirmed-real
-- vnstock method in the free/open-source package (Trading.price_board);
-- the other 3 have no confirmed method and are deferred, not built here.
-- Retention policy: ACCUMULATE one row per (symbol, snapshot_at) --
-- historical, backtestable -- per F007's spec requiring this decision be
-- made explicitly before the feature is passing. A snapshot is a point-
-- in-time price/volume read, not a correction of a prior snapshot, so
-- overwriting would destroy real historical signal.
CREATE TABLE IF NOT EXISTS staging.realtime_quote_snapshot (
    symbol        VARCHAR NOT NULL,
    snapshot_at   TIMESTAMP NOT NULL,
    data_json     VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.realtime_quote_snapshot (
    symbol        VARCHAR NOT NULL,
    snapshot_at   TIMESTAMP NOT NULL,
    data_json     VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, snapshot_at)
);

-- staging/core.price_adjustment_events (F009 item 4): corporate-action
-- price-adjustment multipliers, computed DOWNSTREAM from F006's
-- corporate_events, NOT from vnstock directly -- confirmed live
-- 2026-08-16 that .ohlcv()/Quote.history() expose no adjusted-price or
-- split-adjustment parameter at all. core.market_ohlcv_daily's raw prices
-- are never mutated (raw-payload-preserving principle, F009 item 7);
-- adjustment is applied at query time by joining this table, not baked
-- into F002's output. See src/etl/adjustments.py -- UNVALIDATED against a
-- real published adjusted-price series, see DECISIONS.md, do not trust
-- in a live backtest until that validation happens.
CREATE TABLE IF NOT EXISTS staging.price_adjustment_events (
    symbol           VARCHAR NOT NULL,
    ex_date          DATE NOT NULL,
    adjustment_type  VARCHAR NOT NULL,  -- 'dividend' | 'share_issue'
    multiplier       DOUBLE NOT NULL,
    source_event_id  VARCHAR NOT NULL,
    computed_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.price_adjustment_events (
    symbol           VARCHAR NOT NULL,
    ex_date          DATE NOT NULL,
    adjustment_type  VARCHAR NOT NULL,
    multiplier       DOUBLE NOT NULL,
    source_event_id  VARCHAR NOT NULL,
    computed_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, ex_date, source_event_id)
);

-- staging/core.pit_events (F102): point-in-time news+price+fundamental
-- join. One row per (non-duplicate) news article, joined against
-- adjusted prices (src/etl/adjustments.py) at trading-day offsets and
-- point-in-time-correct fundamentals (fundamentals.get_as_of(), which
-- respects both fetched_at and available_at -- never a future revision
-- leaking into a past query). sentiment is NULL here -- F201 fills it in
-- with the rule-based scorer, this table only proves the join is
-- look-ahead-bias-free. price_t1/t5/t30 are NULL (not fabricated) when
-- fewer than N trading days of future data exist yet for that symbol --
-- see src/pipeline/pit_join.py module docstring.
CREATE TABLE IF NOT EXISTS staging.pit_events (
    symbol             VARCHAR NOT NULL,
    source_url         VARCHAR NOT NULL,
    published_at       TIMESTAMP NOT NULL,
    headline           VARCHAR NOT NULL,
    sentiment          DOUBLE,
    price_at_publish   DOUBLE,
    price_t1           DOUBLE,
    price_t5           DOUBLE,
    price_t30          DOUBLE,
    fundamentals_json  VARCHAR,
    fundamentals_as_of DATE,
    built_at           TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.pit_events (
    symbol             VARCHAR NOT NULL,
    source_url         VARCHAR NOT NULL,
    published_at       TIMESTAMP NOT NULL,
    headline           VARCHAR NOT NULL,
    sentiment          DOUBLE,
    price_at_publish   DOUBLE,
    price_t1           DOUBLE,
    price_t5           DOUBLE,
    price_t30          DOUBLE,
    fundamentals_json  VARCHAR,
    fundamentals_as_of DATE,
    built_at           TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, source_url)
);

-- staging/core.news_resources: Dành cho toàn bộ tin tức vĩ mô, báo chí tài chính,
-- chỉ đạo điều hành chính phủ, thông tư bộ ngành và hiệp hội ngành nghề
-- (phân biệt với core.news chuyên về tin tức gắn với từng mã cổ phiếu cụ thể).
CREATE TABLE IF NOT EXISTS staging.news_resources (
    source        VARCHAR NOT NULL,
    issuing_body  VARCHAR NOT NULL,
    doc_type      VARCHAR,
    doc_number    VARCHAR,
    published_at  TIMESTAMP NOT NULL,
    available_at  TIMESTAMP NOT NULL,
    headline      VARCHAR NOT NULL,
    summary       VARCHAR,
    body          VARCHAR,
    source_url    VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.news_resources (
    source        VARCHAR NOT NULL,
    issuing_body  VARCHAR NOT NULL,
    doc_type      VARCHAR,
    doc_number    VARCHAR,
    published_at  TIMESTAMP NOT NULL,
    available_at  TIMESTAMP NOT NULL,
    headline      VARCHAR NOT NULL,
    summary       VARCHAR,
    body          VARCHAR,
    source_url    VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (source_url)
);

-- staging/core.macro_policy: Duy trì tương thích ngược với các pipeline cũ
CREATE TABLE IF NOT EXISTS staging.macro_policy (
    source        VARCHAR NOT NULL,
    issuing_body  VARCHAR NOT NULL,
    doc_type      VARCHAR,
    doc_number    VARCHAR,
    published_at  TIMESTAMP NOT NULL,
    available_at  TIMESTAMP NOT NULL,
    headline      VARCHAR NOT NULL,
    summary       VARCHAR,
    body          VARCHAR,
    source_url    VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.macro_policy (
    source        VARCHAR NOT NULL,
    issuing_body  VARCHAR NOT NULL,
    doc_type      VARCHAR,
    doc_number    VARCHAR,
    published_at  TIMESTAMP NOT NULL,
    available_at  TIMESTAMP NOT NULL,
    headline      VARCHAR NOT NULL,
    summary       VARCHAR,
    body          VARCHAR,
    source_url    VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (source_url)
);

-- core.market_foreign_flow_daily: Foreign investor trading volume & room (volume-only, B3/B4 compliant)
CREATE TABLE IF NOT EXISTS core.market_foreign_flow_daily (
    symbol        VARCHAR NOT NULL,
    date          DATE NOT NULL,
    buy_volume    DOUBLE,
    sell_volume   DOUBLE,
    net_volume    DOUBLE,
    foreign_room  DOUBLE,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- core.market_index_daily: Benchmark market indices & global macro commodities (VN-INDEX, S&P 500, DXY, Crude Oil, Gold, Coffee, Rice, etc.)
CREATE TABLE IF NOT EXISTS core.market_index_daily (
    index_code    VARCHAR NOT NULL,
    date          DATE NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        BIGINT,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (index_code, date)
);

-- staging/core.market_global_equity_daily: Daily OHLCV for international leading equities (Magnificent 7, Global Tech, etc.)
CREATE TABLE IF NOT EXISTS staging.market_global_equity_daily (
    symbol        VARCHAR NOT NULL,
    date          DATE NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        BIGINT,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.market_global_equity_daily (
    symbol        VARCHAR NOT NULL,
    date          DATE NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        BIGINT,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- =============================================================================
-- QUANTITATIVE ENRICHMENT SCHEMAS (F009a, F009b, F009c)
-- =============================================================================

-- staging/core.proprietary_flow: Daily proprietary trading desk flows per symbol
CREATE TABLE IF NOT EXISTS staging.proprietary_flow (
    symbol        VARCHAR NOT NULL,
    date          DATE NOT NULL,
    buy_vol       DOUBLE,
    buy_val       DOUBLE,
    sell_vol      DOUBLE,
    sell_val      DOUBLE,
    net_vol       DOUBLE,
    net_val       DOUBLE,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.proprietary_flow (
    symbol        VARCHAR NOT NULL,
    date          DATE NOT NULL,
    buy_vol       DOUBLE,
    buy_val       DOUBLE,
    sell_vol      DOUBLE,
    sell_val      DOUBLE,
    net_vol       DOUBLE,
    net_val       DOUBLE,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- staging/core.financial_notes: Deep financial statement notes breakdown (debt, provisions, NPLs)
CREATE TABLE IF NOT EXISTS staging.financial_notes (
    symbol        VARCHAR NOT NULL,
    period        VARCHAR NOT NULL,
    note_id       VARCHAR NOT NULL,
    note_name     VARCHAR,
    item_order    INTEGER,
    item_level    INTEGER,
    unit          VARCHAR,
    value         DOUBLE,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.financial_notes (
    symbol        VARCHAR NOT NULL,
    period        VARCHAR NOT NULL,
    note_id       VARCHAR NOT NULL,
    note_name     VARCHAR,
    item_order    INTEGER,
    item_level    INTEGER,
    unit          VARCHAR,
    value         DOUBLE,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, period, note_id)
);

-- staging/core.macro_rates: Interbank interest rates (ON, 1W, 1M) & Gov bond yield (VN10Y)
CREATE TABLE IF NOT EXISTS staging.macro_rates (
    rate_type     VARCHAR NOT NULL, -- 'INTERBANK' | 'GOV_BOND_YIELD'
    term          VARCHAR NOT NULL, -- 'ON', '1W', '2W', '1M', '3M', '6M', '1Y', '5Y', '10Y'
    date          DATE NOT NULL,
    rate_value    DOUBLE NOT NULL,  -- in %/year
    source        VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.macro_rates (
    rate_type     VARCHAR NOT NULL,
    term          VARCHAR NOT NULL,
    date          DATE NOT NULL,
    rate_value    DOUBLE NOT NULL,
    source        VARCHAR NOT NULL,
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (rate_type, term, date)
);

-- staging/core.macro_economic_series: Long-term macroeconomic indicators (gdp, cpi, fdi, trade, money supply, retail, iip)
CREATE TABLE IF NOT EXISTS staging.macro_economic_series (
    indicator     VARCHAR NOT NULL,
    sub_indicator VARCHAR NOT NULL,
    report_period VARCHAR NOT NULL,
    period_date   DATE,
    numeric_value DOUBLE,
    unit          VARCHAR,
    meta_json     VARCHAR,
    source        VARCHAR NOT NULL DEFAULT 'vnstock',
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.macro_economic_series (
    indicator     VARCHAR NOT NULL,
    sub_indicator VARCHAR NOT NULL,
    report_period VARCHAR NOT NULL,
    period_date   DATE,
    numeric_value DOUBLE,
    unit          VARCHAR,
    meta_json     VARCHAR,
    source        VARCHAR NOT NULL DEFAULT 'vnstock',
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (indicator, sub_indicator, report_period)
);

-- core.company_overview: Detailed corporate profile & governance (VN30 & market leaders)
CREATE TABLE IF NOT EXISTS core.company_overview (
    symbol                 VARCHAR NOT NULL PRIMARY KEY,
    business_model         VARCHAR,
    founded_date           VARCHAR,
    charter_capital        DOUBLE,
    number_of_employees    INTEGER,
    listing_date           VARCHAR,
    par_value              DOUBLE,
    exchange               VARCHAR,
    listing_price          DOUBLE,
    listed_volume          BIGINT,
    ceo_name               VARCHAR,
    ceo_position           VARCHAR,
    inspector_name         VARCHAR,
    inspector_position     VARCHAR,
    establishment_license  VARCHAR,
    business_code          VARCHAR,
    tax_id                 VARCHAR,
    auditor                VARCHAR,
    company_type           VARCHAR,
    address                VARCHAR,
    phone                  VARCHAR,
    fax                    VARCHAR,
    email                  VARCHAR,
    website                VARCHAR,
    branches               VARCHAR,
    history                VARCHAR,
    free_float_percentage  DOUBLE,
    free_float             BIGINT,
    outstanding_shares     BIGINT,
    as_of_date             VARCHAR,
    source                 VARCHAR NOT NULL DEFAULT 'vnstock',
    fetched_at             TIMESTAMP NOT NULL
);

-- core.company_shareholders: Major shareholders distribution (VN30 & market leaders)
CREATE TABLE IF NOT EXISTS core.company_shareholders (
    symbol               VARCHAR NOT NULL,
    shareholder_name     VARCHAR NOT NULL,
    shares_owned         BIGINT,
    ownership_percentage DOUBLE,
    update_date          VARCHAR,
    source               VARCHAR NOT NULL DEFAULT 'vnstock',
    fetched_at           TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, shareholder_name)
);

-- F402: Feedback log for scored predictions vs realized returns and model drift monitoring
CREATE TABLE IF NOT EXISTS meta.prediction_feedback_log (
    prediction_id          VARCHAR PRIMARY KEY,
    created_at             TIMESTAMP NOT NULL,
    symbol                 VARCHAR NOT NULL,
    headline               VARCHAR NOT NULL,
    source                 VARCHAR,
    source_trust_weight    DOUBLE NOT NULL,
    raw_sentiment_score    DOUBLE NOT NULL,
    consistent_alpha_score DOUBLE NOT NULL,
    sentiment_class        VARCHAR NOT NULL,
    p_star_neg             DOUBLE NOT NULL,
    p_star_neu             DOUBLE NOT NULL,
    p_star_pos             DOUBLE NOT NULL,
    violation_score        DOUBLE NOT NULL,
    is_consistent          BOOLEAN NOT NULL,
    is_duplicate           BOOLEAN NOT NULL,
    action_recommendation  VARCHAR NOT NULL,
    regime_safe_to_trade   BOOLEAN NOT NULL,
    matched_shareholder    VARCHAR,
    
    -- Realized Settlement Prices (back-filled by FeedbackReconciler)
    event_date             DATE,
    realized_price_t0      DOUBLE,
    realized_price_t1      DOUBLE,
    realized_price_t5      DOUBLE,
    realized_price_t30     DOUBLE,
    
    -- Realized Returns: (P_t - P_0) / P_0
    return_t1              DOUBLE,
    return_t5              DOUBLE,
    return_t30             DOUBLE,
    
    -- Metric Calibration
    direction_hit_t5       INTEGER,
    brier_score_t5         DOUBLE,
    
    is_backfilled          BOOLEAN NOT NULL DEFAULT FALSE,
    backfilled_at          TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta.model_drift_telemetry (
    run_id                         VARCHAR PRIMARY KEY,
    audit_timestamp                TIMESTAMP NOT NULL,
    window_size                    INTEGER NOT NULL,
    rolling_directional_accuracy_t5 DOUBLE,
    rolling_brier_score_t5         DOUBLE,
    rolling_spearman_ic_t5         DOUBLE,
    rolling_spearman_ic_t30        DOUBLE,
    total_evaluated                INTEGER NOT NULL,
    total_pending                  INTEGER NOT NULL,
    circuit_breaker_status         VARCHAR NOT NULL, -- 'NORMAL' | 'WARNING' | 'SYSTEM_DEGRADED_HALT'
    alert_message                  VARCHAR
);

-- F403: Continuous Training & Shadow Model Promotion History
CREATE TABLE IF NOT EXISTS meta.continuous_training_history (
    training_run_id        VARCHAR PRIMARY KEY,
    triggered_at           TIMESTAMP NOT NULL,
    trigger_reason         VARCHAR NOT NULL, -- 'DRIFT_ALERT' | 'SAMPLE_VOLUME' | 'MANUAL'
    samples_count          INTEGER NOT NULL,
    epochs                 INTEGER NOT NULL,
    train_loss_start       DOUBLE,
    train_loss_final       DOUBLE,
    prev_val_accuracy      DOUBLE,
    shadow_val_accuracy    DOUBLE,
    prev_val_brier         DOUBLE,
    shadow_val_brier       DOUBLE,
    is_promoted            BOOLEAN NOT NULL,
    checkpoint_path        VARCHAR,
    metadata_json          VARCHAR
);

