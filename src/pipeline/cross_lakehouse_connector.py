"""src/pipeline/cross_lakehouse_connector.py

Phân hệ Kết nối Đa Hồ & Tường Lửa Chuẩn Hóa Thực Thể (F106).
(Cross-Lakehouse Connector & Universe Integrity Firewall).

Hiện thực hóa toàn bộ các khuyến nghị kỹ thuật (Recommendations) của F106:
1. "Explicit Projection & Read-Only ATTACH": Mở hồ với cấu hình DuckDB tối ưu (threads, memory limit)
   và chỉ định rõ ràng danh sách cột, ngăn ngừa bùng nổ bộ nhớ.
2. "Universe Integrity Firewall": Tự động lọc qua core.dim_symbol (1,751 active equities),
   cách ly các mã chứng quyền CW, ETF, trái phiếu hoặc mã hủy niêm yết trôi nổi.
3. "F105 News Entity Integration": Tích hợp các bảng ánh xạ 3NF core.news_entity_map và
   core.news_relevance_meta vào ma trận liên kết đa hồ.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
from typing import Dict, Generator, List, Optional, Sequence, Union

import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("cross_lakehouse_connector")

DEFAULT_SNAPSHOT_DB = "db/vesta_snapshot.duckdb"
DEFAULT_OHLCV_DB = "db/vesta_ohlcv.duckdb"
DEFAULT_NEWS_DB = "db/vesta_news.duckdb"


class CrossLakehouseError(Exception):
    """Lỗi phát sinh trong quá trình kết nối hoặc truy vấn đa hồ DuckDB."""


def get_cross_lakehouse_connection(
    snapshot_path: str = DEFAULT_SNAPSHOT_DB,
    ohlcv_path: str = DEFAULT_OHLCV_DB,
    news_path: str = DEFAULT_NEWS_DB,
    read_only: bool = True,
    threads: int = 4,
    memory_limit: str = "8GB",
) -> duckdb.DuckDBPyConnection:
    """Khởi tạo kết nối DuckDB đa hồ an toàn và hiệu năng cao với cơ chế READ_ONLY."""
    if not os.path.exists(snapshot_path):
        raise FileNotFoundError(f"Không tìm thấy lakehouse snapshot tại: {snapshot_path}")

    config = {
        "access_mode": "read_only" if read_only else "automatic",
        "threads": str(threads),
        "max_memory": memory_limit,
        "preserve_insertion_order": "false",
    }

    try:
        con = duckdb.connect(snapshot_path, read_only=read_only, config=config)
    except Exception as e:
        raise CrossLakehouseError(f"Không thể mở CSDL {snapshot_path}: {e}") from e

    # Gắn hồ OHLCV
    if os.path.exists(ohlcv_path):
        try:
            con.execute(f"ATTACH '{ohlcv_path}' AS ohlcv_db (READ_ONLY);")
            logger.debug(f"Đã gắn thành công hồ OHLCV: {ohlcv_path}")
        except Exception as e:
            logger.warning(f"Không thể gắn hồ OHLCV ({ohlcv_path}): {e}")

    # Gắn hồ News
    if os.path.exists(news_path):
        try:
            con.execute(f"ATTACH '{news_path}' AS news_db (READ_ONLY);")
            logger.debug(f"Đã gắn thành công hồ News: {news_path}")
        except Exception as e:
            logger.warning(f"Không thể gắn hồ News ({news_path}): {e}")

    return con


@contextlib.contextmanager
def open_cross_lakehouse(
    snapshot_path: str = DEFAULT_SNAPSHOT_DB,
    ohlcv_path: str = DEFAULT_OHLCV_DB,
    news_path: str = DEFAULT_NEWS_DB,
    read_only: bool = True,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Context manager đảm bảo tự động đóng kết nối và giải phóng file lock."""
    con = get_cross_lakehouse_connection(
        snapshot_path=snapshot_path,
        ohlcv_path=ohlcv_path,
        news_path=news_path,
        read_only=read_only,
    )
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception as e:
            logger.debug(f"Lỗi khi đóng kết nối DuckDB: {e}")


def execute_projected_query(
    con: duckdb.DuckDBPyConnection,
    sql_query: str,
    disallow_select_star: bool = True,
) -> pd.DataFrame:
    """Thực thi câu truy vấn với ràng buộc 'Explicit Column Projection' (Khuyến nghị F106)."""
    normalized_sql = " ".join(sql_query.strip().split()).upper()
    if disallow_select_star and "SELECT *" in normalized_sql:
        raise ValueError(
            "Vi phạm khuyến nghị F106: Không được sử dụng 'SELECT *' trên các hồ dữ liệu lớn. "
            "Vui lòng chỉ định rõ danh sách các cột cần truy vấn (Explicit Projection)."
        )
    return con.execute(sql_query).df()


def query_universe_firewall(
    con: duckdb.DuckDBPyConnection,
    target_table: str,
    columns: Sequence[str],
    symbol_col: str = "symbol",
    where_clause: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """Truy vấn dữ liệu từ bảng mục tiêu qua Tường Lửa core.dim_symbol (Universe Integrity Firewall).

    Chỉ giữ lại các bản ghi thuộc 1,751 mã cổ phiếu chính thức trên HOSE/HNX/UPCOM.
    """
    if not columns:
        raise ValueError("Phải cung cấp danh sách cột rõ ràng (columns) cho truy vấn.")

    proj_cols = ", ".join([f"t.{c.strip()}" for c in columns])
    where_str = f"AND ({where_clause})" if where_clause else ""
    order_str = f"ORDER BY {order_by}" if order_by else ""
    limit_str = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT {proj_cols}
        FROM {target_table} t
        JOIN core.dim_symbol dim ON t.{symbol_col} = dim.symbol
        WHERE 1=1 {where_str}
        {order_str}
        {limit_str};
    """
    return con.execute(query).df()


def compute_cross_lakehouse_master_matrix(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Tính toán ma trận tỷ lệ khớp nối đa hồ cập nhật mới nhất (Master Join Coverage Matrix)."""
    query = """
    WITH dim AS (
        SELECT DISTINCT symbol FROM core.dim_symbol
    ),
    dim_count AS (
        SELECT COUNT(*) AS total_dim FROM dim
    ),
    match_counts AS (
        SELECT 'Snapshots: Overview' AS dataset, COUNT(DISTINCT d.symbol) AS matched_symbols, (SELECT total_dim FROM dim_count) AS total_dim
        FROM dim d JOIN core.company_overview o ON d.symbol = o.symbol
        UNION ALL
        SELECT 'Snapshots: Shareholders', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.company_shareholders s ON d.symbol = s.symbol
        UNION ALL
        SELECT 'Snapshots: Corporate Events', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.corporate_events e ON d.symbol = e.symbol
        UNION ALL
        SELECT 'Snapshots: Financial Notes', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.financial_notes fn ON d.symbol = fn.symbol
        UNION ALL
        SELECT 'Snapshots: Fundamentals', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.fundamentals f ON d.symbol = f.symbol
        UNION ALL
        SELECT 'Snapshots: Historical Screener', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.market_screener_snapshot scr ON d.symbol = scr.symbol
        UNION ALL
        SELECT 'Snapshots: Realtime Quotes', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.realtime_quote_snapshot rq ON d.symbol = rq.symbol
        UNION ALL
        SELECT 'Snapshots: Foreign Daily Flow', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN core.market_foreign_flow_daily ff ON d.symbol = ff.symbol
        UNION ALL
        SELECT 'OHLCV: Daily Candles (1D)', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN ohlcv_db.core.market_ohlcv_daily ohl ON d.symbol = ohl.symbol
        UNION ALL
        SELECT 'OHLCV: Intraday 1M Candles', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN ohlcv_db.core.market_ohlcv_1m m1 ON d.symbol = m1.symbol
        UNION ALL
        SELECT 'News: Direct Symbol Tagged', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN news_db.core.news n ON d.symbol = n.symbol
        UNION ALL
        SELECT 'News: F105 Resolved Entities', COUNT(DISTINCT d.symbol), (SELECT total_dim FROM dim_count)
        FROM dim d JOIN news_db.core.news_entity_map nem ON d.symbol = nem.symbol
    )
    SELECT 
        dataset, 
        matched_symbols, 
        total_dim,
        ROUND(matched_symbols * 100.0 / total_dim, 2) AS match_rate_pct
    FROM match_counts
    ORDER BY match_rate_pct DESC;
    """
    return con.execute(query).df()
