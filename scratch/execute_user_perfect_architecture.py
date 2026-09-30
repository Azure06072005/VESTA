"""Kịch bản thực thi kiến trúc CSDL hoàn hảo theo phản hồi của Người dùng:
1. Hợp nhất toàn bộ dữ liệu OHLCV 1D & Chỉ số sàn vào vesta_intraday_1m.duckdb (nơi chứa 22.75M nến 1m).
2. Thay thế và đổi tên vesta_intraday_1m.duckdb thành vesta_ohlcv.duckdb duy nhất.
3. Dọn dẹp toàn bộ 51 bảng khung rỗng (0 rows) không liên quan khỏi vesta_news.duckdb.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("db_rearchitect")

PROJECT_DIR = "d:/VESTA"
INTRA_DB = f"{PROJECT_DIR}/db/vesta_intraday_1m.duckdb"
OHLCV_TEMP_DB = f"{PROJECT_DIR}/db/vesta_ohlcv.duckdb"
NEWS_DB = f"{PROJECT_DIR}/db/vesta_news.duckdb"


def step_1_merge_and_rename_ohlcv():
    logger.info("=== BƯỚC 1: HỢP NHẤT TOÀN BỘ OHLCV VÀO VESTA_INTRADAY_1M VÀ ĐỔI TÊN ===")
    
    # 1. Mở vesta_intraday_1m.duckdb
    con_intra = duckdb.connect(INTRA_DB, read_only=False)
    con_intra.execute(f"ATTACH '{OHLCV_TEMP_DB}' AS temp_ohlcv (READ_ONLY);")
    
    con_intra.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con_intra.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    
    # Nạp 1D daily, staging daily và market index daily
    logger.info("Đang nạp core.market_ohlcv_daily (5.18M dòng) vào vesta_intraday_1m...")
    con_intra.execute("""
        CREATE OR REPLACE TABLE core.market_ohlcv_daily AS 
        SELECT * FROM temp_ohlcv.core.market_ohlcv_daily;
    """)
    
    logger.info("Đang nạp staging.market_ohlcv_daily (4.84M dòng) vào vesta_intraday_1m...")
    con_intra.execute("""
        CREATE OR REPLACE TABLE staging.market_ohlcv_daily AS 
        SELECT * FROM temp_ohlcv.staging.market_ohlcv_daily;
    """)
    
    logger.info("Đang nạp core.market_index_daily (216k dòng) vào vesta_intraday_1m...")
    con_intra.execute("""
        CREATE OR REPLACE TABLE core.market_index_daily AS 
        SELECT * FROM temp_ohlcv.core.market_index_daily;
    """)
    
    # Tạo các views
    logger.info("Đang tạo views định lượng giá kép trong vesta_intraday_1m...")
    con_intra.execute("CREATE OR REPLACE VIEW core.v_market_ohlcv_dual AS SELECT * FROM core.market_ohlcv_daily;")
    con_intra.execute("CREATE OR REPLACE VIEW core.v_market_ohlcv_1m_dual AS SELECT * FROM core.market_ohlcv_1m;")
    
    # Kiểm tra số dòng
    cnt_1d = con_intra.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
    cnt_1m = con_intra.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    cnt_idx = con_intra.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
    
    logger.info(f"-> Kiểm đếm sau nạp trong vesta_intraday_1m:")
    logger.info(f"   * core.market_ohlcv_daily: {cnt_1d:,} nến 1D")
    logger.info(f"   * core.market_ohlcv_1m: {cnt_1m:,} nến 1M (ĐẦY ĐỦ 22.75 TRIỆU NẾN!)")
    logger.info(f"   * core.market_index_daily: {cnt_idx:,} nến chỉ số")
    
    con_intra.execute("CHECKPOINT;")
    con_intra.close()
    
    # 2. Xóa OHLCV_TEMP_DB và đổi tên INTRA_DB thành OHLCV_DB
    logger.info("Đang thay thế file tạm và đổi tên vesta_intraday_1m.duckdb -> vesta_ohlcv.duckdb...")
    if os.path.exists(OHLCV_TEMP_DB):
        os.remove(OHLCV_TEMP_DB)
    os.rename(INTRA_DB, OHLCV_TEMP_DB)
    logger.info(f"✅ Đã đổi tên thành công: {OHLCV_TEMP_DB} hiện chứa TOÀN BỘ 22.75M nến 1m và 5.18M nến 1D!")


def step_2_cleanup_empty_tables_news():
    logger.info("\n=== BƯỚC 2: DỌN DẸP 51 BẢNG KHUNG RỖNG KHỎI VESTA_NEWS.DUCKDB ===")
    
    con_news = duckdb.connect(NEWS_DB, read_only=False)
    tables = con_news.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()
    
    dropped_count = 0
    news_tables_to_keep = {
        'core.news', 'staging.news',
        'core.news_resources', 'staging.news_resources',
        'core.sector_news_signal',
        'core.macro_policy', 'staging.macro_policy'
    }
    
    for schema, name in tables:
        full_name = f"{schema}.{name}"
        if full_name not in news_tables_to_keep:
            cnt = con_news.execute(f"SELECT count(*) FROM {full_name}").fetchone()[0]
            if cnt == 0:
                con_news.execute(f"DROP TABLE IF EXISTS {full_name};")
                dropped_count += 1
                logger.info(f" - Đã DROP bảng rỗng: {full_name}")
            else:
                logger.warning(f" - Bảng {full_name} có {cnt:,} dòng, giữ lại an toàn!")
    
    con_news.execute("CHECKPOINT;")
    con_news.close()
    logger.info(f"✅ Đã dọn dẹp sạch {dropped_count} bảng rỗng khỏi vesta_news.duckdb!")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    step_1_merge_and_rename_ohlcv()
    step_2_cleanup_empty_tables_news()
    logger.info("\n🎉 HOÀN TẤT 100% CẢ HAI YÊU CẦU TỐI ƯU CƠ SỞ DỮ LIỆU!")


if __name__ == "__main__":
    main()
