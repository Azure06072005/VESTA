"""F009 item 6: batch/chunk orchestrator for full-universe crawls.

DECISION (2026-08-16, see DECISIONS.md): a full ~1800-symbol crawl hits
vnstock's community-tier rate limit (60 requests/minute, confirmed live in
every discovery script's banner output throughout this project) and takes
multiple hours run monolithically. Rather than rewrite any crawler, this
is a thin layer on top of F008's existing meta.crawl_progress tracking:
it iterates the symbol universe in resumable chunks, skipping symbols
already marked 'success' or 'empty' for this dataset, so an interrupted
run (network drop, manual stop, rate-limit lockout) picks up where it
left off on the next invocation instead of re-crawling from symbol 1.

This does NOT change F008's retry semantics (run_job/record_success/
record_transient_failure/record_empty are unchanged) -- it only adds the
"what's left to do" query and chunking on top.
"""
from __future__ import annotations

import sys
import time
import pathlib
from typing import Callable, TypeVar

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import run_job  # noqa: E402

T = TypeVar("T")


def get_pending_symbols(
    con: duckdb.DuckDBPyConnection, dataset_name: str, symbols: list[str], max_retry: int = 3
) -> list[str]:
    """Symbols still needing an attempt for this dataset: either never
    attempted (no row in meta.crawl_progress), or previously 'failed' and
    still under the retry budget. Symbols already 'success' or 'empty' are
    excluded -- this is what makes a re-run of the orchestrator resumable
    rather than a full restart.
    """
    if not symbols:
        return []

    con.register("candidate_symbols", pd.DataFrame({"symbol": symbols}))
    rows = con.execute(
        """
        SELECT c.symbol
        FROM candidate_symbols c
        LEFT JOIN meta.crawl_progress p
          ON p.dataset_name = ? AND p.symbol = c.symbol
        WHERE p.symbol IS NULL
           OR (p.status = 'failed' AND p.retry_count < ?)
        """,
        [dataset_name, max_retry],
    ).fetchall()
    con.unregister("candidate_symbols")

    pending = {r[0] for r in rows}
    # Preserve the caller's original ordering rather than SQL's arbitrary one.
    return [s for s in symbols if s in pending]


def run_batched(
    con: duckdb.DuckDBPyConnection,
    dataset_name: str,
    symbols: list[str],
    crawl_fn: Callable[[str], T],
    batch_size: int = 100,
    max_retry: int = 3,
    delay_between_batches_seconds: float = 0.0,
) -> dict[str, list[str]]:
    """Runs crawl_fn(symbol) for every pending symbol, in chunks of
    batch_size, recording outcomes via F008's run_job() as it goes (so a
    crash mid-batch still leaves completed symbols correctly marked).
    crawl_fn should raise EmptyResultError for genuine emptiness and let
    any other exception bubble -- same contract as F008's run_job().

    Returns {'succeeded': [...], 'failed': [...], 'empty': [...]} for
    symbols actually attempted THIS call -- symbols skipped because they
    were already done are not included (see get_pending_symbols).
    """
    pending = get_pending_symbols(con, dataset_name, symbols, max_retry)
    outcome: dict[str, list[str]] = {"succeeded": [], "failed": [], "empty": []}

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        for symbol in batch:
            bound_symbol = symbol

            def _call(s: str = bound_symbol) -> T:
                return crawl_fn(s)

            try:
                result = run_job(con, dataset_name, symbol, _call)
            except Exception:
                outcome["failed"].append(symbol)
                continue
            if result is None:
                outcome["empty"].append(symbol)
            else:
                outcome["succeeded"].append(symbol)

        is_last_batch = batch_start + batch_size >= len(pending)
        if delay_between_batches_seconds > 0 and not is_last_batch:
            time.sleep(delay_between_batches_seconds)

    return outcome


if __name__ == "__main__":
    import argparse
    import importlib

    parser = argparse.ArgumentParser(description="F009 item 6: run a crawler across a symbol universe in resumable batches")
    parser.add_argument("dataset_name", help="e.g. F002, F005 -- used as the meta.crawl_progress key")
    parser.add_argument("crawler_module", help="e.g. crawlers.market_ohlcv -- must expose a run(symbol) function")
    parser.add_argument("symbols_file", help="path to a text file, one symbol per line")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-retry", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to pause between batches")
    args = parser.parse_args()

    with open(args.symbols_file, encoding="utf-8") as f:
        symbol_list = [line.strip() for line in f if line.strip()]

    module = importlib.import_module(args.crawler_module)
    connection = db.bootstrap_schema()
    summary = run_batched(
        connection,
        args.dataset_name,
        symbol_list,
        module.run,
        batch_size=args.batch_size,
        max_retry=args.max_retry,
        delay_between_batches_seconds=args.delay,
    )
    print(
        f"[batch_orchestrator] {args.dataset_name}: "
        f"{len(summary['succeeded'])} succeeded, {len(summary['failed'])} failed, "
        f"{len(summary['empty'])} empty (this run only -- already-done symbols were skipped)"
    )