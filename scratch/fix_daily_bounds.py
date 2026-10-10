import sys
import duckdb
import shutil

sys.stdout.reconfigure(encoding="utf-8")
con = duckdb.connect("db/vesta_ohlcv.duckdb")

# 1. Xóa các hàng rác 0-0-0-0 volume 0
con.execute("""
    DELETE FROM core.market_ohlcv_daily
    WHERE open <= 0 AND high <= 0 AND low <= 0 AND close <= 0;
""")

# 2. Điền giá tham chiếu cho các phiên không khớp lệnh (close = 0 nhưng open > 0)
con.execute("""
    UPDATE core.market_ohlcv_daily
    SET close = open,
        low = open
    WHERE close <= 0 AND open > 0;
""")

# 3. Với các hàng còn close <= 0, xóa bỏ
con.execute("""
    DELETE FROM core.market_ohlcv_daily
    WHERE close <= 0;
""")

# 4. Sửa hình học nến không làm tròn để giữ nguyên độ chính xác
con.execute("""
    UPDATE core.market_ohlcv_daily
    SET high = GREATEST(high, open, close),
        low = LEAST(low, open, close)
    WHERE high < open OR high < close OR low > open OR low > close;
""")

con.execute("CHECKPOINT;")
con.close()
shutil.copy2("db/vesta_ohlcv.duckdb", "db/admin/vesta_ohlcv.duckdb")
print("✓ Đã xử lý triệt để toàn bộ sai lệch hình học nến trong market_ohlcv_daily!")
