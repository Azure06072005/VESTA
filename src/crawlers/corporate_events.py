"""F006: Corporate events crawler.

Confirmed live against vnstock==4.0.5 (2026-08-13, real discovery output
pasted by Tran Dieu): the real per-symbol events source is
`Company(source='VCI', symbol=symbol).events()`.

CONFIRMED SCHEMA (replaces the earlier alias-guessing version):
- Real id column: `id` (string, e.g. Mongo-style ObjectId strings).
- Real closed-set category column: `category`, with exactly 4 observed
  values: DIVIDEND, MAJOR_SHAREHOLDER_TRADING, OTHER, SHAREHOLDER_MEETING.
  This is the field used for event_type -- clean closed set, matches
  F006's spec requirement directly. (`event_code` is a finer-grained
  closed set -- AGME, AIS, DDIND, DDINS, DDRP, DIV, ISS -- kept available
  as an alias but `category` is preferred as the primary classification.)
- Real primary date column: `display_date1` (populated on every observed
  row, unlike start_date/end_date/record_date which show 'nan' for some
  event types). Other date fields (public_date, record_date, exright_date,
  payout_date, issue_date, listing_date) vary by event category and are
  preserved in detail_json rather than promoted to columns.
- CONFIRMED: no chunking by year needed. A single .events() call for FPT
  returned 50 rows spanning 2024-2035 (some forward-dated, e.g.
  listing_date values years out) -- this is full history in one call, not
  a windowed/paginated result. The original feature name's "chunked
  per-year" framing does not reflect how the API actually works.
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
from etl.retry_failed_jobs import EmptyResultError

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

# CONFIRMED live 2026-08-13 -- see module docstring.
EVENT_ID_ALIASES = ["id", "event_id"]
EVENT_TYPE_ALIASES = ["category", "event_code", "event_type"]
EVENT_DATE_ALIASES = ["display_date1", "public_date", "record_date", "exright_date"]

# CONFIRMED live 2026-08-13 against a real call for FPT -- the 4 observed
# `category` values. If a 5th value shows up for another symbol, it will
# be logged (not dropped) and should be added here deliberately.
KNOWN_EVENT_TYPES: set[str] = {
    "DIVIDEND",
    "MAJOR_SHAREHOLDER_TRADING",
    "OTHER",
    "SHAREHOLDER_MEETING",
}

EVENT_COLUMNS = ["symbol", "event_id", "event_type", "event_date", "detail_json", "fetched_at"]


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


def fetch_raw(symbol: str) -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns whatever vnstock's .events() gives back, untouched --
    normalization happens in normalize_events() so that logic stays
    testable without network access. Confirmed live 2026-08-13: returns
    full history in one call (50 rows for FPT, spanning 2024-2035) -- no
    year-chunking needed.
    """
    _authenticate()
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    company = vs.Company(source="VCI", symbol=symbol)
    result: pd.DataFrame = company.events()
    return result


def _find_column(df: pd.DataFrame, aliases: list[str], field: str, required: bool = True) -> str | None:
    for candidate in aliases:
        if candidate in df.columns:
            return candidate
    if required:
        raise ValueError(
            f"Could not find a source column for '{field}' in fetched "
            f"corporate events data. Columns present: {list(df.columns)}. "
            f"Aliases tried: {aliases}. Run "
            f"discover_corporate_events_schema.py against a live key and "
            f"update the alias list rather than guessing."
        )
    return None


def normalize_events(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pure transform: map raw columns -> standard schema, classify
    event_type against KNOWN_EVENT_TYPES (logging unrecognized types
    rather than dropping them, per F006's spec), store the full raw row
    as JSON in detail_json for later event-embedding use. No network
    access -- fully unit-testable with synthetic DataFrames.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r} -- "
            f"F008-compatible: a symbol with genuinely no corporate events "
            f"is a valid, non-failure outcome -- recorded via "
            f"record_empty(), NOT retried."
        )

    id_col = _find_column(raw_df, EVENT_ID_ALIASES, "event_id")
    type_col = _find_column(raw_df, EVENT_TYPE_ALIASES, "event_type")
    date_col = _find_column(raw_df, EVENT_DATE_ALIASES, "event_date", required=False)

    unrecognized_types = sorted(set(raw_df[type_col].astype(str)) - KNOWN_EVENT_TYPES)
    if unrecognized_types:
        # Logged, not dropped -- per F006 spec ("never silently dropped").
        print(
            f"[F006] unrecognized event_type value(s) for {symbol!r}, not "
            f"in KNOWN_EVENT_TYPES (confirmed live 2026-08-13: DIVIDEND, "
            f"MAJOR_SHAREHOLDER_TRADING, OTHER, SHAREHOLDER_MEETING): "
            f"{unrecognized_types}"
        )

    records = raw_df.to_dict(orient="records")
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "event_id": raw_df[id_col].astype(str),
            "event_type": raw_df[type_col].astype(str),
            "event_date": pd.to_datetime(raw_df[date_col]).dt.date if date_col else pd.NaT,
            "detail_json": [_row_to_json(r) for r in records],
        }
    )
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    dupes = out.duplicated(subset=["symbol", "event_id"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_events produced {dupes} duplicate (symbol, "
            f"event_id) row(s) for {symbol!r} -- refusing to write "
            f"ambiguous data. This may indicate event_id isn't actually "
            f"unique per event; re-check against discovery output."
        )

    return out[EVENT_COLUMNS]


def _row_to_json(row: "dict[object, object]") -> str:
    def _default(o: object) -> str:
        return str(o)

    return json.dumps(row, default=_default, ensure_ascii=False)


def write_events(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to staging, then promote to core for this symbol
    only. Idempotent: re-running with the same input replaces the same
    (symbol, event_id) rows rather than duplicating them.
    """
    missing = set(EVENT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Corporate events DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    symbols = df["symbol"].unique().tolist()

    con.execute("DELETE FROM staging.corporate_events WHERE symbol IN ?", [symbols])
    con.register("events_df", df[EVENT_COLUMNS])
    con.execute("INSERT INTO staging.corporate_events SELECT * FROM events_df")

    con.execute("DELETE FROM core.corporate_events WHERE symbol IN ?", [symbols])
    con.execute("INSERT INTO core.corporate_events SELECT * FROM events_df")
    con.unregister("events_df")

    return len(df)


def run(symbol: str) -> int:
    """Entry point: fetch live, normalize, write. Returns row count written."""
    raw = fetch_raw(symbol)
    normalized = normalize_events(raw, symbol)
    return write_events(normalized)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F006: crawl corporate events for one symbol")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F006 corporate_events: wrote {n} rows for {args.symbol} to core.corporate_events")