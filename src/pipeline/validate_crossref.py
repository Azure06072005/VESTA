"""F101: Cross-dataset validation gate.

Runs after F009 (the F0xx tier checkpoint). Checks referential
consistency across every core table with a symbol column: every symbol
must exist in core.dim_symbol, and no fetched_at/computed_at may be in
the future. Also traces core.price_adjustment_events.source_event_id
back to a real core.corporate_events.event_id (added because F009 item 4
introduced this derived table -- an adjustment event with no matching
corporate event would mean the adjustment logic invented data).

This is a cross-dataset check ON TOP OF each crawler's own per-batch
validation (already part of F001-F009 individually) -- not a replacement
for it, and not a substitute for F009's remediation of cross-cutting gaps
(revision handling, adjustment factors, dedup) that referential-integrity
checks alone would never catch.

Per F101's spec, this fails LOUDLY (raises ValidationError) rather than
returning a report silently -- an orphan symbol or future timestamp is a
real data-integrity bug, not a warning to note and move past.
"""
from __future__ import annotations

import datetime as dt
import sys
import pathlib

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

# (schema, table, symbol_column, timestamp_column) for every core table
# that carries a symbol and a fetched_at/computed_at-style timestamp.
TABLES_WITH_SYMBOL = [
    ("core", "market_ohlcv_daily", "symbol", "fetched_at"),
    ("core", "fundamentals", "symbol", "fetched_at"),
    ("core", "corporate_events", "symbol", "fetched_at"),
    ("core", "news", "symbol", "fetched_at"),
    ("core", "realtime_quote_snapshot", "symbol", "fetched_at"),
    ("core", "price_adjustment_events", "symbol", "computed_at"),
]


class ValidationError(Exception):
    """Raised when cross-dataset validation finds a real integrity
    problem. Never caught and silently logged -- an orphan symbol or a
    future-dated row means something upstream is genuinely broken.
    """


def get_valid_symbols(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute("SELECT symbol FROM core.dim_symbol").fetchall()
    return {r[0] for r in rows}


def find_orphan_symbols(
    con: duckdb.DuckDBPyConnection, schema: str, table: str, symbol_col: str, valid_symbols: set[str]
) -> list[str]:
    """Symbols present in this table but absent from core.dim_symbol."""
    rows = con.execute(f"SELECT DISTINCT {symbol_col} FROM {schema}.{table}").fetchall()  # noqa: S608
    present = {r[0] for r in rows}
    return sorted(present - valid_symbols)


def find_future_timestamps(
    con: duckdb.DuckDBPyConnection, schema: str, table: str, ts_col: str, now: dt.datetime | None = None
) -> int:
    """Count of rows whose fetched_at/computed_at is after `now` --
    should always be 0. A non-zero count means a crawler's clock is wrong,
    or something worse (fabricated timestamps).
    """
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    row = con.execute(f"SELECT COUNT(*) FROM {schema}.{table} WHERE {ts_col} > ?", [now]).fetchone()  # noqa: S608
    return row[0] if row is not None else 0


def find_orphan_adjustment_events(con: duckdb.DuckDBPyConnection) -> list[str]:
    """price_adjustment_events.source_event_id values with no matching
    core.corporate_events.event_id -- would mean an adjustment factor was
    computed from an event that doesn't (or no longer) exists.
    """
    for schema, table in (("core", "price_adjustment_events"), ("core", "corporate_events")):
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()
        if not exists or exists[0] == 0:
            return []  # either table doesn't exist yet -- nothing to check

    rows = con.execute(
        """
        SELECT DISTINCT a.source_event_id
        FROM core.price_adjustment_events a
        LEFT JOIN core.corporate_events e ON a.source_event_id = e.event_id
        WHERE e.event_id IS NULL
        """
    ).fetchall()
    return sorted(r[0] for r in rows)


def run_validation(con: "duckdb.DuckDBPyConnection | None" = None) -> dict[str, object]:
    """Returns a structured report of every problem found -- does NOT
    raise. Used by validate_or_raise() and by tests that want to inspect
    the report shape directly.
    """
    con = con or db.bootstrap_schema()
    valid_symbols = get_valid_symbols(con)

    orphan_symbols: dict[str, list[str]] = {}
    future_timestamps: dict[str, int] = {}

    for schema, table, symbol_col, ts_col in TABLES_WITH_SYMBOL:
        table_exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()
        if not table_exists or table_exists[0] == 0:
            continue  # table not created yet (e.g. fresh DB, feature not built) -- nothing to check

        orphans = find_orphan_symbols(con, schema, table, symbol_col, valid_symbols)
        if orphans:
            orphan_symbols[f"{schema}.{table}"] = orphans

        future_count = find_future_timestamps(con, schema, table, ts_col)
        if future_count:
            future_timestamps[f"{schema}.{table}"] = future_count

    orphan_adjustment_events = find_orphan_adjustment_events(con)

    return {
        "orphan_symbols": orphan_symbols,
        "future_timestamps": future_timestamps,
        "orphan_adjustment_events": orphan_adjustment_events,
    }


def validate_or_raise(con: "duckdb.DuckDBPyConnection | None" = None) -> None:
    """Entry point for CI/CLI use: raises ValidationError with every
    problem listed if anything is wrong, otherwise returns silently.
    """
    report = run_validation(con)
    problems = []

    if report["orphan_symbols"]:
        problems.append(f"orphan symbols (present in a table but not in core.dim_symbol): {report['orphan_symbols']}")
    if report["future_timestamps"]:
        problems.append(f"future-dated rows (fetched_at/computed_at after now): {report['future_timestamps']}")
    if report["orphan_adjustment_events"]:
        problems.append(
            f"price_adjustment_events with no matching corporate_events row: {report['orphan_adjustment_events']}"
        )

    if problems:
        raise ValidationError("Cross-dataset validation FAILED:\n" + "\n".join(f"  - {p}" for p in problems))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F101: cross-dataset referential integrity validation")
    parser.add_argument("--all", action="store_true", help="run all checks (currently the only mode)")
    parser.parse_args()

    validate_or_raise()
    print("PASS")