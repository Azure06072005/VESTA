import sys
import datetime as dt
import duckdb
import pandas as pd

sys.path.insert(0, 'src')
from crawlers import market_ohlcv
from crawlers.track_crawling_progress import VN30_SYMBOLS
from etl import db

sys.stdout.reconfigure(encoding='utf-8')

print("=== [1/3] CẬP NHẬT GIÁ NẾN 1D (2026-09-25 ĐẾN 2026-10-02) ===")

con_ohlcv = db.connect_ohlcv()

# Lấy danh mục rổ VN30
symbols = VN30_SYMBOLS.copy()
start_d = "2026-09-25"
end_d = "2026-10-02"

print(f"Bắt đầu cào nến 1D cho {len(symbols)} mã VN30 từ {start_d} đến {end_d}...")
total_bars = 0

for i, sym in enumerate(symbols, 1):
    try:
        raw_df = market_ohlcv.fetch_raw(sym, start=start_d, end=end_d)
        if raw_df is not None and not raw_df.empty:
            norm_df = market_ohlcv.normalize_ohlcv(raw_df, sym)
            cnt = market_ohlcv.write_ohlcv(norm_df, con=con_ohlcv)
            total_bars += cnt
            print(f"  [{i:02d}/{len(symbols)}] {sym}: +{cnt} nến (max_date: {norm_df['date'].max()})")
        else:
            print(f"  [{i:02d}/{len(symbols)}] {sym}: 0 nến mới.")
    except Exception as e:
        print(f"  [{i:02d}/{len(symbols)}] {sym}: Lỗi {e}")

con_ohlcv.close()
print(f"✅ Hoàn tất cập nhật nến 1D: +{total_bars} bản ghi nạp vào db/vesta_ohlcv.duckdb!")
