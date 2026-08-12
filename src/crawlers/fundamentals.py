"""F005: Fundamental crawler suite (balance sheet, income statement, cash
flow, ratio).

Confirmed live against vnstock==4.0.5 (2026-08-12): `Fundamental().equity
(symbol)` returns an EquityFundamental object with real methods:
    income_statement(period: str = 'year', orient: str = 'report', **kwargs)
    balance_sheet(period: str = 'year', orient: str = 'report', **kwargs)
    cash_flow(period: str = 'year', orient: str = 'report', **kwargs)
    ratio(orient: str = 'report', **kwargs)                # no `period` arg
These signatures were introspected directly -- note `ratio()` takes no
`period` kwarg, and none of the four take `limit` (the earlier partially-
hallucinated report claimed `limit=5`; that kwarg does not exist here).

UNCONFIRMED / ASSUMED, flagged explicitly rather than silently coded
around (PROJECT_INSTRUCTIONS.md A1):
1. Actual column names each method returns -- unknown until
   discover_fundamentals_schema.py is run live. normalize_statement()
   requires a `period_end` column to exist and fails loudly if it
   doesn't, rather than guessing.
2. `available_at` (real public disclosure date) is NOT exposed by vnstock
   at all. This module computes it as `period_end + DISCLOSURE_LAG_DAYS`
   -- an assumed reporting-lag constant, not a real disclosure date. This
   is a placeholder approximation, not the "actual public disclosure
   date" the feature spec calls for. It must be logged as its own
   DECISIONS.md entry (lag length + justification) before F005 can be
   considered to meet its own point-in-time correctness requirement --
   F102's look-ahead-bias join depends on this being right.

financial_health (5th sub-dataset in the original spec) is out of scope
for this pass -- no confirmed vnstock method for it was found. Left as an
open item, not silently implemented as a guess.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

# SOURCED (2026-08-12, see DECISIONS.md): Circular 96/2020/TT-BTC sets a
# 20-day regulatory deadline for quarterly financial report submission.
# Real-world practice regularly exceeds this -- extension requests to
# HOSE are common, with documented cases (e.g. REE) requesting Q4 filing
# out to 30 days. 30 days = regulatory deadline + buffer for the commonly
# observed extension pattern, chosen because underestimating the lag
# leaks future information into F102's backtest (worse failure mode than
# overestimating and discarding a few real data points).
DISCLOSURE_LAG_DAYS = 30

# report_type -> (method name, whether it accepts a `period` kwarg)
REPORT_TYPES: dict[str, tuple[str, bool]] = {
    "income_statement": ("income_statement", True),
    "balance_sheet": ("balance_sheet", True),
    "cash_flow": ("cash_flow", True),
    "ratio": ("ratio", False),
}

# UNCONFIRMED -- see module docstring point 1. Update once
# discover_fundamentals_schema.py output is available.
PERIOD_END_ALIASES = ["period_end", "date", "report_date", "period"]

FUNDAMENTAL_COLUMNS = ["symbol", "report_type", "period_end", "available_at", "data_json", "fetched_at"]


def _authenticate() -> None:
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    import vnstock  # local import: keep vnstock optional for pure unit tests

    vnstock.change_api_key(api_key)


def fetch_raw(symbol: str, report_type: str, period: str = "quarter") -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns whatever vnstock's method gives back, untouched --
    normalization happens in normalize_statement() so that logic stays
    testable without network access.
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report_type {report_type!r}, expected one of {list(REPORT_TYPES)}")

    _authenticate()
    import vnstock

    method_name, takes_period = REPORT_TYPES[report_type]
    fund = vnstock.Fundamental().equity(symbol)
    method = getattr(fund, method_name)
    result: pd.DataFrame = method(period=period) if takes_period else method()
    return result


def _find_period_end_column(df: pd.DataFrame) -> str:
    for candidate in PERIOD_END_ALIASES:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"Could not find a period-end column in fetched fundamental data. "
        f"Columns present: {list(df.columns)}. PERIOD_END_ALIASES tried: "
        f"{PERIOD_END_ALIASES}. Run discover_fundamentals_schema.py against "
        f"a live key and update PERIOD_END_ALIASES rather than guessing."
    )


def normalize_statement(raw_df: pd.DataFrame, symbol: str, report_type: str) -> pd.DataFrame:
    """Pure transform: one row per (symbol, report_type, period_end), the
    full raw row stored as JSON in data_json (schema-flexible since each
    report type has a very different column set -- see F005's spec noting
    ~28-156 columns depending on statement type), plus the assumed
    available_at. No network access -- fully unit-testable.
    """
    if raw_df.empty:
        raise ValueError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
            f"report_type={report_type!r} -- per conventions.md, crawlers "
            f"fail loudly rather than silently substituting stale data."
        )

    period_col = _find_period_end_column(raw_df)
    period_end = pd.to_datetime(raw_df[period_col]).dt.date

    out = pd.DataFrame(
        {
            "symbol": symbol,
            "report_type": report_type,
            "period_end": period_end,
            "available_at": period_end + pd.Timedelta(days=DISCLOSURE_LAG_DAYS),
        }
    )
    records = raw_df.to_dict(orient="records")
    out["data_json"] = [_row_to_json(r) for r in records]
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    dupes = out.duplicated(subset=["symbol", "report_type", "period_end"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_statement produced {dupes} duplicate (symbol, "
            f"report_type, period_end) row(s) for {symbol!r}/{report_type!r} "
            f"-- refusing to write ambiguous data."
        )

    return out[FUNDAMENTAL_COLUMNS]


def _row_to_json(row: "dict[object, object]") -> str:
    import json

    def _default(o: object) -> str:
        if isinstance(o, (dt.date, dt.datetime, pd.Timestamp)):
            return str(o)
        return str(o)

    return json.dumps(row, default=_default, ensure_ascii=False)


def write_statements(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to staging, then promote to core for this
    (symbol, report_type) only. Idempotent: re-running replaces the same
    keys rather than duplicating them.
    """
    missing = set(FUNDAMENTAL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Fundamental DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    keys = df[["symbol", "report_type"]].drop_duplicates().to_records(index=False).tolist()

    con.register("fund_df", df[FUNDAMENTAL_COLUMNS])
    for symbol, report_type in keys:
        con.execute(
            "DELETE FROM staging.fundamentals WHERE symbol = ? AND report_type = ?",
            [symbol, report_type],
        )
        con.execute(
            "DELETE FROM core.fundamentals WHERE symbol = ? AND report_type = ?",
            [symbol, report_type],
        )
    con.execute("INSERT INTO staging.fundamentals SELECT * FROM fund_df")
    con.execute("INSERT INTO core.fundamentals SELECT * FROM fund_df")
    con.unregister("fund_df")

    return len(df)


def run(symbol: str, report_type: str, period: str = "quarter") -> int:
    """Entry point: fetch live, normalize, write. Returns row count written."""
    raw = fetch_raw(symbol, report_type, period)
    normalized = normalize_statement(raw, symbol, report_type)
    return write_statements(normalized)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F005: crawl one fundamental report type for one symbol")
    parser.add_argument("symbol")
    parser.add_argument("report_type", choices=list(REPORT_TYPES))
    parser.add_argument("--period", default="quarter", choices=["quarter", "year"])
    args = parser.parse_args()

    n = run(args.symbol, args.report_type, args.period)
    print(f"F005 fundamentals: wrote {n} rows for {args.symbol}/{args.report_type} to core.fundamentals")