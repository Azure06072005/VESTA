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

-- staging/core.fundamentals (F005): one row per (symbol, report_type,
-- period_end). Each report type (income_statement/balance_sheet/
-- cash_flow/ratio) has a very different, wide column set (28-156+ cols
-- per the feature spec), so raw fields are stored as a JSON blob
-- (data_json) rather than exploded into one column per financial-statement
-- line item -- keeps the table schema stable across report types.
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
    PRIMARY KEY (symbol, report_type, period_end)
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