"""Unit tests for MultiSourceQueueOrchestrator."""

from __future__ import annotations

import pytest
from src.crawlers.queue_orchestrator import MultiSourceQueueOrchestrator, CrawlJob


def test_queue_initialization() -> None:
    orch = MultiSourceQueueOrchestrator(duckdb_path=":memory:")
    assert len(orch.jobs) >= 3
    job_names = [j.name for j in orch.jobs]
    assert "worldbank" in job_names
    assert "tinnhanhchungkhoan" in job_names
    assert "vasep" in job_names


def test_queue_execution_mock() -> None:
    orch = MultiSourceQueueOrchestrator(duckdb_path=":memory:", delay_between_jobs=0.01)
    # Ghi đè runner bằng mock jobs nhanh
    orch.jobs = [
        CrawlJob("mock_source_1", "Mock Job 1", lambda: 10),
        CrawlJob("mock_source_2", "Mock Job 2", lambda: 25),
    ]

    results = orch.run_all()
    assert len(results) == 2
    assert results[0].status == "success"
    assert results[0].items_ingested == 10
    assert results[1].status == "success"
    assert results[1].items_ingested == 25


def test_queue_handles_error() -> None:
    orch = MultiSourceQueueOrchestrator(duckdb_path=":memory:", delay_between_jobs=0.01)

    def failing_runner():
        raise RuntimeError("API timeout error")

    orch.jobs = [
        CrawlJob("failing_source", "Fail Job", failing_runner),
    ]
    job = orch.run_job("failing_source")
    assert job is not None
    assert job.status == "failed"
    assert "API timeout error" in (job.error or "")
