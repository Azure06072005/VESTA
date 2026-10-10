"""scratch/sanitize_data_quality.py

Thực hiện tự động vệ sinh và sửa chữa (Auto-Sanitization) các lỗi chất lượng dữ liệu:
1. Sửa sai lệch hình học nến trong core.market_ohlcv_daily:
   high = GREATEST(high, open, close)
   low = LEAST(low, open, close)
2. Kẹp biên độ Fear & Greed [0, 100] trong core.market_sentiment_snapshot.
3. Làm sạch 2 hàng niên độ BCTC lỗi (năm 2, 202) trong core.fundamentals.
4. Nhân bản đồng bộ sang db/admin/*.duckdb.
"""

import sys
import duckdb
import shutil

sys.stdout.reconfigure(encoding="utf-8")

print("1. Sửa chữa hình học nến trên db/vesta_ohlcv.duckdb...")
con_ohlcv = duckdb.connect("db/vesta_ohlcv.duckdb")
con_ohlcv.execute("""
    UPDATE core.market_ohlcv_daily
    SET high = ROUND(GREATEST(high, open, close), 4),
        low = ROUND(LEAST(low, open, close), 4)
    WHERE high < open OR high < close OR low > open OR low > close;
""")
con_ohlcv.execute("CHECKPOINT;")
con_ohlcv.close()
shutil.copy2("db/vesta_ohlcv.duckdb", "db/admin/vesta_ohlcv.duckdb")
print("✓ Đã sửa nến OHLCV và đồng bộ sang admin.")

print("2. Kẹp biên độ Fear & Greed trên db/vesta_market_index.duckdb...")
con_mkt = duckdb.connect("db/vesta_market_index.duckdb")
con_mkt.execute("""
    UPDATE core.market_sentiment_snapshot
    SET fear_greed_score = ROUND(GREATEST(0.0, LEAST(100.0, fear_greed_score)), 2)
    WHERE fear_greed_score < 0 OR fear_greed_score > 100;
""")
con_mkt.execute("CHECKPOINT;")
con_mkt.close()
shutil.copy2("db/vesta_market_index.duckdb", "db/admin/vesta_market_index.duckdb")
print("✓ Đã sửa Fear & Greed và đồng bộ sang admin.")

print("3. Làm sạch dữ liệu niên độ BCTC trên db/vesta_fundamentals.duckdb...")
con_fun = duckdb.connect("db/vesta_fundamentals.duckdb")
con_fun.execute("""
    DELETE FROM core.fundamentals
    WHERE period_end < '2000-01-01' OR period_end > '2026-12-31';
""")
con_fun.execute("CHECKPOINT;")
con_fun.close()
shutil.copy2("db/vesta_fundamentals.duckdb", "db/admin/vesta_fundamentals.duckdb")
print("✓ Đã sửa niên độ BCTC và đồng bộ sang admin.")
print("\n✓ Hoàn tất Auto-Sanitization thành công 100%!")
