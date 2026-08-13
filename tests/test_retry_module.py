"""F008 verification.

Synthetic transient failure that recovers on retry; synthetic permanent-
empty response marked as such and never retried; synthetic permanent
failure hits max_retry and stops being retryable.
"""
from __future__ import annotations

import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl import retry_failed_jobs as rfj  # noqa: E402


def test_record_success_resets_retry_count(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    rfj.record_transient_failure(con, "F002", "FPT")
    rfj.record_transient_failure(con, "F002", "FPT")
    rfj.record_success(con, "F002", "FPT")

    row = con.execute(
        "SELECT status, retry_count FROM meta.crawl_progress WHERE dataset_name = 'F002' AND symbol = 'FPT'"
    ).fetchone()
    assert row == ("success", 0)


def test_transient_failure_then_recovery_via_run_job(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)

    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("simulated transient network failure")
        return "ok"

    with pytest.raises(ConnectionError):
        rfj.run_job(con, "F002", "FPT", flaky)

    row = con.execute(
        "SELECT status, retry_count FROM meta.crawl_progress WHERE dataset_name = 'F002' AND symbol = 'FPT'"
    ).fetchone()
    assert row == ("failed", 1)
    assert ("F002", "FPT", 1) in rfj.get_retryable_jobs(con, max_retry=3)

    # Second attempt (simulating a retry loop) succeeds.
    result = rfj.run_job(con, "F002", "FPT", flaky)
    assert result == "ok"
    row = con.execute(
        "SELECT status, retry_count FROM meta.crawl_progress WHERE dataset_name = 'F002' AND symbol = 'FPT'"
    ).fetchone()
    assert row == ("success", 0)


def test_permanent_empty_is_recorded_and_never_retryable(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)

    def genuinely_empty() -> None:
        raise rfj.EmptyResultError("API returned zero rows, symbol has no data for this range")

    result = rfj.run_job(con, "F006", "XYZ", genuinely_empty)
    assert result is None

    row = con.execute(
        "SELECT status, retry_count FROM meta.crawl_progress WHERE dataset_name = 'F006' AND symbol = 'XYZ'"
    ).fetchone()
    assert row == ("empty", 0)
    assert ("F006", "XYZ", 0) not in rfj.get_retryable_jobs(con, max_retry=3)


def test_permanent_failure_hits_max_retry_and_stops_being_retryable(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)

    def always_fails() -> None:
        raise TimeoutError("simulated permanent failure")

    for _ in range(3):
        with pytest.raises(TimeoutError):
            rfj.run_job(con, "F002", "BROKEN", always_fails)

    retryable = rfj.get_retryable_jobs(con, max_retry=3)
    exhausted = rfj.get_exhausted_jobs(con, max_retry=3)
    assert ("F002", "BROKEN", 3) not in retryable
    assert ("F002", "BROKEN", 3) in exhausted


def test_get_retryable_jobs_filters_by_dataset(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    rfj.record_transient_failure(con, "F002", "AAA")
    rfj.record_transient_failure(con, "F005", "BBB")

    f002_jobs = [j for j in rfj.get_retryable_jobs(con) if j[0] == "F002"]
    assert f002_jobs == [("F002", "AAA", 1)]


def test_retry_all_recovers_all_pending_jobs_for_a_dataset(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    rfj.record_transient_failure(con, "F002", "AAA")
    rfj.record_transient_failure(con, "F002", "BBB")

    def fn_factory(symbol: str):
        def fn() -> str:
            return f"crawled-{symbol}"

        return fn

    outcome = rfj.retry_all(con, "F002", fn_factory, max_retry=3)
    assert set(outcome["succeeded"]) == {"AAA", "BBB"}
    assert outcome["failed"] == []
    assert outcome["empty"] == []
    assert rfj.get_retryable_jobs(con, max_retry=3) == []


def test_retry_all_only_touches_jobs_still_under_retry_budget(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    # AAA already exhausted -- must not be retried by retry_all.
    for _ in range(3):
        with pytest.raises(TimeoutError):
            rfj.run_job(con, "F002", "AAA", lambda: (_ for _ in ()).throw(TimeoutError()))
    rfj.record_transient_failure(con, "F002", "BBB")

    calls: list[str] = []

    def fn_factory(symbol: str):
        def fn() -> str:
            calls.append(symbol)
            return "ok"

        return fn

    rfj.retry_all(con, "F002", fn_factory, max_retry=3)
    assert calls == ["BBB"]  # AAA (exhausted) was skipped