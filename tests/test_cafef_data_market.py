"""Unit tests for CafeF Market Data Enhancer (cafef_data_market.py)."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

from src.crawlers.cafef_data_market import CafeFMarketDataEnhancer


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo DuckDB test database tạm thời với schema core.market_ohlcv_daily."""
    db_path = str(tmp_path / "test_vesta.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE core.market_ohlcv_daily (
            symbol VARCHAR NOT NULL,
            date DATE NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)
    con.close()
    return db_path


def test_parse_ohlcv_csv_standard():
    """Kiểm tra parse đúng cấu trúc CSV CafeF chuẩn."""
    csv_data = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>\n"
        "VCB,20260904,58.9,59.3,58.6,58.9,4309500\n"
        "FPT,20260904,135.0,136.5,134.2,136.0,2100500\n"
    )
    df = CafeFMarketDataEnhancer.parse_ohlcv_csv(io.StringIO(csv_data))
    assert len(df) == 2
    assert list(df["symbol"]) == ["VCB", "FPT"]
    assert df.loc[0, "date"] == dt.date(2026, 9, 4)
    assert df.loc[0, "close"] == 58.9
    assert df.loc[0, "volume"] == 4309500


def test_parse_ohlcv_csv_missing_column():
    """Kiểm tra báo lỗi khi CSV thiếu cột bắt buộc."""
    csv_data = "<Ticker>,<DTYYYYMMDD>,<Close>\nVCB,20260904,58.9\n"
    with pytest.raises(ValueError, match="CSV thiếu cột bắt buộc"):
        CafeFMarketDataEnhancer.parse_ohlcv_csv(io.StringIO(csv_data))


def test_parse_ohlcv_csv_deduplication():
    """Kiểm tra tự động khử trùng lặp khóa chính trong cùng file."""
    csv_data = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>\n"
        "VCB,20260904,58.9,59.3,58.6,58.9,4000000\n"
        "VCB,20260904,58.9,59.3,58.6,58.9,4309500\n"
    )
    df = CafeFMarketDataEnhancer.parse_ohlcv_csv(io.StringIO(csv_data))
    assert len(df) == 1
    assert df.loc[0, "volume"] == 4309500


def test_ingest_stock_ohlcv_success(temp_duckdb):
    """Kiểm tra nạp dữ liệu cổ phiếu thành công vào DuckDB."""
    enhancer = CafeFMarketDataEnhancer(duckdb_path=temp_duckdb)

    # Giả lập file zip chứa CSV
    csv_content = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>\n"
        "VCB,20260904,58.9,59.3,58.6,58.9,4309500\n"
        "HPG,20260904,25.5,25.8,25.2,25.7,15200000\n"
    ).encode("utf-8-sig")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("CafeF.HSX.04.09.2026.csv", csv_content)
    zip_buffer.seek(0)
    mock_zip = zipfile.ZipFile(zip_buffer)

    with patch.object(enhancer, "download_zip", return_value=mock_zip):
        count = enhancer.ingest_stock_ohlcv(date_str_dmy="04092026", date_str_ymd="20260904")
        assert count == 2

    # Xác thực trong DuckDB
    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT symbol, date, close, volume FROM core.market_ohlcv_daily ORDER BY symbol").fetchall()
    con.close()
    assert len(rows) == 2
    assert rows[0] == ("HPG", dt.date(2026, 9, 4), 25.7, 15200000)
    assert rows[1] == ("VCB", dt.date(2026, 9, 4), 58.9, 4309500)


def test_ingest_stock_ohlcv_symbol_filter(temp_duckdb):
    """Kiểm tra lọc mã cổ phiếu khi nạp."""
    enhancer = CafeFMarketDataEnhancer(duckdb_path=temp_duckdb)

    csv_content = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>\n"
        "VCB,20260904,58.9,59.3,58.6,58.9,4309500\n"
        "HPG,20260904,25.5,25.8,25.2,25.7,15200000\n"
    ).encode("utf-8-sig")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("CafeF.HSX.04.09.2026.csv", csv_content)
    zip_buffer.seek(0)

    with patch.object(enhancer, "download_zip", return_value=zipfile.ZipFile(zip_buffer)):
        count = enhancer.ingest_stock_ohlcv(
            date_str_dmy="04092026",
            date_str_ymd="20260904",
            symbols_filter=["VCB"]
        )
        assert count == 1

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT symbol FROM core.market_ohlcv_daily").fetchall()
    con.close()
    assert rows == [("VCB",)]


def test_ingest_market_index(temp_duckdb):
    """Kiểm tra nạp chỉ số thị trường vào core.market_index_daily."""
    enhancer = CafeFMarketDataEnhancer(duckdb_path=temp_duckdb)

    csv_content = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>\n"
        "VN-INDEX,20260904,1850.5,1855.2,1848.1,1853.08,820500000\n"
        "VN30-INDEX,20260904,1920.0,1925.4,1918.2,1922.5,310000000\n"
    ).encode("utf-8-sig")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("CafeF.INDEX.04.09.2026.csv", csv_content)
    zip_buffer.seek(0)

    with patch.object(enhancer, "download_zip", return_value=zipfile.ZipFile(zip_buffer)):
        count = enhancer.ingest_market_index(date_str_dmy="04092026", date_str_ymd="20260904")
        assert count == 2

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT index_code, date, close FROM core.market_index_daily ORDER BY index_code").fetchall()
    con.close()
    assert len(rows) == 2
    assert rows[0] == ("VN-INDEX", dt.date(2026, 9, 4), 1853.08)
    assert rows[1] == ("VN30-INDEX", dt.date(2026, 9, 4), 1922.5)
