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
    fetched_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol)
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
    fetched_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.fundamentals (
    symbol       VARCHAR NOT NULL,
    report_type  VARCHAR NOT NULL,
    period_end   DATE NOT NULL,
    available_at DATE NOT NULL,
    data_json    VARCHAR NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
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
    fetched_at   TIMESTAMP NOT NULL
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