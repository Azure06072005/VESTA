"""Unit tests for CafeF Finance Enhancer (cafef_finance_enhancer.py)."""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from src.crawlers.cafef_finance_enhancer import CafeFFinanceEnhancer


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.fundamentals và staging.fundamentals."""
    db_path = str(tmp_path / "test_fundamentals.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    con.execute("""
        CREATE TABLE core.fundamentals (
            symbol VARCHAR NOT NULL,
            report_type VARCHAR NOT NULL,
            period_end DATE NOT NULL,
            available_at TIMESTAMP NOT NULL,
            data_json JSON NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, report_type, period_end, fetched_at)
        );
    """)
    con.execute("""
        CREATE TABLE staging.fundamentals (
            symbol VARCHAR NOT NULL,
            report_type VARCHAR NOT NULL,
            period_end DATE NOT NULL,
            available_at TIMESTAMP NOT NULL,
            data_json JSON NOT NULL,
            fetched_at TIMESTAMP NOT NULL
        );
    """)
    con.close()
    return db_path


def test_parse_quarter_period():
    """Kiểm tra phân tích cú pháp chuỗi kỳ quý sang ngày kết thúc chuẩn xác."""
    assert CafeFFinanceEnhancer._parse_quarter_period("Q1/2026") == dt.date(2026, 3, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q2/2026") == dt.date(2026, 6, 30)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q3/2025") == dt.date(2025, 9, 30)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q4/2025") == dt.date(2025, 12, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("2025") == dt.date(2025, 12, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("Invalid") is None


def test_parse_and_normalize():
    """Kiểm tra bóc tách cấu trúc templace và data theo quý của CafeF API."""
    raw_val = {
        "templace": [
            {"code": "1", "name": "TÀI SẢN NGẮN HẠN"},
            {"code": "2", "name": "Tiền và tương đương tiền"},
        ],
        "data": [
            {
                "symbol": "VCB",
                "year": 2026,
                "quater": 2,
                "time": "Q2-2026",
                "data": [
                    {"code": "1", "value": 1000000.0},
                    {"code": "2", "value": 200000.0},
                ]
            },
            {
                "symbol": "VCB",
                "year": 2026,
                "quater": 1,
                "time": "Q1-2026",
                "data": [
                    {"code": "1", "value": 950000.0},
                    {"code": "2", "value": 180000.0},
                ]
            }
        ]
    }
    enhancer = CafeFFinanceEnhancer(duckdb_path=":memory:")
    records = enhancer.parse_and_normalize("VCB", "balance_sheet", raw_val)

    assert len(records) == 2
    rec_q2 = next(r for r in records if r["period_end"] == dt.date(2026, 6, 30))
    metrics_q2 = json.loads(rec_q2["data_json"])
    assert metrics_q2["TÀI SẢN NGẮN HẠN"] == 1000000.0
    assert metrics_q2["Tiền và tương đương tiền"] == 200000.0

    # Kiểm tra tính tuân thủ Zero Look-Ahead Bias: available_at = period_end + 30 days
    assert rec_q2["available_at"].date() == dt.date(2026, 7, 30)


def test_save_batch(temp_duckdb):
    """Kiểm tra lưu trữ vào DuckDB và cơ chế ON CONFLICT."""
    enhancer = CafeFFinanceEnhancer(duckdb_path=temp_duckdb)
    now = dt.datetime.now(dt.timezone.utc)
    records = [
        {
            "symbol": "FPT",
            "report_type": "income_statement",
            "period_end": dt.date(2026, 6, 30),
            "available_at": dt.datetime(2026, 7, 30, 0, 0, tzinfo=dt.timezone.utc),
            "data_json": json.dumps({"Doanh thu thuần": 5000000.0}),
            "fetched_at": now,
        }
    ]
    saved = enhancer.save_batch(records)
    assert saved == 1

    con = duckdb.connect(temp_duckdb)
    row = con.execute("SELECT symbol, report_type, data_json FROM core.fundamentals").fetchone()
    con.close()

    assert row[0] == "FPT"
    assert row[1] == "income_statement"
    assert "5000000.0" in row[2]
