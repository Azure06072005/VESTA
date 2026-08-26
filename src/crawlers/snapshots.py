"""F007 (SCOPE SHRUNK 2026-08-14, see DECISIONS.md): realtime quote
snapshot crawler only.

Original spec called for 4 sub-features: market valuation history,
technical/flow screener, gainer/loser/volume rankings, realtime quote.
Confirmed live 2026-08-13/14 against the installed COMMUNITY package
(`vnstock==4.0.5`):
- `Insights` class does not exist anywhere in that package (confirmed
  absent -- an earlier report's `Insights.ranking.gainer()` claim was
  hallucinated, see DECISIONS.md 2026-08-11 entry).
- A full survey of every top-level vnstock class (Trading, Retail, Fund,
  Quote, Market, Broker, Reference) found no confirmed method for
  valuation history, a technical/flow screener, or gainer/loser/volume
  rankings.
- `Trading(source='VCI').price_board(symbols_list=[...])` IS a real,
  confirmed-callable method and plausibly covers "realtime quote" -- this
  is the one piece of F007 this module implements. The other 3
  sub-features are deferred, not built here -- see DECISIONS.md.

UPDATE 2026-08-26 -- POSSIBLY SUPERSEDED, NOT YET ACTED ON: DECISIONS.md's
2026-08-26 entry reports that a separate PROPRIETARY package
(`vnstock_data==3.2.7`, a paid Sponsor-tier extension, distinct from the
community `vnstock` surveyed above) does provide an `Insights` class with
`ranking`/`screener`/`sentiment`/`flow` submodules, and that `gainer()`,
`breadth()`, and `filter()` were called live and returned data. That
finding does NOT yet meet this project's own evidence standard (a pasted
raw stdout dump -- shapes, column names, sample rows -- the way every
other confirmed schema in this repo was established, e.g. F002's OHLCV
columns or this file's own 82-column MultiIndex discovery above). Until
that raw output is pasted and reviewed, F007's SCOPE AND STATE ARE
UNCHANGED -- this module still implements realtime-quote-only, and no
code here has been written against `Insights`/`Analytics`/`Macro`. Do not
assume the 4-sub-feature original spec is restorable until that
verification gap is closed; see the tracking entry for this at F007b in
feature_list.json (state: active, not started) and the 2026-08-26
DECISIONS.md addendum.

CONFIRMED SCHEMA (2026-08-14, real discovery output pasted by Tran Dieu,
replaces the flat-DataFrame first guess): `price_board()` returns an
82-column MultiIndex DataFrame across 3 top-level categories: 'listing'
(symbol, ceiling, floor, ref_price, exchange, trading_status, ...),
'bid_ask' (bid_1..3_price/volume, ask_1..3_price/volume, bid_count,
ask_count, ...), 'match' (match_price, match_vol, accumulated_volume,
foreign_buy_volume, foreign_sell_volume, highest, lowest, ATO/ATC price
fields, ...). The symbol column lives at ('listing', 'symbol').
normalize_snapshot() flattens the MultiIndex to 'category_field' string
keys (e.g. 'listing_symbol', 'bid_ask_bid_1_price') before serializing
each row to JSON, so no data is lost and no field name needs to be
individually mapped -- the full 82-column row is preserved.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

# CONFIRMED live 2026-08-14: the real symbol column after flattening the
# MultiIndex is 'listing_symbol'. Aliases kept for robustness against a
# flat (non-MultiIndex) response, e.g. in offline/synthetic test data.
SYMBOL_COLUMN_ALIASES = ["listing_symbol", "symbol", "ticker"]

SNAPSHOT_COLUMNS = ["symbol", "snapshot_at", "data_json", "fetched_at"]


def _authenticate() -> None:
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    if hasattr(vs, "change_api_key"):
        vs.change_api_key(api_key)


def fetch_raw(symbols: list[str]) -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns whatever vnstock's price_board() gives back, untouched
    (including its MultiIndex columns) -- flattening happens in
    normalize_snapshot() so that logic stays testable without network
    access.
    """
    _authenticate()
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    trading = vs.Trading(source="VCI")
    result: pd.DataFrame = trading.price_board(symbols_list=symbols)
    return result


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Confirmed live 2026-08-14: price_board() returns a MultiIndex
    (category, field) column structure. Flatten to 'category_field'
    string keys. A no-op if columns are already flat (e.g. synthetic test
    data), so this function works for both shapes.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = pd.Index(["_".join(str(part) for part in col) for col in df.columns])
    return df


def normalize_snapshot(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: one row per symbol in the fetched price board, full
    (flattened) raw row preserved as JSON. Requires a symbol column
    (after flattening) to key rows by; fails loudly if none of
    SYMBOL_COLUMN_ALIASES is present rather than guessing. No network
    access -- fully unit-testable with synthetic DataFrames, MultiIndex
    or flat.
    """
    if raw_df.empty:
        raise EmptyResultError(
            "fetch_raw returned an empty DataFrame -- F008-compatible: "
            "recorded as genuine emptiness via record_empty(), NOT "
            "retried. (Could also indicate all requested symbols were "
            "invalid; if this fires unexpectedly, verify the symbol list "
            "first before assuming it's a transient API issue.)"
        )

    flat_df = _flatten_columns(raw_df)

    symbol_col = next((c for c in SYMBOL_COLUMN_ALIASES if c in flat_df.columns), None)
    if symbol_col is None:
        raise ValueError(
            f"Could not find a symbol column among {SYMBOL_COLUMN_ALIASES} "
            f"in fetched (flattened) price board data. Columns present: "
            f"{list(flat_df.columns)}. Run discover_price_board_schema.py "
            f"against a live key to confirm the real column name."
        )

    snapshot_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = flat_df.to_dict(orient="records")

    out = pd.DataFrame(
        {
            "symbol": flat_df[symbol_col].astype(str),
            "snapshot_at": snapshot_at,
            "data_json": [_row_to_json(r) for r in records],
        }
    )
    out["fetched_at"] = snapshot_at

    dupes = out.duplicated(subset=["symbol", "snapshot_at"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_snapshot produced {dupes} duplicate (symbol, "
            f"snapshot_at) row(s) -- likely the same symbol appeared "
            f"twice in one price_board() response, refusing to write "
            f"ambiguous data."
        )

    return out[SNAPSHOT_COLUMNS]


def _row_to_json(row: "dict[object, object]") -> str:
    def _default(o: object) -> str:
        return str(o)

    return json.dumps(row, default=_default, ensure_ascii=False)


def write_snapshot(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to staging, then promote to core. ACCUMULATE
    retention (DECISIONS.md 2026-08-14): never deletes prior snapshots for
    a symbol -- only guards against re-inserting the exact same
    (symbol, snapshot_at) key, which in practice won't collide since
    snapshot_at is a real-time timestamp captured at fetch time.
    """
    missing = set(SNAPSHOT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Snapshot DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    con.register("snapshot_df", df[SNAPSHOT_COLUMNS])
    con.execute(
        "INSERT INTO staging.realtime_quote_snapshot SELECT * FROM snapshot_df "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM staging.realtime_quote_snapshot s "
        "  WHERE s.symbol = snapshot_df.symbol AND s.snapshot_at = snapshot_df.snapshot_at"
        ")"
    )
    con.execute(
        "INSERT INTO core.realtime_quote_snapshot SELECT * FROM snapshot_df "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM core.realtime_quote_snapshot s "
        "  WHERE s.symbol = snapshot_df.symbol AND s.snapshot_at = snapshot_df.snapshot_at"
        ")"
    )
    con.unregister("snapshot_df")

    return len(df)


def run(symbols: "list[str] | str") -> int:
    """Entry point: fetch live, normalize, write. Returns row count written.

    Accepts either a single symbol (str, normalized to a 1-element list --
    makes this orchestrator-compatible, since batch_orchestrator calls
    crawl_fn(symbol) with a bare string) or a list of symbols for a
    genuine multi-symbol price-board snapshot in one call.
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    raw = fetch_raw(symbols)
    normalized = normalize_snapshot(raw)
    return write_snapshot(normalized)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F007: crawl a realtime price-board snapshot")
    parser.add_argument("symbols", nargs="+", help="One or more ticker symbols")
    args = parser.parse_args()

    n = run(args.symbols)
    print(f"F007 realtime_quote_snapshot: wrote {n} rows to core.realtime_quote_snapshot")