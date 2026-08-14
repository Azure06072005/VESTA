"""F007 (SCOPE SHRUNK 2026-08-14, see DECISIONS.md): realtime quote
snapshot crawler only.

Original spec called for 4 sub-features: market valuation history,
technical/flow screener, gainer/loser/volume rankings, realtime quote.
Confirmed live 2026-08-13/14 against the installed vnstock==4.0.5:
- `Insights` class does not exist anywhere in the package (confirmed
  absent -- an earlier report's `Insights.ranking.gainer()` claim was
  hallucinated, see DECISIONS.md 2026-08-11 entry).
- A full survey of every top-level vnstock class (Trading, Retail, Fund,
  Quote, Market, Broker, Reference) found no confirmed method for
  valuation history, a technical/flow screener, or gainer/loser/volume
  rankings.
- `Trading(source='VCI').price_board(symbols_list=[...])` IS a real,
  confirmed-callable method (introspected directly: `price_board(
  symbols_list: Any = None, **kwargs: Any) -> Any`) and plausibly covers
  "realtime quote" -- this is the one piece of F007 this module
  implements. The other 3 sub-features are deferred, not built here --
  see DECISIONS.md for the decision and why (no confirmed free-tier
  method found; paid vnstock_data was not purchased).

UNCONFIRMED / ASSUMED, flagged explicitly (PROJECT_INSTRUCTIONS.md A1):
the actual columns/shape price_board() returns -- unknown until
discover_price_board_schema.py is run live. normalize_snapshot() stores
the full raw row as JSON rather than mapping named columns, specifically
because the shape is unconfirmed -- safer to preserve everything than to
guess which fields matter and silently drop the rest.

Retention: ACCUMULATE (per DECISIONS.md 2026-08-14) -- one row per
(symbol, snapshot_at), never overwritten. A price snapshot is a point-in-
time fact, not a correction of a prior one.
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

SNAPSHOT_COLUMNS = ["symbol", "snapshot_at", "data_json", "fetched_at"]


def _authenticate() -> None:
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    import vnstock  # local import: keep vnstock optional for pure unit tests

    vnstock.change_api_key(api_key)


def fetch_raw(symbols: list[str]) -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns whatever vnstock's price_board() gives back, untouched --
    normalization happens in normalize_snapshot() so that logic stays
    testable without network access.
    """
    _authenticate()
    import vnstock

    trading = vnstock.Trading(source="VCI")
    result: pd.DataFrame = trading.price_board(symbols_list=symbols)
    return result


def normalize_snapshot(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: one row per symbol in the fetched price board, full
    raw row preserved as JSON (schema unconfirmed -- see module
    docstring). Requires a 'symbol' or 'ticker' column to key rows by;
    fails loudly if neither is present rather than guessing. No network
    access -- fully unit-testable with synthetic DataFrames.
    """
    if raw_df.empty:
        raise EmptyResultError(
            "fetch_raw returned an empty DataFrame -- F008-compatible: "
            "recorded as genuine emptiness via record_empty(), NOT "
            "retried. (Could also indicate all requested symbols were "
            "invalid; if this fires unexpectedly, verify the symbol list "
            "first before assuming it's a transient API issue.)"
        )

    symbol_col = next((c for c in ("symbol", "ticker") if c in raw_df.columns), None)
    if symbol_col is None:
        raise ValueError(
            f"Could not find a 'symbol' or 'ticker' column in fetched "
            f"price board data. Columns present: {list(raw_df.columns)}. "
            f"Run discover_price_board_schema.py against a live key to "
            f"confirm the real column name."
        )

    snapshot_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = raw_df.to_dict(orient="records")

    out = pd.DataFrame(
        {
            "symbol": raw_df[symbol_col].astype(str),
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


def run(symbols: list[str]) -> int:
    """Entry point: fetch live, normalize, write. Returns row count written."""
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