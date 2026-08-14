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

SOURCED (2026-08-12, see DECISIONS.md): `available_at` is computed as
`period_end + DISCLOSURE_LAG_DAYS` (30 days). This is grounded in Circular
96/2020/TT-BTC's 20-day quarterly disclosure deadline plus a buffer for
the commonly observed pattern of extension requests -- it is still a
single-constant approximation across all symbols/periods, not a real
per-filing disclosure date (vnstock exposes no such field), but it is no
longer an ungrounded guess.

RESOLVED (2026-08-12, formally accepted by Tran Dieu, see DECISIONS.md):
`balance_sheet()` returned a completely empty DataFrame for the test
symbol against a live call. This is accepted as a real vnstock API gap,
not a bug -- income_statement, cash_flow, and ratio are unaffected and
proceed to `passing` independently. balance_sheet's crawl still fails
loudly on the empty fetch by design; that is correct behavior, not
something to catch and paper over.

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

from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

DISCLOSURE_LAG_DAYS = 30

REPORT_TYPES: dict[str, tuple[str, bool]] = {
    "income_statement": ("income_statement", True),
    "balance_sheet": ("balance_sheet", True),
    "cash_flow": ("cash_flow", True),
    "ratio": ("ratio", False),
}

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
    """Live network call. Requires VNSTOCK_API_KEY to be set."""
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report_type {report_type!r}, expected one of {list(REPORT_TYPES)}")

    _authenticate()
    import vnstock

    method_name, takes_period = REPORT_TYPES[report_type]
    fund = vnstock.Fundamental().equity(symbol)
    method = getattr(fund, method_name)
    result: pd.DataFrame = method(period=period) if takes_period else method()
    return result


def _parse_period_column(col: str) -> dt.date | None:
    import re
    col_str = str(col).strip()
    m_quarter = re.match(r"^(\d{4})-Q([1-4])(?:_\d+)?$", col_str)
    if m_quarter:
        year = int(m_quarter.group(1))
        q = int(m_quarter.group(2))
        quarter_end_days = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        month, day = quarter_end_days[q]
        return dt.date(year, month, day)

    m_year = re.match(r"^(\d{4})(?:_\d+)?$", col_str)
    if m_year:
        year = int(m_year.group(1))
        return dt.date(year, 12, 31)

    return None


def melt_pivoted_statement(raw_df: pd.DataFrame, symbol: str, report_type: str) -> pd.DataFrame:
    """Pure transform: converts pivoted financial statement (rows=metrics,
    cols=period labels) into one row per period with a JSON data blob.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
            f"report_type={report_type!r} -- F008-compatible: recorded as "
            f"genuine emptiness via record_empty(), NOT retried."
        )

    candidate_id_cols = ["item_id", "item", "name", "metric"]
    id_col = next((c for c in candidate_id_cols if c in raw_df.columns), raw_df.columns[0])

    period_cols_map: dict[str, dt.date] = {}
    for col in raw_df.columns:
        if col == id_col:
            continue
        p_date = _parse_period_column(col)
        if p_date is not None:
            period_cols_map[col] = p_date

    if not period_cols_map:
        raise ValueError(
            f"No period-label columns found in fetched fundamental data. "
            f"Columns present: {list(raw_df.columns)}."
        )

    rows = []
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for col, period_end in period_cols_map.items():
        metrics = {}
        for _, r in raw_df.iterrows():
            metric_key = str(r[id_col])
            val = r[col]
            metrics[metric_key] = val if pd.notnull(val) else None

        available_at = period_end + dt.timedelta(days=DISCLOSURE_LAG_DAYS)
        rows.append(
            {
                "symbol": symbol,
                "report_type": report_type,
                "period_end": period_end,
                "available_at": available_at,
                "data_json": _row_to_json(metrics),
                "fetched_at": now,
            }
        )

    out = pd.DataFrame(rows)
    dupes = out.duplicated(subset=["symbol", "report_type", "period_end"]).sum()
    if dupes:
        raise ValueError(
            f"melt_pivoted_statement produced {dupes} duplicate (symbol, "
            f"report_type, period_end) row(s) for {symbol!r}/{report_type!r}."
        )

    return out[FUNDAMENTAL_COLUMNS]


def normalize_statement(raw_df: pd.DataFrame, symbol: str, report_type: str) -> pd.DataFrame:
    """Backward-compatible alias for melt_pivoted_statement."""
    return melt_pivoted_statement(raw_df, symbol, report_type)


def _row_to_json(row: "dict[str, object] | dict[object, object] | dict[str, object | None]") -> str:
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