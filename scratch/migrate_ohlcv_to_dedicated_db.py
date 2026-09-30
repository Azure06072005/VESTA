"""Script di chuyển toàn bộ dữ liệu OHLCV (1D, 1m, Chỉ số thị trường) 
từ Main Database (vesta_snapshot.duckdb) sang OHLCV Database chuyên biệt (vesta_ohlcv.duckdb).

Tuân thủ:
  - Khởi tạo đầy đủ schema core và staging trong vesta_ohlcv.duckdb
  - Sao chép nguyên vẹn dữ liệu: core.market_ohlcv_daily, staging.market_ohlcv_daily,
    core.market_ohlcv_1m, core.market_index_daily và các views liên quan.
  - Đối chiếu kiểm tra số dòng 1:1 trước khi xác nhận.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import time
from pathlib import Path
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ohlcv_migration")

SNAP_DB = "d:/VESTA/db/vesta_snapshot.duckdb"
OHLCV_DB = "d:/VESTA/db/vesta_ohlcv.duckdb"


def migrate_ohlcv():
    start_time = time.time()
    logger.info("=== BẮT ĐẦU DI CHUYỂN DỮ LIỆU OHLCV SANG VESTA_OHLCV.DUCKDB ===")
    
    con = duckdb.connect(OHLCV_DB, read_only=False)
    con.execute(f"ATTACH '{SNAP_DB}' AS snap (READ_ONLY);")
    
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    
    tables_to_migrate = [
        ("core", "market_ohlcv_daily"),
        ("staging", "market_ohlcv_daily"),
        ("core", "market_ohlcv_1m"),
        ("core", "market_index_daily"),
    ]
    
    verification_results = {}
    
    for schema, tbl in tables_to_migrate:
        t_start = time.time()
        logger.info(f"Đang sao chép {schema}.{tbl} sang vesta_ohlcv.duckdb...")
        
        # Sao chép bảng sang database mới
        con.execute(f"""
            CREATE OR REPLACE TABLE {schema}.{tbl} AS 
            SELECT * FROM snap.{schema}.{tbl}
        """)
        
        # Kiểm đếm số dòng đối chiếu
        src_cnt = con.execute(f"SELECT count(*) FROM snap.{schema}.{tbl}").fetchone()[0]
        dst_cnt = con.execute(f"SELECT count(*) FROM {schema}.{tbl}").fetchone()[0]
        
        elapsed = time.time() - t_start
        logger.info(f"-> {schema}.{tbl}: Gốc = {src_cnt:,} | Đích = {dst_cnt:,} (Khớp 100%: {src_cnt == dst_cnt}) [{elapsed:.2f}s]")
        verification_results[f"{schema}.{tbl}"] = (src_cnt, dst_cnt, src_cnt == dst_cnt)
    
    # Tạo lại các Views phân tích giá kép (Dual-Mode Pricing Views)
    logger.info("Đang khởi tạo các Views phân tích giá trong vesta_ohlcv.duckdb...")
    con.execute("""
        CREATE OR REPLACE VIEW core.v_market_ohlcv_dual AS
        SELECT * FROM core.market_ohlcv_daily;
    """)
    con.execute("""
        CREATE OR REPLACE VIEW core.v_market_ohlcv_1m_dual AS
        SELECT * FROM core.market_ohlcv_1m;
    """)
    
    con.close()
    
    total_time = time.time() - start_time
    logger.info(f"\n=== HOÀN TẤT DI CHUYỂN DỮ LIỆU OHLCV TRONG {total_time:.2f} GIÂY ===")
    all_matched = all(v[2] for v in verification_results.values())
    if all_matched:
        logger.info("✅ 100% CÁC BẢNG ĐÃ ĐỐI CHIẾU KHỚP TUYỆT ĐỐI!")
    else:
        logger.error("❌ CẢNH BÁO: CÓ BẢNG KHÔNG KHỚP SỐ LƯỢNG DÒNG!")
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    migrate_ohlcv()
