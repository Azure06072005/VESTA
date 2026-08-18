"""F009 item 6 verification.

The property that matters most: an interrupted run must resume without
re-crawling already-succeeded symbols.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl import batch_orchestrator as bo  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402


def test_get_pending_symbols_returns_all_when_none_attempted(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    pending = bo.get_pending_symbols(con, "F002", ["AAA", "BBB", "CCC"])
    assert pending == ["AAA", "BBB", "CCC"]


def test_get_pending_symbols_excludes_already_succeeded(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    bo.run_batched(con, "F002", ["AAA"], lambda s: f"done-{s}")

    pending = bo.get_pending_symbols(con, "F002", ["AAA", "BBB", "CCC"])
    assert pending == ["BBB", "CCC"]


def test_get_pending_symbols_excludes_already_empty(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")

    def empty_fn(s: str) -> None:
        raise EmptyResultError("no data")

    bo.run_batched(con, "F002", ["AAA"], empty_fn)
    pending = bo.get_pending_symbols(con, "F002", ["AAA", "BBB"])
    assert pending == ["BBB"]


def test_get_pending_symbols_includes_failed_under_retry_budget(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")

    def always_fails(s: str) -> None:
        raise ConnectionError("simulated network failure")

    bo.run_batched(con, "F002", ["AAA"], always_fails)  # retry_count now 1
    pending = bo.get_pending_symbols(con, "F002", ["AAA"], max_retry=3)
    assert pending == ["AAA"]  # still under budget, eligible again


def test_get_pending_symbols_excludes_exhausted_failures(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")

    def always_fails(s: str) -> None:
        raise ConnectionError("simulated network failure")

    for _ in range(3):
        bo.run_batched(con, "F002", ["AAA"], always_fails, max_retry=3)

    pending = bo.get_pending_symbols(con, "F002", ["AAA"], max_retry=3)
    assert pending == []  # exhausted -- not retried again


def test_run_batched_resumes_without_recrawling_succeeded_symbols(tmp_path):
    # THE core property: simulate an interrupted run, then a resumed run,
    # and confirm already-succeeded symbols are never passed to crawl_fn
    # a second time.
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    calls: list[str] = []

    def crawl_fn(symbol: str) -> str:
        calls.append(symbol)
        return f"ok-{symbol}"

    first_run = bo.run_batched(con, "F002", ["AAA", "BBB"], crawl_fn, batch_size=100)
    assert set(first_run["succeeded"]) == {"AAA", "BBB"}
    assert calls == ["AAA", "BBB"]

    # "Resume" with an expanded symbol list including the same two plus a new one.
    second_run = bo.run_batched(con, "F002", ["AAA", "BBB", "CCC"], crawl_fn, batch_size=100)
    assert second_run["succeeded"] == ["CCC"]  # only the new symbol was attempted
    assert calls == ["AAA", "BBB", "CCC"]  # AAA/BBB were NOT re-crawled


def test_run_batched_respects_batch_size_boundaries(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    symbols = [f"SYM{i}" for i in range(5)]
    calls: list[str] = []

    def crawl_fn(symbol: str) -> str:
        calls.append(symbol)
        return "ok"

    outcome = bo.run_batched(con, "F002", symbols, crawl_fn, batch_size=2)
    assert len(outcome["succeeded"]) == 5
    assert calls == symbols  # all attempted, batching is transparent to the caller


def test_run_batched_records_failures_and_empties_separately(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")

    def mixed_fn(symbol: str) -> str:
        if symbol == "FAIL":
            raise ConnectionError("simulated")
        if symbol == "EMPTY":
            raise EmptyResultError("no data")
        return "ok"

    outcome = bo.run_batched(con, "F002", ["OK", "FAIL", "EMPTY"], mixed_fn)
    assert outcome["succeeded"] == ["OK"]
    assert outcome["failed"] == ["FAIL"]
    assert outcome["empty"] == ["EMPTY"]