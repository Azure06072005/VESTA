"""F008: Retry/reconciliation module.

Generic coordinator over meta.crawl_progress (created in F000). Any
crawler can report success/failure/genuine-emptiness for a
(dataset_name, symbol) unit of work through this module, and
get_retryable_jobs() tells the caller what's safe to retry.
"""
from __future__ import annotations

import datetime as dt
import sys
import pathlib
from typing import Callable, TypeVar

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

T = TypeVar("T")


class EmptyResultError(Exception):
    """Raise this from a crawler call passed to run_job() to signal a
    genuinely empty API response (not a failure) -- it will be recorded
    as status='empty' and will NOT be retried again.
    """


def _get_retry_count(con: duckdb.DuckDBPyConnection, dataset_name: str, symbol: str) -> int | None:
    row = con.execute(
        "SELECT retry_count FROM meta.crawl_progress WHERE dataset_name = ? AND symbol = ?",
        [dataset_name, symbol],
    ).fetchone()
    return row[0] if row else None


def _upsert(
    con: duckdb.DuckDBPyConnection,
    dataset_name: str,
    symbol: str,
    status: str,
    retry_count: int,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    existing = _get_retry_count(con, dataset_name, symbol)
    if existing is None:
        con.execute(
            "INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt) "
            "VALUES (?, ?, ?, ?, ?)",
            [dataset_name, symbol, status, retry_count, now],
        )
    else:
        con.execute(
            "UPDATE meta.crawl_progress SET status = ?, retry_count = ?, last_attempt = ? "
            "WHERE dataset_name = ? AND symbol = ?",
            [status, retry_count, now, dataset_name, symbol],
        )


def record_success(con: duckdb.DuckDBPyConnection, dataset_name: str, symbol: str) -> None:
    """Success resets retry_count to 0 -- a later transient failure on the
    same (dataset, symbol) starts its retry budget fresh."""
    _upsert(con, dataset_name, symbol, status="success", retry_count=0)


def record_empty(con: duckdb.DuckDBPyConnection, dataset_name: str, symbol: str) -> None:
    """Genuine API emptiness -- not a failure, never retried again."""
    _upsert(con, dataset_name, symbol, status="empty", retry_count=0)


def record_transient_failure(con: duckdb.DuckDBPyConnection, dataset_name: str, symbol: str) -> int:
    """Increments retry_count and marks status='failed'. Returns the new
    retry_count so the caller can check it against max_retry immediately
    if needed."""
    existing = _get_retry_count(con, dataset_name, symbol)
    new_retry_count = (existing or 0) + 1
    _upsert(con, dataset_name, symbol, status="failed", retry_count=new_retry_count)
    return new_retry_count


def get_retryable_jobs(con: duckdb.DuckDBPyConnection, max_retry: int = 3) -> list[tuple[str, str, int]]:
    """(dataset_name, symbol, retry_count) tuples still under the retry
    budget. 'empty' and 'success' rows are never retryable."""
    rows = con.execute(
        "SELECT dataset_name, symbol, retry_count FROM meta.crawl_progress "
        "WHERE status = 'failed' AND retry_count < ? ORDER BY dataset_name, symbol",
        [max_retry],
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def get_exhausted_jobs(con: duckdb.DuckDBPyConnection, max_retry: int = 3) -> list[tuple[str, str, int]]:
    """(dataset_name, symbol, retry_count) tuples that hit max_retry and
    will NOT be retried again by get_retryable_jobs() -- surfaced
    separately so a human/alert can see what's permanently stuck."""
    rows = con.execute(
        "SELECT dataset_name, symbol, retry_count FROM meta.crawl_progress "
        "WHERE status = 'failed' AND retry_count >= ? ORDER BY dataset_name, symbol",
        [max_retry],
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def run_job(
    con: duckdb.DuckDBPyConnection,
    dataset_name: str,
    symbol: str,
    fn: Callable[[], T],
) -> T | None:
    """Run fn() once, recording the outcome in meta.crawl_progress."""
    try:
        result = fn()
    except EmptyResultError:
        record_empty(con, dataset_name, symbol)
        return None
    except Exception:
        record_transient_failure(con, dataset_name, symbol)
        raise
    else:
        record_success(con, dataset_name, symbol)
        return result


def retry_all(
    con: duckdb.DuckDBPyConnection,
    dataset_name: str,
    fn_factory: Callable[[str], Callable[[], T]],
    max_retry: int = 3,
) -> dict[str, list[str]]:
    """Re-run every retryable job for a given dataset."""
    outcome: dict[str, list[str]] = {"succeeded": [], "failed": [], "empty": []}
    jobs = [j for j in get_retryable_jobs(con, max_retry) if j[0] == dataset_name]
    for _, symbol, _ in jobs:
        try:
            result = run_job(con, dataset_name, symbol, fn_factory(symbol))
        except Exception:
            outcome["failed"].append(symbol)
            continue
        if result is None:
            outcome["empty"].append(symbol)
        else:
            outcome["succeeded"].append(symbol)
    return outcome


if __name__ == "__main__":
    connection = db.bootstrap_schema()
    retryable = get_retryable_jobs(connection)
    exhausted = get_exhausted_jobs(connection)
    print(f"F008: {len(retryable)} retryable job(s), {len(exhausted)} exhausted job(s)")
    for dataset_name, symbol, retry_count in exhausted:
        print(f"  EXHAUSTED: {dataset_name}/{symbol} (retry_count={retry_count})")
