"""Automated pytest test suite for market data integrity and verification."""

from __future__ import annotations

import datetime as dt
import duckdb
import pytest

from src.crawlers.verify_market_data import verify_market_data


def test_verify_market_data_execution():
    """Kiểm tra script verify_market_data chạy không lỗi và trả về dữ liệu đúng chuẩn."""
    results = verify_market_data(duckdb_path="d:/VESTA/db/vesta.duckdb")
    assert "ohlcv" in results
    assert "indices" in results
    assert "research_reports" in results
    assert "vietstock_news" in results

    # 1. OHLCV phải có trên 5 triệu bản ghi và trên 3.500 mã
    ohlcv = results["ohlcv"]
    assert ohlcv["records"] > 5_000_000
    assert ohlcv["symbols"] >= 3_900
    assert ohlcv["min_date"] == dt.date(2000, 7, 28)
    assert ohlcv["max_date"] >= dt.date(2026, 9, 1)

    # 2. Chỉ số phải có VNINDEX và HNX-INDEX
    indices = {row[0]: row[1] for row in results["indices"]}
    assert "VNINDEX" in indices
    assert "HNX-INDEX" in indices
    assert indices["VNINDEX"] > 6_000
    assert indices["HNX-INDEX"] > 5_000

    # 3. Báo cáo phân tích phải có target price và recommendation
    rep = results["research_reports"]
    assert rep[0] >= 20  # Ít nhất 20 báo cáo đã nạp
    assert rep[1] >= 10  # Số mã cổ phiếu bao phủ
    assert rep[2] > 0   # Có giá mục tiêu

    # 4. Dữ liệu khối ngoại CCNN
    assert "foreign_flow" in results
    ff = results["foreign_flow"]
    assert ff[0] > 4_000_000  # Trên 4 triệu bản ghi khối ngoại
    assert ff[1] >= 3_900    # Trên 3.900 mã cổ phiếu
    assert ff[2] <= dt.date(2002, 1, 1)


def test_ohlcv_data_types_and_no_null_keys():
    """Kiểm tra tính toàn vẹn khóa chính và không có null ở các trường định danh."""
    con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
    null_pk = con.execute("""
        SELECT count(1) FROM core.market_ohlcv_daily
        WHERE symbol IS NULL OR date IS NULL
    """).fetchone()[0]
    total = con.execute("SELECT count(1) FROM core.market_ohlcv_daily").fetchone()[0]
    valid_close = con.execute("SELECT count(1) FROM core.market_ohlcv_daily WHERE close IS NOT NULL").fetchone()[0]
    con.close()
    assert null_pk == 0
    assert (valid_close / total) > 0.9999
