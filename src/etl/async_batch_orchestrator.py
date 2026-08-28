"""Asynchronous batch orchestrator for ETL pipelines.

Similar to batch_orchestrator.py but uses concurrent.futures.ThreadPoolExecutor
to run jobs concurrently. This is useful for I/O bound crawlers (like F003) to
maximize throughput while respecting rate limits.
"""
from __future__ import annotations

import time
import sys
import pathlib
import concurrent.futures
from typing import Callable, TypeVar

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import retry_failed_jobs

T = TypeVar("T")

def run_concurrently(
    con: duckdb.DuckDBPyConnection,
    dataset_name: str,
    symbols: list[str],
    crawl_fn: Callable[[str], T],
    max_concurrency: int = 5,
    max_retry: int = 3,
    delay_between_requests_seconds: float = 0.0,
) -> dict[str, list[str]]:
    """Runs crawl_fn across multiple symbols concurrently.

    Respects the same meta.crawl_progress logic as run_batched.
    If a job fails transiently, it is left for retry_all() to handle.
    """
    outcome: dict[str, list[str]] = {"succeeded": [], "failed": [], "empty": []}

    print(f"[{dataset_name}] Starting concurrent run for {len(symbols)} symbols with max_concurrency={max_concurrency}...")

    def _worker(sym: str) -> str:
        if delay_between_requests_seconds > 0:
            time.sleep(delay_between_requests_seconds)
            
        local_con = con.cursor()
            
        def _call() -> T:
            return crawl_fn(sym, local_con)
            
        try:
            result = retry_failed_jobs.run_job(
                con=local_con,
                dataset_name=dataset_name,
                symbol=sym,
                fn=_call,
            )
            local_con.close()
            if result is None:
                return "empty"
            return "succeeded"
        except Exception as e:
            print(f"[{dataset_name}] {sym} failed: {e}")
            return "failed"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_symbol = {executor.submit(_worker, sym): sym for sym in symbols}
        
        completed = 0
        total = len(symbols)
        for future in concurrent.futures.as_completed(future_to_symbol):
            sym = future_to_symbol[future]
            completed += 1
            
            try:
                status = future.result()
                outcome[status].append(sym)
            except Exception as exc:
                print(f"[{dataset_name}] {sym} raised unexpected exception: {exc}")
                outcome["failed"].append(sym)
                
            if completed % 50 == 0 or completed == total:
                print(f"[{dataset_name}] Progress: {completed}/{total} completed (Success: {len(outcome['succeeded'])}, Empty: {len(outcome['empty'])}, Failed: {len(outcome['failed'])})")

    return outcome
