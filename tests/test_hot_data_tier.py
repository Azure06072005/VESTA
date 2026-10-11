"""
Unit tests for VESTA Hot vs. Cold Data Tiering (Giải pháp 1)
===========================================================
Kiểm tra tính toàn vẹn và khả năng truy vấn của 5 CSDL Nóng (Hot Tier - db/hot/*.duckdb).
"""
import os
import sys
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from service.console_api import get_db_connection, connect_resilient_reader
from service.market_extended_api import connect_reader


@pytest.fixture(autouse=True)
def enable_hot_tier(monkeypatch):
    """Bật cờ môi trường VESTA_DATA_TIER=hot cho toàn bộ bài kiểm thử."""
    monkeypatch.setenv("VESTA_DATA_TIER", "hot")


def test_hot_db_files_exist():
    """Xác nhận 5 tệp DuckDB nóng và tệp zip lưu trữ đều tồn tại trong db/hot/."""
    hot_dir = REPO_ROOT / "db" / "hot"
    assert hot_dir.exists(), "Thư mục db/hot/ không tồn tại"

    expected_files = [
        "vesta_ohlcv.duckdb",
        "vesta_market_index.duckdb",
        "vesta_fundamentals.duckdb",
        "vesta_events.duckdb",
        "vesta_news.duckdb",
        "vesta_hot_tier.zip",
    ]
    for fn in expected_files:
        fpath = hot_dir / fn
        assert fpath.exists(), f"Thiếu tệp nóng: {fn}"
        size_mb = fpath.stat().st_size / (1024 * 1024)
        assert size_mb > 0.1, f"Tệp {fn} rỗng ({size_mb} MB)"


def test_hot_db_connection_and_attached_schemas():
    """Kiểm tra get_db_connection() gắn kết thành công tất cả 5 CSDL nóng."""
    con = get_db_connection(read_only=True)
    assert con is not None, "Không thể kết nối get_db_connection() ở chế độ Hot Tier"

    # Kiểm tra các CSDL được ATTACH
    attached = [row[1] for row in con.execute("PRAGMA database_list;").fetchall()]
    assert "market_index" in attached, "market_index chưa được ATTACH"
    assert "fundamentals" in attached, "fundamentals chưa được ATTACH"
    assert "events" in attached, "events chưa được ATTACH"
    assert "news_db" in attached, "news_db chưa được ATTACH"
    assert "ohlcv_db" in attached, "ohlcv_db chưa được ATTACH"
    con.close()


def test_hot_tier_query_ohlcv_daily_and_1m():
    """Kiểm tra nến ngày và nến 1 phút có dữ liệu chính xác trên Hot Tier."""
    con = get_db_connection(read_only=True)
    
    # Nến ngày VCB
    res_d = con.execute("""
        SELECT COUNT(*), MIN(date)::VARCHAR, MAX(date)::VARCHAR 
        FROM ohlcv_db.core.market_ohlcv_daily 
        WHERE symbol = 'VCB';
    """).fetchone()
    assert res_d[0] > 0, "Không có nến ngày VCB trên Hot Tier"
    assert res_d[1] >= "2024-01-01", f"Ngày bắt đầu nến không khớp: {res_d[1]}"

    # Nến 1 phút VCB
    res_1m = con.execute("""
        SELECT COUNT(*), MIN(time)::VARCHAR, MAX(time)::VARCHAR 
        FROM ohlcv_db.core.market_ohlcv_1m 
        WHERE symbol = 'VCB';
    """).fetchone()
    assert res_1m[0] > 0, "Không có nến 1m VCB trên Hot Tier"
    assert res_1m[1] >= "2026-09-01", f"Ngày bắt đầu nến 1m không khớp: {res_1m[1]}"
    con.close()


def test_hot_tier_query_market_index_and_dimensions():
    """Kiểm tra danh mục mã và các bảng vĩ mô/tâm lý."""
    con = get_db_connection(read_only=True)
    
    # Danh mục mã cổ phiếu
    sym_count = con.execute("SELECT COUNT(*) FROM market_index.core.dim_symbol;").fetchone()[0]
    assert sym_count > 1000, f"Số lượng mã không đủ: {sym_count}"

    # Fear & Greed / Tâm lý thị trường
    fg_count = con.execute("SELECT COUNT(*) FROM market_index.core.market_sentiment_snapshot;").fetchone()[0]
    assert fg_count > 0, "Thiếu dữ liệu Fear & Greed"

    # Dòng tiền ngoại
    ff_count = con.execute("SELECT COUNT(*) FROM market_index.core.market_foreign_flow_daily;").fetchone()[0]
    assert ff_count > 500000, f"Dòng tiền ngoại thiếu: {ff_count}"
    con.close()


def test_hot_tier_query_news_and_views():
    """Kiểm tra bảng tin tức nóng và 2 views v_stock_news, v_macro_news."""
    con = get_db_connection(read_only=True)
    
    news_count = con.execute("SELECT COUNT(*) FROM news_db.core.news;").fetchone()[0]
    assert news_count > 10000, f"Tin tức nóng quá ít: {news_count}"

    stock_news = con.execute("SELECT COUNT(*) FROM news_db.core.v_stock_news;").fetchone()[0]
    assert stock_news > 0, "View v_stock_news rỗng"

    macro_news = con.execute("SELECT COUNT(*) FROM news_db.core.v_macro_news;").fetchone()[0]
    assert macro_news > 0, "View v_macro_news rỗng"
    con.close()


def test_hot_tier_connect_resilient_and_market_extended():
    """Kiểm tra connect_resilient_reader và connect_reader hoạt động trơn tru với Hot Tier."""
    con1 = connect_resilient_reader(str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb"))
    assert con1 is not None, "connect_resilient_reader thất bại với Hot Tier"
    con1.close()

    con2 = connect_reader("vesta_news.duckdb")
    assert con2 is not None, "connect_reader thất bại với Hot Tier"
    con2.close()
