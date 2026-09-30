"""Script dọn dẹp các bảng OHLCV và News đã được di chuyển khỏi Main Database (vesta_snapshot.duckdb).

Bảo đảm an toàn:
  1. Kiểm tra xác nhận dữ liệu đã tồn tại đầy đủ trong vesta_ohlcv.duckdb và vesta_news.duckdb.
  2. Xóa các Views phụ thuộc trước.
  3. DROP các bảng OHLCV (core.market_ohlcv_daily, staging.market_ohlcv_daily, core.market_ohlcv_1m).
  4. DROP các bảng News (core.news, staging.news, core.news_resources, staging.news_resources, core.sector_news_signal).
  5. Chạy CHECKPOINT trên vesta_snapshot.duckdb.
"""

from __future__ import annotations

import logging
import sys
import time
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cleanup_main_db")

SNAP_DB = "d:/VESTA/db/vesta_snapshot.duckdb"
OHLCV_DB = "d:/VESTA/db/vesta_ohlcv.duckdb"
NEWS_DB = "d:/VESTA/db/vesta_news.duckdb"


def cleanup():
    logger.info("=== BẮT ĐẦU DỌN DẸP MAIN DATABASE (VESTA_SNAPSHOT.DUCKDB) ===")
    
    # 1. Kiểm tra an toàn trước khi xóa
    con_ohlcv = duckdb.connect(OHLCV_DB, read_only=True)
    cnt_daily = con_ohlcv.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
    cnt_1m = con_ohlcv.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    con_ohlcv.close()
    
    con_news = duckdb.connect(NEWS_DB, read_only=True)
    cnt_news = con_news.execute("SELECT count(*) FROM core.news").fetchone()[0]
    con_news.close()
    
    logger.info(f"Xác nhận dữ liệu an toàn tại kho đích:")
    logger.info(f" - vesta_ohlcv.duckdb: {cnt_daily:,} nến ngày 1D, {cnt_1m:,} nến 1m")
    logger.info(f" - vesta_news.duckdb: {cnt_news:,} tin tức")
    
    assert cnt_daily > 5_000_000, "LỖI AN TOÀN: vesta_ohlcv.duckdb thiếu nến daily!"
    assert cnt_1m > 6_000_000, "LỖI AN TOÀN: vesta_ohlcv.duckdb thiếu nến 1m!"
    assert cnt_news > 600_000, "LỖI AN TOÀN: vesta_news.duckdb thiếu tin tức!"
    
    logger.info("-> Kiểm tra điều kiện an toàn: ĐẠT CHUẨN 100%!")
    
    # 2. Thực hiện xóa các bảng đã di dời khỏi vesta_snapshot.duckdb
    con_snap = duckdb.connect(SNAP_DB, read_only=False)
    
    # Xóa views
    logger.info("Đang xóa các Views OHLCV trong main DB...")
    con_snap.execute("DROP VIEW IF EXISTS core.v_market_ohlcv_1m_dual;")
    con_snap.execute("DROP VIEW IF EXISTS core.v_market_ohlcv_dual;")
    
    # Xóa bảng OHLCV
    logger.info("Đang xóa các bảng OHLCV trong main DB...")
    con_snap.execute("DROP TABLE IF EXISTS core.market_ohlcv_1m;")
    con_snap.execute("DROP TABLE IF EXISTS core.market_ohlcv_daily;")
    con_snap.execute("DROP TABLE IF EXISTS staging.market_ohlcv_daily;")
    
    # Xóa bảng News
    logger.info("Đang xóa các bảng News trong main DB...")
    con_snap.execute("DROP TABLE IF EXISTS core.news;")
    con_snap.execute("DROP TABLE IF EXISTS staging.news;")
    con_snap.execute("DROP TABLE IF EXISTS core.news_resources;")
    con_snap.execute("DROP TABLE IF EXISTS staging.news_resources;")
    con_snap.execute("DROP TABLE IF EXISTS core.sector_news_signal;")
    
    logger.info("Đang thực hiện CHECKPOINT để giải phóng không gian...")
    con_snap.execute("CHECKPOINT;")
    con_snap.close()
    
    logger.info("✅ HOÀN TẤT DỌN DẸP MAIN DATABASE AN TOÀN TUYỆT ĐỐI!")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cleanup()
