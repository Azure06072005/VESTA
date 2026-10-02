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

-- meta.strategy_trial_log (F202/F202b): Immutable ledger of all backtested strategy
-- trial configurations, required for Deflated Sharpe Ratio (DSR) and PBO calculation.
CREATE TABLE IF NOT EXISTS meta.strategy_trial_log (
    trial_id           VARCHAR PRIMARY KEY,
    strategy_name      VARCHAR NOT NULL,
    trial_timestamp    TIMESTAMP NOT NULL,
    horizon_days       INTEGER NOT NULL,
    sentiment_source   VARCHAR NOT NULL,
    threshold_param    DOUBLE,
    universe           VARCHAR NOT NULL,
    sample_size_n      INTEGER NOT NULL,
    observed_sr        DOUBLE NOT NULL,
    annualized_sr      DOUBLE,
    skewness           DOUBLE,
    kurtosis           DOUBLE,
    p_value_naive      DOUBLE,
    dsr_score          DOUBLE,
    config_json        VARCHAR,
    git_commit_hash    VARCHAR
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
    symbol         VARCHAR NOT NULL PRIMARY KEY,
    org_name       VARCHAR NOT NULL,
    exchange       VARCHAR NOT NULL,
    center_id      INTEGER NOT NULL,
    is_vn30        BOOLEAN NOT NULL,
    is_hnx30       BOOLEAN NOT NULL,
    slug_base      VARCHAR NOT NULL,
    source         VARCHAR NOT NULL DEFAULT 'cafef',
    fetched_at     TIMESTAMP NOT NULL,
    raw_json       VARCHAR NOT NULL,
    tradeable_flag BOOLEAN NOT NULL DEFAULT FALSE,
    subuniverse    VARCHAR NOT NULL DEFAULT 'OTC'
);

ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS tradeable_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS subuniverse VARCHAR DEFAULT 'OTC';

-- core.v_symbol_universe (F001b Recommendation):
-- Unified symbol universe with explicit subuniverse tagging.
-- Liquid quantitative models MUST filter `WHERE tradeable_flag = TRUE`
-- to exclude the 750 illiquid OTC tickers and prevent execution noise.
CREATE OR REPLACE VIEW core.v_symbol_universe AS
SELECT 
    symbol, 
    organ_name as org_name, 
    exchange, 
    is_delisted,
    TRUE as tradeable_flag, 
    'LISTED' as subuniverse,
    'vnstock' as source,
    fetched_at
FROM core.dim_symbol
UNION ALL
SELECT 
    symbol, 
    org_name, 
    exchange, 
    TRUE as is_delisted,
    tradeable_flag, 
    subuniverse,
    source,
    fetched_at
FROM core.dim_symbol_cafef;

-- F001 Recommendation: Static 4-tier ICB industry hierarchy mapping
CREATE TABLE IF NOT EXISTS core.dim_icb_hierarchy (
    icb_code            VARCHAR NOT NULL PRIMARY KEY,
    level               INTEGER NOT NULL,
    icb_name_vi         VARCHAR NOT NULL,
    icb_name_en         VARCHAR NOT NULL,
    parent_code         VARCHAR,
    industry_code       VARCHAR NOT NULL,
    industry_name_vi    VARCHAR NOT NULL,
    industry_name_en    VARCHAR NOT NULL,
    supersector_code    VARCHAR,
    supersector_name_vi VARCHAR,
    supersector_name_en VARCHAR,
    sector_code         VARCHAR,
    sector_name_vi      VARCHAR,
    sector_name_en      VARCHAR,
    subsector_code      VARCHAR,
    subsector_name_vi   VARCHAR,
    subsector_name_en   VARCHAR,
    updated_at          TIMESTAMP NOT NULL
);

-- F001 Recommendation: Continuous symbol exchange migration history
CREATE TABLE IF NOT EXISTS core.symbol_exchange_history (
    symbol          VARCHAR NOT NULL,
    exchange        VARCHAR NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE,
    is_current      BOOLEAN NOT NULL,
    listing_price   DOUBLE,
    event_note      VARCHAR,
    source          VARCHAR NOT NULL DEFAULT 'HOSE/HNX/CompanyOverview',
    created_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, exchange, start_date)
);

-- F001c: Index constituents & group rooms mapping (VN30, VN100, VNMID, VNSML, VNSI, VNX50, HNX30, VNDIAMOND, VNFINLEAD, VNFINSELECT, HOSE Sector Indices)
CREATE TABLE IF NOT EXISTS core.dim_index_metadata (
    index_code          VARCHAR NOT NULL PRIMARY KEY,
    index_name          VARCHAR NOT NULL,
    exchange            VARCHAR NOT NULL,    -- 'HOSE' | 'HNX' | 'VNX'
    category            VARCHAR NOT NULL,    -- 'BENCHMARK' | 'MARKET_CAP' | 'ESG' | 'THEMATIC' | 'SECTOR'
    description         VARCHAR,
    rebalance_cycle     VARCHAR,            -- 'QUARTERLY' | 'SEMI_ANNUALLY' | 'ANNUALLY'
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.dim_index_constituents (
    index_code          VARCHAR NOT NULL,
    symbol              VARCHAR NOT NULL,
    weight              DOUBLE,              -- index weighting % if available
    rank                INTEGER,             -- constituent rank by market cap/liquidity
    effective_date      DATE NOT NULL,       -- effective rebalancing date
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    source              VARCHAR NOT NULL DEFAULT 'SSI_IBOARD', -- 'SSI_IBOARD' | 'KBS' | 'HOSE'
    fetched_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (index_code, symbol, effective_date)
);

CREATE OR REPLACE VIEW core.v_active_index_constituents AS
SELECT 
    c.index_code,
    m.index_name,
    m.category,
    m.exchange,
    c.symbol,
    s.organ_name,
    c.weight,
    c.rank,
    c.effective_date,
    c.source
FROM core.dim_index_constituents c
JOIN core.dim_index_metadata m ON c.index_code = m.index_code
LEFT JOIN core.dim_symbol s ON c.symbol = s.symbol
WHERE c.is_current = TRUE;

-- F002: Market OHLCV daily bars (raw payload preserving)
CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
    symbol      VARCHAR NOT NULL,
    date        DATE NOT NULL,
    open        DOUBLE NOT NULL,
    high        DOUBLE NOT NULL,
    low         DOUBLE NOT NULL,
    close       DOUBLE NOT NULL,
    volume      BIGINT NOT NULL,
    fetched_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- F002 Recommendation: Corporate Actions & Ex-Dividend Price Adjustment Factors
CREATE TABLE IF NOT EXISTS core.price_adjustment_events (
    symbol                       VARCHAR NOT NULL,
    ex_date                      DATE NOT NULL,
    adjustment_type              VARCHAR NOT NULL,     -- 'CASH_DIVIDEND' | 'STOCK_DIVIDEND' | 'COMBINED'
    cash_dividend                DOUBLE,               -- D (nghìn VNĐ/cổ phiếu)
    stock_dividend_ratio         DOUBLE,               -- alpha (ví dụ 0.15 = 15%)
    cum_close_price              DOUBLE,               -- P_close (giá đóng cửa ngày T-1)
    ex_reference_price           DOUBLE,               -- P_ex (giá tham chiếu ngày GDKHQ)
    multiplier                   DOUBLE NOT NULL,      -- f = P_ex / P_close (hệ số điều chỉnh bước đơn)
    cumulative_adjustment_factor DOUBLE NOT NULL,      -- CAF (chuỗi nhân dồn)
    source_event_ids             VARCHAR,
    computed_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, ex_date)
);

-- F002 Recommendation: Continuous Timeline of Cumulative Adjustment Factors (CAF)
CREATE TABLE IF NOT EXISTS core.symbol_caf_timeline (
    symbol      VARCHAR NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    caf         DOUBLE NOT NULL,
    PRIMARY KEY (symbol, start_date)
);

-- F002 Recommendation: Dual-Mode Market OHLCV Analytical View (Raw & Adjusted Prices)
CREATE OR REPLACE VIEW core.v_market_ohlcv_dual AS
SELECT 
    m.symbol,
    m.date,
    -- 1. Giá điều chỉnh (Vendor-Adjusted Prices dùng cho tính tỷ suất sinh lời thực tế)
    m.open as adj_open,
    m.high as adj_high,
    m.low as adj_low,
    m.close as adj_close,
    m.volume as adj_volume,
    -- 2. Hệ số nhân dồn tích lũy (Cumulative Adjustment Factor)
    COALESCE(c.caf, 1.0) as caf,
    -- 3. Giá thô nguyên bản (Raw Unadjusted Prices dùng cho đo bước giá & biên độ trần/sàn)
    ROUND(m.open / COALESCE(c.caf, 1.0), 2) as raw_open,
    ROUND(m.high / COALESCE(c.caf, 1.0), 2) as raw_high,
    ROUND(m.low / COALESCE(c.caf, 1.0), 2) as raw_low,
    ROUND(m.close / COALESCE(c.caf, 1.0), 2) as raw_close,
    ROUND(m.volume * COALESCE(c.caf, 1.0), 0) as raw_volume,
    m.fetched_at
FROM core.market_ohlcv_daily m
LEFT JOIN core.symbol_caf_timeline c
  ON m.symbol = c.symbol 
 AND m.date >= c.start_date 
 AND m.date < c.end_date;

-- F002b: High-Frequency 1-Minute Intraday Bar Table & Meta Progress
CREATE TABLE IF NOT EXISTS core.market_ohlcv_1m (
    symbol      VARCHAR NOT NULL,
    time        TIMESTAMP NOT NULL,
    open        DOUBLE NOT NULL,
    high        DOUBLE NOT NULL,
    low         DOUBLE NOT NULL,
    close       DOUBLE NOT NULL,
    volume      BIGINT NOT NULL,
    fetched_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, time)
);

CREATE TABLE IF NOT EXISTS meta.crawl_progress_1m (
    symbol          VARCHAR PRIMARY KEY,
    earliest_time   TIMESTAMP,
    latest_time     TIMESTAMP,
    total_bars      INTEGER NOT NULL DEFAULT 0,
    trading_days    INTEGER NOT NULL DEFAULT 0,
    is_complete_3y  BOOLEAN DEFAULT FALSE,
    last_status     VARCHAR,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- F002b: Dual-Mode 1-Minute OHLCV Analytical View (Raw & Adjusted Intraday Prices)
CREATE OR REPLACE VIEW core.v_market_ohlcv_1m_dual AS
SELECT 
    m.symbol,
    m.time,
    -- 1. Giá điều chỉnh (Vendor-Adjusted Prices dùng cho tính tỷ suất sinh lời thực tế)
    m.open as adj_open,
    m.high as adj_high,
    m.low as adj_low,
    m.close as adj_close,
    m.volume as adj_volume,
    -- 2. Hệ số nhân dồn tích lũy (Cumulative Adjustment Factor)
    COALESCE(c.caf, 1.0) as caf,
    -- 3. Giá thô nguyên bản (Raw Unadjusted Prices dùng cho đo bước giá & biên độ trần/sàn)
    ROUND(m.open / COALESCE(c.caf, 1.0), 2) as raw_open,
    ROUND(m.high / COALESCE(c.caf, 1.0), 2) as raw_high,
    ROUND(m.low / COALESCE(c.caf, 1.0), 2) as raw_low,
    ROUND(m.close / COALESCE(c.caf, 1.0), 2) as raw_close,
    ROUND(m.volume * COALESCE(c.caf, 1.0), 0) as raw_volume,
    m.fetched_at
FROM core.market_ohlcv_1m m
LEFT JOIN core.symbol_caf_timeline c
  ON m.symbol = c.symbol 
 AND CAST(m.time AS DATE) >= c.start_date 
 AND CAST(m.time AS DATE) < c.end_date;

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
-- staging/core.news (F003/F004/F106): Hợp nhất toàn diện tin tức doanh nghiệp,
-- tin vĩ mô, báo chí tài chính và công bố thông tin theo chuẩn 14 cột
CREATE TABLE IF NOT EXISTS staging.news (
    source_url   VARCHAR,
    news_type    VARCHAR DEFAULT 'STOCK_NEWS',
    symbol       VARCHAR,
    source       VARCHAR,
    issuing_body VARCHAR,
    doc_type     VARCHAR,
    doc_number   VARCHAR,
    published_at TIMESTAMP,
    available_at TIMESTAMP,
    headline     VARCHAR,
    summary      VARCHAR,
    body         VARCHAR,
    duplicate_of VARCHAR,
    fetched_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.news (
    source_url   VARCHAR NOT NULL,
    news_type    VARCHAR NOT NULL DEFAULT 'STOCK_NEWS',
    symbol       VARCHAR,
    source       VARCHAR NOT NULL,
    issuing_body VARCHAR,
    doc_type     VARCHAR,
    doc_number   VARCHAR,
    published_at TIMESTAMP NOT NULL,
    available_at TIMESTAMP NOT NULL,
    headline     VARCHAR NOT NULL,
    summary      VARCHAR,
    body         VARCHAR,
    duplicate_of VARCHAR,
    fetched_at   TIMESTAMP NOT NULL,
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
CREATE OR REPLACE VIEW staging.news_resources AS
SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
FROM staging.news
WHERE symbol IS NULL;

CREATE OR REPLACE VIEW core.news_resources AS
SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
FROM core.news
WHERE symbol IS NULL;

-- staging/core.macro_policy: Duy trì tương thích ngược với các pipeline cũ
CREATE OR REPLACE VIEW staging.macro_policy AS
SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
FROM staging.news
WHERE news_type = 'MACRO_POLICY' OR (symbol IS NULL AND source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'thoibaonganhang'));

CREATE OR REPLACE VIEW core.macro_policy AS
SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
FROM core.news
WHERE news_type = 'MACRO_POLICY' OR (symbol IS NULL AND source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'thoibaonganhang'));

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

-- ============================================================================
-- F007b: Market Insights, Screener, Index Valuation & Market Breadth Tables
-- ============================================================================

-- staging/core.market_screener_snapshot: Multi-factor quantitative screening snapshots
CREATE TABLE IF NOT EXISTS staging.market_screener_snapshot (
    symbol                   VARCHAR NOT NULL,
    snapshot_date            DATE NOT NULL,
    exchange                 VARCHAR,
    price                    DOUBLE,
    reference_price          DOUBLE,
    ceiling_price            DOUBLE,
    floor_price              DOUBLE,
    price_change_percent     DOUBLE,
    market_cap               DOUBLE,
    accumulated_value        DOUBLE,
    accumulated_volume       DOUBLE,
    stock_strength           DOUBLE,
    data_json                VARCHAR,
    source                   VARCHAR NOT NULL DEFAULT 'VIETCAP_IQ_DIRECT',
    fetched_at               TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.market_screener_snapshot (
    symbol                   VARCHAR NOT NULL,
    snapshot_date            DATE NOT NULL,
    exchange                 VARCHAR,
    price                    DOUBLE,
    reference_price          DOUBLE,
    ceiling_price            DOUBLE,
    floor_price              DOUBLE,
    price_change_percent     DOUBLE,
    market_cap               DOUBLE,
    accumulated_value        DOUBLE,
    accumulated_volume       DOUBLE,
    stock_strength           DOUBLE,
    data_json                VARCHAR,
    source                   VARCHAR NOT NULL DEFAULT 'VIETCAP_IQ_DIRECT',
    fetched_at               TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, snapshot_date)
);

-- staging/core.index_valuation_series: Historical daily valuation ratios (P/E, P/B) for indices
CREATE TABLE IF NOT EXISTS staging.index_valuation_series (
    index_code    VARCHAR NOT NULL,
    ratio_code    VARCHAR NOT NULL,
    report_date   DATE NOT NULL,
    ratio_value   DOUBLE NOT NULL,
    source        VARCHAR NOT NULL DEFAULT 'VNDIRECT_FINFO_DIRECT',
    fetched_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.index_valuation_series (
    index_code    VARCHAR NOT NULL,
    ratio_code    VARCHAR NOT NULL,
    report_date   DATE NOT NULL,
    ratio_value   DOUBLE NOT NULL,
    source        VARCHAR NOT NULL DEFAULT 'VNDIRECT_FINFO_DIRECT',
    fetched_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (index_code, ratio_code, report_date)
);

-- staging/core.market_breadth_series: Historical market breadth time series
CREATE TABLE IF NOT EXISTS staging.market_breadth_series (
    exchange               VARCHAR NOT NULL,
    trade_date             DATE NOT NULL,
    pe                     DOUBLE,
    pb                     DOUBLE,
    above_ma20_pct         DOUBLE,
    above_ma50_pct         DOUBLE,
    above_ma200_pct        DOUBLE,
    avg_20d_above_ma50_pct DOUBLE,
    position_line          DOUBLE,
    close_index            DOUBLE,
    source                 VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
    fetched_at             TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.market_breadth_series (
    exchange               VARCHAR NOT NULL,
    trade_date             DATE NOT NULL,
    pe                     DOUBLE,
    pb                     DOUBLE,
    above_ma20_pct         DOUBLE,
    above_ma50_pct         DOUBLE,
    above_ma200_pct        DOUBLE,
    avg_20d_above_ma50_pct DOUBLE,
    position_line          DOUBLE,
    close_index            DOUBLE,
    source                 VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
    fetched_at             TIMESTAMP NOT NULL,
    PRIMARY KEY (exchange, trade_date)
);

-- staging/core.market_sentiment_snapshot: Fear & Greed and market sentiment snapshots
CREATE TABLE IF NOT EXISTS staging.market_sentiment_snapshot (
    exchange           VARCHAR NOT NULL,
    snapshot_date      DATE NOT NULL,
    fear_greed_score   DOUBLE,
    advances           INTEGER,
    declines           INTEGER,
    no_change          INTEGER,
    mfi                DOUBLE,
    rsi                DOUBLE,
    index_change       DOUBLE,
    volume_change      DOUBLE,
    raw_json           VARCHAR,
    source             VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
    fetched_at         TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.market_sentiment_snapshot (
    exchange           VARCHAR NOT NULL,
    snapshot_date      DATE NOT NULL,
    fear_greed_score   DOUBLE,
    advances           INTEGER,
    declines           INTEGER,
    no_change          INTEGER,
    mfi                DOUBLE,
    rsi                DOUBLE,
    index_change       DOUBLE,
    volume_change      DOUBLE,
    raw_json           VARCHAR,
    source             VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
    fetched_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (exchange, snapshot_date)
);


