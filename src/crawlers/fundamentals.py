"""F005: Fundamental crawler suite (balance sheet, income statement, cash
flow, ratio).

Confirmed live against vnstock==4.0.5 (2026-08-12): `Fundamental().equity
(symbol)` returns an EquityFundamental object with real methods:
    income_statement(period: str = 'year', orient: str = 'report', **kwargs)
    balance_sheet(period: str = 'year', orient: str = 'report', **kwargs)
    cash_flow(period: str = 'year', orient: str = 'report', **kwargs)
    ratio(orient: str = 'report', **kwargs)                # no `period` arg

CONFIRMED SCHEMA (2026-08-12, live discovery run, replaces the first
guess): the returned frame is PIVOTED, not one-row-per-period. Each row is
a financial line item (identified by an id/name column); each column
after the id column(s) is a period label like '2026-Q1' or a bare year
like '2025'. There is no `period_end` column at all -- the original
column-alias-lookup approach in this module's first version was wrong and
has been replaced with melt_pivoted_statement().

KNOWN ISSUE: `balance_sheet()` returned a completely empty DataFrame for
the test symbol against a live call. This is accepted as a real vnstock
API gap, not a bug -- income_statement, cash_flow, and ratio are
unaffected and proceed to `passing` independently. balance_sheet's crawl
still fails loudly on the empty fetch by design (raises EmptyResultError,
F008-compatible: recorded as genuine emptiness, not retried); that is
correct behavior, not something to catch and paper over.

SOURCED (2026-08-12, see DECISIONS.md): `available_at` is computed as
`period_end + DISCLOSURE_LAG_DAYS` (30 days). This is grounded in Circular
96/2020/TT-BTC's 20-day quarterly disclosure deadline plus a buffer for
the commonly observed pattern of extension requests -- it is still a
single-constant approximation across all symbols/periods, not a real
per-filing disclosure date (vnstock exposes no such field), but it is no
longer an ungrounded guess.

financial_health (5th sub-dataset in the original spec) remains out of
scope -- no confirmed vnstock method for it was found.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

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

# Matches period column labels: '2026-Q1', '2025-Q4', or a bare year '2025'.
PERIOD_COLUMN_PATTERN = re.compile(r"^\d{4}(-Q[1-4])?$")

# Preferred order for the metric-identifier column among the non-period
# columns. UNCONFIRMED which of these actually appears -- picks the first
# match found, or falls back to whatever non-period column exists.
ID_COLUMN_CANDIDATES = ["item_id", "item", "name", "criteria"]

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
    normalization happens in melt_pivoted_statement() so that logic stays
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


def _period_label_to_date(label: str) -> dt.date:
    match = re.match(r"^(\d{4})(?:-Q([1-4]))?$", str(label))
    if not match:
        raise ValueError(f"Period label {label!r} doesn't match expected 'YYYY' or 'YYYY-Qn' format.")
    year, quarter = match.group(1), match.group(2)
    if quarter:
        end_date: dt.date = pd.Period(f"{year}Q{quarter}", freq="Q").end_time.date()
    else:
        end_date = pd.Period(year, freq="Y").end_time.date()
    return end_date


def melt_pivoted_statement(raw_df: pd.DataFrame, symbol: str, report_type: str) -> pd.DataFrame:
    """Pure transform for vnstock's confirmed pivoted shape: rows are
    financial line items, columns after the id column(s) are period
    labels ('2026-Q1', '2025', ...). Melts to one row per (symbol,
    report_type, period_end) with all metrics for that period packed into
    a JSON blob (data_json), since each report type has a very different,
    wide set of line items. No network access -- fully unit-testable.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
            f"report_type={report_type!r} -- F008-compatible: recorded as "
            f"genuine emptiness via record_empty(), NOT retried. "
            f"(Confirmed live 2026-08-12: balance_sheet returned empty for "
            f"the test symbol -- FORMALLY ACCEPTED as a real vnstock API "
            f"gap, not a bug, see DECISIONS.md.)"
        )

    period_cols = [c for c in raw_df.columns if PERIOD_COLUMN_PATTERN.match(str(c))]
    if not period_cols:
        raise ValueError(
            f"No period-label columns (matching 'YYYY' or 'YYYY-Qn') found "
            f"in fetched data for {symbol!r}/{report_type!r}. Columns "
            f"present: {list(raw_df.columns)}. The pivoted-schema assumption "
            f"in this module may no longer hold -- re-run "
            f"discover_fundamentals_schema.py before changing this code."
        )

    id_cols = [c for c in raw_df.columns if c not in period_cols]
    if not id_cols:
        raise ValueError(
            f"No non-period (id/metric-name) columns found for "
            f"{symbol!r}/{report_type!r}. Columns present: {list(raw_df.columns)}."
        )
    metric_key_col = next((c for c in ID_COLUMN_CANDIDATES if c in id_cols), id_cols[0])

    melted = raw_df.melt(id_vars=id_cols, value_vars=period_cols, var_name="period_label", value_name="value")
    melted["period_end"] = melted["period_label"].map(_period_label_to_date)

    rows: list[dict[str, object]] = []
    for period_end_raw, group in melted.groupby("period_end"):
        period_end: dt.date = period_end_raw  # type: ignore[assignment]
        metrics = dict(zip(group[metric_key_col].astype(str), group["value"]))
        rows.append(
            {
                "symbol": symbol,
                "report_type": report_type,
                "period_end": period_end,
                "available_at": period_end + dt.timedelta(days=DISCLOSURE_LAG_DAYS),
                "data_json": json.dumps(metrics, default=str, ensure_ascii=False),
                "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            }
        )

    out = pd.DataFrame(rows)

    dupes = out.duplicated(subset=["symbol", "report_type", "period_end"]).sum()
    if dupes:
        raise ValueError(
            f"melt_pivoted_statement produced {dupes} duplicate (symbol, "
            f"report_type, period_end) row(s) for {symbol!r}/{report_type!r} "
            f"-- refusing to write ambiguous data."
        )

    return out[FUNDAMENTAL_COLUMNS]


def write_statements(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """APPEND-ONLY revision history (fixed 2026-08-16, see DECISIONS.md
    F009 item 3): never deletes or overwrites an existing (symbol,
    report_type, period_end) row. Compares each incoming row's data_json
    against the most recent existing revision for that period; inserts
    only if new or changed. This means a later restatement is recorded as
    an ADDITIONAL row, not a silent overwrite of the original -- avoiding
    a look-ahead-bias leak where a backtest querying 'what was known as of
    date X' would otherwise see a revised figure that didn't exist yet.

    Returns the count of rows actually written (new or changed) -- NOT
    len(df), since unchanged periods on a re-crawl are correctly skipped
    as idempotent no-ops rather than reinserted as duplicate vintages.
    """
    missing = set(FUNDAMENTAL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Fundamental DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    con.register("fund_df", df[FUNDAMENTAL_COLUMNS])

    to_write = con.execute(
        """
        WITH latest_existing AS (
            SELECT symbol, report_type, period_end, data_json,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, report_type, period_end
                       ORDER BY fetched_at DESC
                   ) AS rn
            FROM core.fundamentals
        )
        SELECT n.*
        FROM fund_df n
        LEFT JOIN (SELECT * FROM latest_existing WHERE rn = 1) e
          ON n.symbol = e.symbol
         AND n.report_type = e.report_type
         AND n.period_end = e.period_end
        WHERE e.data_json IS NULL OR e.data_json != n.data_json
        """
    ).df()
    con.unregister("fund_df")

    if to_write.empty:
        return 0

    con.register("to_write_df", to_write[FUNDAMENTAL_COLUMNS])
    con.execute("INSERT INTO staging.fundamentals SELECT * FROM to_write_df")
    con.execute("INSERT INTO core.fundamentals SELECT * FROM to_write_df")
    con.unregister("to_write_df")

    written: int = len(to_write)
    return written


def get_as_reported(con: "duckdb.DuckDBPyConnection", symbol: str, report_type: str) -> pd.DataFrame:
    """Returns the AS-REPORTED (first-ever-observed) vintage of each
    period_end -- the earliest fetched_at per (symbol, report_type,
    period_end). This is the SAFE DEFAULT for backtesting: a later
    restatement is typically more accurate but was not knowable at the
    time, so scoring a historical decision against the as-reported figure
    (not the eventual revised one) avoids revision look-ahead bias. This
    matches standard point-in-time-database practice (e.g. Compustat's
    as-reported vs. as-revised distinction) -- F102 should call this, not
    a raw SELECT against core.fundamentals, unless it has a specific
    reason to want a different vintage.
    """
    result: pd.DataFrame = con.execute(
        """
        SELECT symbol, report_type, period_end, available_at, data_json, fetched_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY symbol, report_type, period_end
                ORDER BY fetched_at ASC
            ) AS rn
            FROM core.fundamentals
            WHERE symbol = ? AND report_type = ?
        )
        WHERE rn = 1
        ORDER BY period_end
        """,
        [symbol, report_type],
    ).df()
    return result


def get_as_of(
    con: "duckdb.DuckDBPyConnection", symbol: str, report_type: str, as_of_date: dt.date
) -> pd.DataFrame:
    """Returns the most recent vintage of each period_end that our system
    had actually observed (fetched_at <= as_of_date) AND that vintage's
    own estimated disclosure date had already passed (available_at <=
    as_of_date) -- i.e. what this system could plausibly have known if it
    were running live on as_of_date. NOT the default for backtesting (see
    get_as_reported) -- use this only when a specific 'best known state as
    of a date' query is actually what's needed, since it will surface
    later restatements once both conditions are met, which is correct for
    'what do we believe today' but wrong for scoring a past decision.
    """
    result: pd.DataFrame = con.execute(
        """
        SELECT symbol, report_type, period_end, available_at, data_json, fetched_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY symbol, report_type, period_end
                ORDER BY fetched_at DESC
            ) AS rn
            FROM core.fundamentals
            WHERE symbol = ? AND report_type = ?
              AND fetched_at <= ?
              AND available_at <= ?
        )
        WHERE rn = 1
        ORDER BY period_end
        """,
        [symbol, report_type, as_of_date, as_of_date],
    ).df()
    return result


def run(symbol: str, report_type: str, period: str = "quarter") -> int:
    """Entry point: fetch live, normalize, write. Returns row count written."""
    raw = fetch_raw(symbol, report_type, period)
    normalized = melt_pivoted_statement(raw, symbol, report_type)
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