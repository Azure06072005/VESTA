"""tests/test_cross_lakehouse_mapping.py

Bộ kiểm thử đơn vị cho phân hệ Kết nối Đa Hồ & Tường Lửa Chuẩn Hóa Thực Thể (F106).
(Unit tests for Cross-Lakehouse Connector & Universe Integrity Firewall).
"""
import sys
from pathlib import Path
import duckdb
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.cross_lakehouse_connector import (
    compute_cross_lakehouse_master_matrix,
    execute_projected_query,
    get_cross_lakehouse_connection,
    open_cross_lakehouse,
    query_universe_firewall,
)


@pytest.fixture
def mock_cross_lakehouse(tmp_path):
    """Tạo bộ 3 CSDL DuckDB giả lập để kiểm thử độc lập."""
    snap_path = str(tmp_path / "mock_snapshot.duckdb")
    ohlcv_path = str(tmp_path / "mock_ohlcv.duckdb")
    news_path = str(tmp_path / "mock_news.duckdb")

    # 1. Snapshot DB
    con_s = duckdb.connect(snap_path)
    con_s.execute("CREATE SCHEMA core;")
    con_s.execute("""
        CREATE TABLE core.dim_symbol (
            symbol VARCHAR PRIMARY KEY,
            organ_name VARCHAR,
            exchange VARCHAR
        );
        INSERT INTO core.dim_symbol VALUES 
        ('FPT', 'Tập đoàn FPT', 'HOSE'),
        ('VIC', 'Tập đoàn Vingroup', 'HOSE'),
        ('HPG', 'Tập đoàn Hòa Phát', 'HOSE'),
        ('VNM', 'Sữa Việt Nam', 'HOSE');

        CREATE TABLE core.company_overview (
            symbol VARCHAR PRIMARY KEY,
            ceo_name VARCHAR
        );
        INSERT INTO core.company_overview VALUES 
        ('FPT', 'Nguyễn Văn Khoa'),
        ('VIC', 'Nguyễn Việt Quang');

        CREATE TABLE core.company_shareholders (
            symbol VARCHAR,
            shareholder_name VARCHAR
        );
        INSERT INTO core.company_shareholders VALUES 
        ('FPT', 'Trương Gia Bình');

        CREATE TABLE core.corporate_events (symbol VARCHAR, event_desc VARCHAR);
        INSERT INTO core.corporate_events VALUES ('FPT', 'Chia cổ tức');

        CREATE TABLE core.financial_notes (symbol VARCHAR, note_title VARCHAR);
        INSERT INTO core.financial_notes VALUES ('FPT', 'Thuyết minh số 1');

        CREATE TABLE core.fundamentals (symbol VARCHAR, period_end DATE);
        INSERT INTO core.fundamentals VALUES ('FPT', '2024-12-31');

        CREATE TABLE core.market_screener_snapshot (symbol VARCHAR, pe_ratio DOUBLE);
        INSERT INTO core.market_screener_snapshot VALUES ('FPT', 20.5);

        CREATE TABLE core.realtime_quote_snapshot (symbol VARCHAR, price DOUBLE);
        INSERT INTO core.realtime_quote_snapshot VALUES ('FPT', 130000.0);

        CREATE TABLE core.market_foreign_flow_daily (symbol VARCHAR, buy_vol BIGINT);
        INSERT INTO core.market_foreign_flow_daily VALUES 
        ('FPT', 500000),
        ('ORPHAN_CODE', 100000); -- Mã ngoài universe
    """)
    con_s.close()

    # 2. OHLCV DB
    con_o = duckdb.connect(ohlcv_path)
    con_o.execute("CREATE SCHEMA core;")
    con_o.execute("""
        CREATE TABLE core.market_ohlcv_daily (
            symbol VARCHAR,
            date DATE,
            close DOUBLE
        );
        INSERT INTO core.market_ohlcv_daily VALUES 
        ('FPT', '2024-01-02', 95000.0),
        ('VIC', '2024-01-02', 45000.0),
        ('UNKNOWN_DELISTED', '2010-01-02', 10000.0);

        CREATE TABLE core.market_ohlcv_1m (
            symbol VARCHAR,
            time TIMESTAMP,
            close DOUBLE
        );
        INSERT INTO core.market_ohlcv_1m VALUES ('FPT', '2024-01-02 09:15:00', 95200.0);
    """)
    con_o.close()

    # 3. News DB
    con_n = duckdb.connect(news_path)
    con_n.execute("CREATE SCHEMA core;")
    con_n.execute("""
        CREATE TABLE core.news (
            source_url VARCHAR PRIMARY KEY,
            symbol VARCHAR,
            headline VARCHAR
        );
        INSERT INTO core.news VALUES 
        ('https://news.vn/1', 'FPT', 'FPT tăng trưởng lợi nhuận 20%'),
        ('https://news.vn/2', NULL, 'Ngân hàng Nhà nước hạ lãi suất điều hành');

        CREATE TABLE core.news_entity_map (
            source_url VARCHAR,
            symbol VARCHAR,
            entity_type VARCHAR,
            entity_name VARCHAR
        );
        INSERT INTO core.news_entity_map VALUES 
        ('https://news.vn/2', 'VCB', 'EXECUTIVE', 'Nguyễn Thanh Tùng');
    """)
    con_n.close()

    return snap_path, ohlcv_path, news_path


def test_open_cross_lakehouse_connection(mock_cross_lakehouse):
    snap, ohlcv, news = mock_cross_lakehouse
    with open_cross_lakehouse(snap, ohlcv, news, read_only=True) as con:
        # Kiểm tra truy vấn bảng từ cả 3 hồ đồng thời
        cnt_dim = con.execute("SELECT count(*) FROM core.dim_symbol").fetchone()[0]
        cnt_ohlcv = con.execute("SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily").fetchone()[0]
        cnt_news = con.execute("SELECT count(*) FROM news_db.core.news").fetchone()[0]

        assert cnt_dim == 4
        assert cnt_ohlcv == 3
        assert cnt_news == 2


def test_execute_projected_query_disallows_select_star(mock_cross_lakehouse):
    snap, ohlcv, news = mock_cross_lakehouse
    with open_cross_lakehouse(snap, ohlcv, news, read_only=True) as con:
        # Truy vấn có SELECT * phải bị chặn theo Recommendation F106
        with pytest.raises(ValueError, match="Không được sử dụng 'SELECT \\*'"):
            execute_projected_query(con, "SELECT * FROM core.dim_symbol")

        # Truy vấn có projection rõ ràng phải chạy thành công
        df = execute_projected_query(con, "SELECT symbol, exchange FROM core.dim_symbol")
        assert len(df) == 4
        assert list(df.columns) == ["symbol", "exchange"]


def test_query_universe_firewall(mock_cross_lakehouse):
    snap, ohlcv, news = mock_cross_lakehouse
    with open_cross_lakehouse(snap, ohlcv, news, read_only=True) as con:
        # Bảng market_foreign_flow_daily chứa cả FPT (hợp lệ) và ORPHAN_CODE (ngoài universe)
        df_firewall = query_universe_firewall(
            con,
            target_table="core.market_foreign_flow_daily",
            columns=["symbol", "buy_vol"],
            symbol_col="symbol",
        )

        symbols = set(df_firewall["symbol"])
        assert "FPT" in symbols
        assert "ORPHAN_CODE" not in symbols, "Tường lửa universe phải loại bỏ ORPHAN_CODE!"
        assert len(df_firewall) == 1


def test_compute_cross_lakehouse_master_matrix(mock_cross_lakehouse):
    snap, ohlcv, news = mock_cross_lakehouse
    with open_cross_lakehouse(snap, ohlcv, news, read_only=True) as con:
        df_matrix = compute_cross_lakehouse_master_matrix(con)

        assert isinstance(df_matrix, pd.DataFrame)
        assert "dataset" in df_matrix.columns
        assert "match_rate_pct" in df_matrix.columns

        # Phải chứa cả phân lớp F105
        datasets = set(df_matrix["dataset"])
        assert "News: F105 Resolved Entities" in datasets
        assert "OHLCV: Daily Candles (1D)" in datasets
        assert "Snapshots: Overview" in datasets
