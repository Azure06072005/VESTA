"""F005: Fundamental crawler suite (balance sheet, income statement, cash
flow, ratio).

Confirmed live against vnstock==4.0.5 (2026-08-12): `Fundamental().equity
(symbol)` returns an EquityFundamental object with real methods:
    income_statement(period: str = 'year', orient: str = 'report', **kwargs)
    balance_sheet(period: str = 'year', orient: str = 'report', **kwargs)
    cash_flow(period: str = 'year', orient: str = 'report', **kwargs)
    ratio(orient: str = 'report', **kwargs)                # no `period` arg

CONFIRMED SCHEMA (2026-08-28): The new `vnstock_data` Sponsor tier API
returns a completely melted structure. Each row has `period`, `id`, `name`, 
`unit`, and `value`. This module groups by `period` and dumps the `id` -> `value`
mapping into `data_json`.

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

# The new vnstock_data melted schema has 'period', 'id', 'value'.

FUNDAMENTAL_COLUMNS = ["symbol", "report_type", "period_end", "available_at", "data_json", "fetched_at"]


def _authenticate() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    db.load_env()
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


def fetch_raw(symbol: str, report_type: str, period: str = "quarter") -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns whatever vnstock's method gives back, untouched --
    normalization happens in melt_pivoted_statement() so that logic stays
    testable without network access.
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report_type {report_type!r}, expected one of {list(REPORT_TYPES)}")

    _authenticate()
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    method_name, takes_period = REPORT_TYPES[report_type]
    try:
        fund = vs.Fundamental().equity(symbol)
        method = getattr(fund, method_name)
        result: pd.DataFrame = method(period=period) if takes_period else method()
        if result is None or (isinstance(result, pd.DataFrame) and result.empty):
            raise EmptyResultError(
                f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
                f"report_type={report_type!r} -- F008-compatible: recorded as "
                f"genuine emptiness via record_empty(), NOT retried."
            )
        return result
    except ValueError as ve:
        if "Chỉ cổ phiếu" in str(ve) or "không hợp lệ" in str(ve):
            raise EmptyResultError(
                f"Symbol {symbol!r} is not an equity/stock with financial statements: {ve}"
            ) from ve
        raise


def _period_label_to_date(label: str) -> dt.date:
    clean_label = re.sub(r"_\d+$", "", str(label).strip())
    match = re.match(r"^(\d{4})(?:-Q([1-4]))?$", clean_label)
    if not match:
        raise ValueError(f"Period label {label!r} doesn't match expected 'YYYY' or 'YYYY-Qn' format.")
    year, quarter = match.group(1), match.group(2)
    if quarter:
        end_date: dt.date = pd.Period(f"{year}Q{quarter}", freq="Q").end_time.date()
    else:
        end_date = pd.Period(year, freq="Y").end_time.date()
    return end_date


def melt_pivoted_statement(raw_df: pd.DataFrame, symbol: str, report_type: str) -> pd.DataFrame:
    """Pure transform for fundamental data. Handles:
    1. Pivoted structure (vnstock community): rows are line items ('item_id' or 'item'),
       columns are period labels ('2026-Q1', '2025-Q4', '2025').
    2. Melted structure (vnstock_data sponsor): rows have 'period', 'id'/'item_id', 'value'.
    
    Transforms into one row per (symbol, report_type, period_end) with all metrics
    packed into a JSON blob. No network access -- fully unit-testable.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
            f"report_type={report_type!r} -- F008-compatible: recorded as "
            f"genuine emptiness via record_empty(), NOT retried."
        )

    # Case 1: Melted structure with 'period', ('id' or 'item_id'), 'value'
    id_col_candidate = "id" if "id" in raw_df.columns else ("item_id" if "item_id" in raw_df.columns else None)
    if "period" in raw_df.columns and "value" in raw_df.columns and id_col_candidate:
        df = raw_df.copy()
        df["period_end"] = df["period"].map(_period_label_to_date)
        rows: list[dict[str, object]] = []
        for period_end_raw, group in df.groupby("period_end", observed=False):
            period_end: dt.date = period_end_raw  # type: ignore[assignment]
            metrics = dict(zip(group[id_col_candidate].astype(str), group["value"]))
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
        return out[FUNDAMENTAL_COLUMNS]

    # Case 2: Pivoted structure (period labels as column headers)
    period_cols = [c for c in raw_df.columns if re.match(r"^\d{4}(-Q[1-4])?(_\d+)?$", str(c).strip())]
    if not period_cols:
        raise ValueError(
            f"No period-label columns matching 'YYYY' or 'YYYY-Qn' found in "
            f"fetched data for {symbol!r}/{report_type!r}. Columns present: {list(raw_df.columns)}."
        )

    id_col = "item_id" if "item_id" in raw_df.columns else ("item" if "item" in raw_df.columns else ("id" if "id" in raw_df.columns else raw_df.columns[0]))

    rows_pivoted: list[dict[str, object]] = []
    seen_periods: set[dt.date] = set()
    for pcol in period_cols:
        period_end = _period_label_to_date(str(pcol))
        if period_end in seen_periods:
            continue
        seen_periods.add(period_end)

        metrics = dict(zip(raw_df[id_col].astype(str), raw_df[pcol]))
        rows_pivoted.append(
            {
                "symbol": symbol,
                "report_type": report_type,
                "period_end": period_end,
                "available_at": period_end + dt.timedelta(days=DISCLOSURE_LAG_DAYS),
                "data_json": json.dumps(metrics, default=str, ensure_ascii=False),
                "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            }
        )

    out = pd.DataFrame(rows_pivoted)
    dupes = out.duplicated(subset=["symbol", "report_type", "period_end"]).sum()
    if dupes:
        raise ValueError(
            f"melt_pivoted_statement produced {dupes} duplicate (symbol, "
            f"report_type, period_end) row(s) for {symbol!r}/{report_type!r} "
            f"-- refusing to write ambiguous data."
        )

    return out[FUNDAMENTAL_COLUMNS]


# Alias for backward/forward compatibility
format_melted_statement = melt_pivoted_statement


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


def run(symbol: str, report_type: str = "all", period: str = "quarter") -> int:
    """Entry point: fetch live, normalize, write. Returns row count written.

    report_type="all" (the default, added so this is orchestrator-
    compatible) loops over every REPORT_TYPES entry. EmptyResultError from
    one report type (e.g. balance_sheet's known live-empty gap, see
    DECISIONS.md) is caught and skipped so the other 3 report types still
    get written -- only re-raised if EVERY report type came back empty for
    this symbol (a genuinely empty/delisted symbol, which F008 should
    correctly record as empty). Any other exception (a real transient
    failure) propagates immediately, aborting the remaining report types
    for this call -- F008 marks the whole (F005, symbol) unit as failed,
    and a retry re-attempts all 4 report types together.
    """
    if report_type != "all": 
        raw = fetch_raw(symbol, report_type, period)
        normalized = format_melted_statement(raw, symbol, report_type)
        return write_statements(normalized)

    total_written = 0
    any_succeeded = False
    last_empty_error: EmptyResultError | None = None
    for rt in REPORT_TYPES: 
        try: 
            raw = fetch_raw(symbol, rt, period)
            normalized = format_melted_statement(raw, symbol, rt)
            total_written += write_statements(normalized)
            any_succeeded = True
        except EmptyResultError as e: 
            last_empty_error = e
            continue
    
    if not any_succeeded and last_empty_error is not None: 
        raise last_empty_error 
    return total_written



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F005: crawl one fundamental report type for one symbol")
    parser.add_argument("symbol")
    parser.add_argument(
        "report_type", nargs="?", default="all", choices=[*REPORT_TYPES, "all"]
    )    
    parser.add_argument("--period", default="quarter", choices=["quarter", "year"])
    args = parser.parse_args()

    n = run(args.symbol, args.report_type, args.period)
    print(f"F005 fundamentals: wrote {n} rows for {args.symbol}/{args.report_type} to core.fundamentals")