"""Unit test cho MarketIndexCrawler (F095).

Kiểm tra:
  - Bản đồ chuẩn hóa mã chỉ số INDEX_MAPPING.
  - Khả năng nạp và upsert dữ liệu vào core.market_index_daily trên DuckDB in-memory.
  - Tính idempotent khi ghi lặp lại.
"""

from __future__ import annotations

import datetime as dt
import duckdb
import pandas as pd
import pytest

from src.crawlers.market_index_crawler import INDEX_MAPPING, MarketIndexCrawler


@pytest.fixture
def mock_duckdb(tmp_path):
    """Tạo database DuckDB tạm thời cho test."""
    db_file = str(tmp_path / "test_market_index.duckdb")
    con = duckdb.connect(db_file)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.close()
    return db_file


def test_index_mapping_coverage():
    """Kiểm tra độ phủ các chỉ số sàn và rổ nhóm chính trong INDEX_MAPPING."""
    required_indices = ["VNINDEX", "VN30", "HNXINDEX", "HNX30", "UPCOMINDEX", "VN100"]
    for idx in required_indices:
        assert idx in INDEX_MAPPING, f"Thiếu mã chỉ số bắt buộc: {idx}"


def test_save_to_duckdb_idempotency(mock_duckdb):
    """Kiểm tra khả năng lưu trữ và tính idempotent (ghi đè không nhân bản dòng)."""
    crawler = MarketIndexCrawler(duckdb_path=mock_duckdb)

    # Tạo batch dữ liệu mẫu
    sample_data = pd.DataFrame([
        {
            "index_code": "VNINDEX",
            "date": dt.date(2026, 9, 25),
            "open": 1280.5,
            "high": 1290.0,
            "low": 1275.2,
            "close": 1288.6,
            "volume": 650000000,
            "fetched_at": dt.datetime.now()
        },
        {
            "index_code": "VN30",
            "date": dt.date(2026, 9, 25),
            "open": 1330.0,
            "high": 1342.0,
            "low": 1325.0,
            "close": 1338.5,
            "volume": 250000000,
            "fetched_at": dt.datetime.now()
        }
    ])

    # Lần ghi 1
    rows_saved = crawler.save_to_duckdb(sample_data)
    assert rows_saved == 2

    con = duckdb.connect(mock_duckdb)
    cnt = con.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
    assert cnt == 2

    # Lần ghi 2 (idempotent - cùng khóa chính)
    sample_data_updated = sample_data.copy()
    sample_data_updated["close"] = [1289.0, 1339.0]
    crawler.save_to_duckdb(sample_data_updated)

    cnt_after = con.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
    assert cnt_after == 2, "Số lượng dòng không được tăng lên khi ghi đè cùng khóa chính"

    # Kiểm tra giá trị close đã được cập nhật
    close_vnindex = con.execute("SELECT close FROM core.market_index_daily WHERE index_code='VNINDEX'").fetchone()[0]
    assert close_vnindex == 1289.0
    con.close()


def test_empty_dataframe_handling(mock_duckdb):
    """Kiểm tra xử lý DataFrame rỗng không gây lỗi."""
    crawler = MarketIndexCrawler(duckdb_path=mock_duckdb)
    empty_df = pd.DataFrame()
    saved = crawler.save_to_duckdb(empty_df)
    assert saved == 0
