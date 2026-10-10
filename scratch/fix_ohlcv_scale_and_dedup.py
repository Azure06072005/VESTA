"""scratch/fix_ohlcv_scale_and_dedup.py

Sửa chữa quy mô giá (Price Scale Normalization) và Khử trùng lặp trên vesta_ohlcv.duckdb:
1. Chuẩn hóa 263,063 hàng nến 1m từ 2026-09-21 đến 2026-10-09 có giá > 10,000 VND về đơn vị 1,000 VND đồng nhất với 22.8M hàng lịch sử.
2. Khử trùng lặp 40,940 hàng trong core.market_ohlcv_daily (giữ lại 1 hàng duy nhất cho mỗi symbol, date).
3. Nhân bản đồng bộ sang db/admin/vesta_ohlcv.duckdb.
"""

import os
import sys
import duckdb
import shutil

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "db/vesta_ohlcv.duckdb"
ADMIN_PATH = "db/admin/vesta_ohlcv.duckdb"

print(f"Connecting to {DB_PATH} in read-write mode...")
con = duckdb.connect(DB_PATH)

# 1. Chuẩn hóa quy mô giá nến 1m
print("1. Kiểm tra và chuẩn hóa quy mô giá nến 1m...")
cnt_large = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m WHERE open > 10000").fetchone()[0]
print(f"   Số dòng nến 1m có open > 10,000 VND: {cnt_large:,}")

if cnt_large > 0:
    con.execute("""
        UPDATE core.market_ohlcv_1m
        SET open = ROUND(open / 1000.0, 3),
            high = ROUND(high / 1000.0, 3),
            low = ROUND(low / 1000.0, 3),
            close = ROUND(close / 1000.0, 3)
        WHERE open > 10000
    """)
    cnt_after = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m WHERE open > 10000").fetchone()[0]
    print(f"   ✓ Đã chuẩn hóa xong. Số dòng nến 1m còn open > 10,000: {cnt_after}")

# 2. Khử trùng lặp trong core.market_ohlcv_daily
print("2. Khử trùng lặp trong core.market_ohlcv_daily...")
total_before = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
con.execute("""
    CREATE OR REPLACE TABLE core.market_ohlcv_daily_deduped AS
    SELECT * EXCLUDE (rn)
    FROM (
        SELECT symbol, date, open, high, low, close, volume, fetched_at,
               ROW_NUMBER() OVER (PARTITION BY symbol, date ORDER BY volume DESC, fetched_at DESC) as rn
        FROM core.market_ohlcv_daily
    )
    WHERE rn = 1;
""")

con.execute("DROP TABLE core.market_ohlcv_daily;")
con.execute("ALTER TABLE core.market_ohlcv_daily_deduped RENAME TO market_ohlcv_daily;")

total_after = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
dup_groups = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT symbol, date, COUNT(*) 
        FROM core.market_ohlcv_daily 
        GROUP BY symbol, date 
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

print(f"   Tổng dòng trước: {total_before:,} -> Sau khử trùng lặp: {total_after:,} (Đã loại bỏ {total_before - total_after:,} dòng trùng lặp).")
print(f"   Số nhóm trùng lặp còn lại: {dup_groups}")

# Check checkpoint
con.execute("CHECKPOINT;")
con.close()
print("✓ Đã đóng kết nối CSDL chính an toàn.")

# 3. Đồng bộ sang db/admin/
os.makedirs("db/admin", exist_ok=True)
print(f"3. Đồng bộ sang {ADMIN_PATH}...")
shutil.copy2(DB_PATH, ADMIN_PATH)
print("✓ Đồng bộ hoàn tất!")
