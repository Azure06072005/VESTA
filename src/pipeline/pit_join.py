"""F102: Point-in-time news+price+fundamental join.

Joins F003/F004 (news, deduped via F009's duplicate_of flag), F002
(OHLCV, adjusted via F009's src/etl/adjustments.py), and F005
(fundamentals, queried via F009's get_as_of() -- NOT get_as_reported(),
see below) into one events table. This is the single most important
look-ahead-bias gate in the repo: no feature may be visible before its
real-world disclosure/publish time.

FUNDAMENTALS CHOICE: get_as_of(symbol, report_type, published_at) is used,
not get_as_reported(). get_as_of() already respects both fetched_at <=
as_of_date and available_at <= as_of_date, so it inherently returns
whatever was genuinely knowable at published_at -- including a legitimate
earlier restatement, if that restatement had itself already been
disclosed by then. get_as_reported() answers a narrower question ("what
was the very first number ever reported for this specific period,
regardless of date") -- a different analytical tool, not what "latest
available fundamentals as of published_at" means. Confirmed correct by
construction: if a restatement's fetched_at is after published_at,
get_as_of() cannot see it yet, so no look-ahead is possible either way.

PRICE ADJUSTMENT: joins against adj_close (src/etl/adjustments.py), not
raw close -- a corporate action inside the t+1..t+30 window must not
masquerade as a price return. adj_close is itself UNVALIDATED against a
real published adjusted-price series (see adjustments.py/DECISIONS.md) --
that caveat propagates into this table's price_t* columns.

NEWS DEDUP: only rows with duplicate_of IS NULL are joined -- a
cross-source duplicate (F009 item 5) must not become two independent
events for the same real-world news.

TRADING-DAY OFFSETS: t+1/t+5/t+30 are trading-day offsets, not calendar-
day offsets, derived from each symbol's OWN set of crawled OHLCV dates
(not a generic VN holiday calendar) -- this means offset correctness is
bounded by how much OHLCV history has actually been crawled for that
symbol. A horizon with insufficient future trading days is left NULL,
never fabricated.

MARKET-CLOSE-TIME ASSUMPTION (flagged, not hidden): OHLCV is daily bars,
so "price at publish" needs a same-day-vs-next-day rule for intraday news
timestamps. MARKET_CLOSE_TIME (15:00, HOSE's real closing time) is used:
news published before close on a trading day anchors to that day's
close; published at/after close (or on a non-trading day) anchors to the
next available trading day. This is a reasonable convention, not
independently verified against how the source APIs actually timestamp
articles relative to market sessions.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl import adjustments  # noqa: E402
from crawlers import fundamentals  # noqa: E402

# ASSUMED, see module docstring -- HOSE's real closing time.
MARKET_CLOSE_TIME = dt.time(15, 0)

HORIZONS = {"price_t1": 1, "price_t5": 5, "price_t30": 30}

PIT_EVENT_COLUMNS = [
    "symbol",
    "source_url",
    "published_at",
    "headline",
    "sentiment",
    "price_at_publish",
    "price_t1",
    "price_t5",
    "price_t30",
    "fundamentals_json",
    "fundamentals_as_of",
    "built_at",
]


def get_trading_calendar(con: duckdb.DuckDBPyConnection, symbol: str) -> list[dt.date]:
    """Sorted list of dates this symbol actually has an OHLCV row for --
    the real, symbol-specific trading calendar (naturally reflects VN
    market holidays, since a non-trading day simply has no crawled row).
    """
    rows = con.execute(
        "SELECT DISTINCT date FROM core.market_ohlcv_daily WHERE symbol = ? ORDER BY date", [symbol]
    ).fetchall()
    return [r[0] for r in rows]


def get_adjusted_price_series(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    """OHLCV rows for this symbol with adj_close computed via F009's
    adjustments.apply_adjustment(), indexed by date.
    """
    ohlcv = con.execute(
        "SELECT date, open, high, low, close, volume FROM core.market_ohlcv_daily WHERE symbol = ? ORDER BY date",
        [symbol],
    ).df()
    if ohlcv.empty:
        return ohlcv

    adj_events = con.execute(
        "SELECT ex_date, multiplier FROM core.price_adjustment_events WHERE symbol = ?", [symbol]
    ).df()

    return adjustments.apply_adjustment(ohlcv, adj_events)


def effective_trading_date(published_at: dt.datetime, trading_days: list[dt.date]) -> dt.date | None:
    """Maps a news timestamp to the trading day its price impact should
    anchor to (see MARKET_CLOSE_TIME assumption in module docstring).
    Returns None if there is no trading day on or after the computed
    anchor (e.g. the symbol has no OHLCV data covering this period at
    all) -- callers must handle this as "can't compute a price join",
    not silently pick an arbitrary date.
    """
    if not trading_days:
        return None

    anchor_date = published_at.date()
    if published_at.time() >= MARKET_CLOSE_TIME:
        anchor_date = anchor_date + dt.timedelta(days=1)

    idx = bisect.bisect_left(trading_days, anchor_date)
    if idx >= len(trading_days):
        return None  # anchor is after every crawled trading day -- can't anchor yet
    return trading_days[idx]


def price_at_horizon(
    trading_days: list[dt.date], price_by_date: dict[dt.date, float], base_date: dt.date, n_days: int
) -> float | None:
    """adj_close on the trading day n_days after base_date (n_days=0 is
    base_date itself). Returns None if there aren't enough future trading
    days crawled yet -- never fabricated, never falls back to a nearby
    date silently.
    """
    idx = bisect.bisect_left(trading_days, base_date)
    if idx >= len(trading_days) or trading_days[idx] != base_date:
        return None
    target_idx = idx + n_days
    if target_idx >= len(trading_days):
        return None
    target_date = trading_days[target_idx]
    return price_by_date.get(target_date)


def build_events_for_symbol(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    """Pure-ish transform (reads via con, doesn't fetch externally): joins
    this symbol's non-duplicate news against adjusted prices and
    point-in-time fundamentals. Returns an empty DataFrame if there's no
    news, no OHLCV, or neither -- callers should treat that as "nothing to
    write yet", not an error.
    """
    news_df = con.execute(
        "SELECT source_url, published_at, headline FROM core.news "
        "WHERE symbol = ? AND duplicate_of IS NULL ORDER BY published_at",
        [symbol],
    ).df()
    if news_df.empty:
        return pd.DataFrame(columns=PIT_EVENT_COLUMNS)

    price_series = get_adjusted_price_series(con, symbol)
    trading_days = get_trading_calendar(con, symbol)
    # Normalize to plain date objects -- get_trading_calendar() returns
    # native date (via fetchall()), price_series['date'] comes back as
    # pandas Timestamp (via .df()); without this, dict lookups below
    # silently miss on type mismatch even when the calendar dates "look"
    # identical.
    price_by_date = (
        {pd.Timestamp(d).date(): c for d, c in zip(price_series["date"], price_series["adj_close"])}
        if not price_series.empty
        else {}
    )

    built_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows = []

    for _, news_row in news_df.iterrows():
        published_at = pd.Timestamp(news_row["published_at"]).to_pydatetime()
        base_date = effective_trading_date(published_at, trading_days)

        price_at_publish = None
        price_t1 = price_t5 = price_t30 = None
        if base_date is not None:
            price_at_publish = price_at_horizon(trading_days, price_by_date, base_date, 0)
            price_t1 = price_at_horizon(trading_days, price_by_date, base_date, HORIZONS["price_t1"])
            price_t5 = price_at_horizon(trading_days, price_by_date, base_date, HORIZONS["price_t5"])
            price_t30 = price_at_horizon(trading_days, price_by_date, base_date, HORIZONS["price_t30"])

        merged_fundamentals: dict[str, object] = {}
        fundamentals_as_of = None
        as_of_query_date = published_at.date()
        for report_type in fundamentals.REPORT_TYPES:
            vintage_df = fundamentals.get_as_of(con, symbol, report_type, as_of_query_date)
            if vintage_df.empty:
                continue
            latest_row = vintage_df.sort_values("period_end").iloc[-1]
            merged_fundamentals[report_type] = json.loads(latest_row["data_json"])
            fundamentals_as_of = latest_row["period_end"]

        fundamentals_json = json.dumps(merged_fundamentals, default=str, ensure_ascii=False) if merged_fundamentals else None

        rows.append(
            {
                "symbol": symbol,
                "source_url": news_row["source_url"],
                "published_at": published_at,
                "headline": news_row["headline"],
                "sentiment": None,
                "price_at_publish": price_at_publish,
                "price_t1": price_t1,
                "price_t5": price_t5,
                "price_t30": price_t30,
                "fundamentals_json": fundamentals_json,
                "fundamentals_as_of": fundamentals_as_of,
                "built_at": built_at,
            }
        )

    return pd.DataFrame(rows, columns=PIT_EVENT_COLUMNS)


def write_events(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write, idempotent on (symbol, source_url) -- re-running
    for a symbol replaces its rows (a rebuild, not an accumulation --
    unlike F007's snapshots, an event's derived fields like price_t30 can
    legitimately change as more OHLCV history is crawled, so this is
    correctly a recompute-and-replace, not append-only history).
    """
    if df.empty:
        return 0

    missing = set(PIT_EVENT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Events DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    symbols = df["symbol"].unique().tolist()

    con.execute("DELETE FROM staging.pit_events WHERE symbol IN ?", [symbols])
    con.register("events_df", df[PIT_EVENT_COLUMNS])
    con.execute("INSERT INTO staging.pit_events SELECT * FROM events_df")

    con.execute("DELETE FROM core.pit_events WHERE symbol IN ?", [symbols])
    con.execute("INSERT INTO core.pit_events SELECT * FROM events_df")
    con.unregister("events_df")

    return len(df)


def run(symbol: str) -> int:
    """Entry point: build + write the events table for one symbol."""
    con = db.bootstrap_schema()
    events = build_events_for_symbol(con, symbol)
    return write_events(events, con)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F102: build the point-in-time events table for one symbol")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F102 pit_join: wrote {n} rows for {args.symbol} to core.pit_events")