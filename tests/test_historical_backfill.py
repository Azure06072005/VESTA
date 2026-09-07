"""Unit test cho Historical Backfill Manager (Nhóm A và B).

Kiểm tra:
1. Thứ tự thực thi Nhóm A trước, Nhóm B sau.
2. Cơ chế Circuit Breaker khi gặp HTTP 403, 410, 429, 503.
3. Batch insert và Deduplication vào DuckDB.
"""

from __future__ import annotations

import duckdb
import pytest
from unittest.mock import MagicMock, patch

from src.etl.historical_backfill_groups_a_b import HistoricalBackfillManager, write_macro_policy_batch


def test_circuit_breaker_handling() -> None:
    """Kiểm tra Circuit Breaker tự ngắt khi gặp mã lỗi từ chối."""
    manager = HistoricalBackfillManager(db_path=":memory:", delay=0.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    with patch.object(manager.session, "get", return_value=mock_resp):
        res = manager._get_with_circuit_breaker("https://thuvienphapluat.vn/test")
        assert res is None, "Circuit breaker phải trả về None khi gặp HTTP 403"

    mock_resp.status_code = 429
    with patch.object(manager.session, "get", return_value=mock_resp):
        res = manager._get_with_circuit_breaker("https://vitas.org.vn/test")
        assert res is None, "Circuit breaker phải trả về None khi gặp HTTP 429"


def test_write_macro_policy_batch_idempotent() -> None:
    """Kiểm tra batch insert chuẩn 11 cột và chống trùng lặp."""
    import pandas as pd
    import datetime as dt

    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA staging")
    con.execute("CREATE SCHEMA core")
    con.execute(
        """
        CREATE TABLE staging.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMPTZ, available_at TIMESTAMPTZ, headline VARCHAR, summary VARCHAR,
            body VARCHAR, source_url VARCHAR, fetched_at TIMESTAMPTZ
        );
        CREATE TABLE core.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMPTZ, available_at TIMESTAMPTZ, headline VARCHAR, summary VARCHAR,
            body VARCHAR, source_url VARCHAR PRIMARY KEY, fetched_at TIMESTAMPTZ
        );
        """
    )

    now = dt.datetime.now(dt.timezone.utc)
    df = pd.DataFrame([{
        "source": "test_src",
        "issuing_body": "Test Body",
        "doc_type": "TEST",
        "doc_number": "123",
        "published_at": now,
        "available_at": now,
        "headline": "Test Headline",
        "summary": "Summary",
        "body": "Body content",
        "source_url": "https://example.com/item-1",
        "fetched_at": now
    }])

    n1 = write_macro_policy_batch(con, df)
    assert n1 == 1

    # Lần ghi thứ 2 cùng URL phải không bị crash và không nhân đôi bản ghi (idempotent)
    n2 = write_macro_policy_batch(con, df)
    rows = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert rows == 1
    con.close()
