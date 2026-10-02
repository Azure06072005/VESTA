import sys
import datetime as dt
import duckdb
import pandas as pd

sys.path.insert(0, 'src')
from crawlers import market_ohlcv
from etl import db

sys.stdout.reconfigure(encoding='utf-8')

print("=== [1/2] KIỂM TRA TOÀN BỘ CỔ PHIẾU CẦN CẬP NHẬT OHLCV ĐẾN 2026-10-02 ===")

con_snap = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
vn100 = [r[0] for r in con_snap.execute("SELECT DISTINCT symbol FROM core.dim_index_constituents WHERE index_code IN ('VN100', 'VN30')").fetchall()]
active_syms = [r[0] for r in con_snap.execute("SELECT DISTINCT symbol FROM core.dim_symbol WHERE is_delisted = false").fetchall()]
con_snap.close()

target_symbols = sorted(list(set(vn100 + active_syms[:300])))
print(f"Tổng số mã mục tiêu ưu tiên: {len(target_symbols)} mã (Bao gồm VN100 + VN30 + Top Active).")

con_ohlcv = db.connect_ohlcv()
existing_dates = dict(con_ohlcv.execute("SELECT symbol, max(date) FROM core.market_ohlcv_daily GROUP BY symbol").fetchall())

today_str = dt.datetime.now().strftime("%Y-%m-%d")
start_d = "2026-09-25"
end_d = "2026-10-02"

to_crawl = []
for s in target_symbols:
    max_d = str(existing_dates.get(s, ""))
    if max_d < "2026-10-01":
        to_crawl.append(s)

print(f"Số mã cần cào bù (chưa đạt 2026-10-01/02): {len(to_crawl)} mã.")

total_bars = 0
success_cnt = 0

for i, sym in enumerate(to_crawl, 1):
    try:
        raw_df = market_ohlcv.fetch_raw(sym, start=start_d, end=end_d)
        if raw_df is not None and not raw_df.empty:
            norm_df = market_ohlcv.normalize_ohlcv(raw_df, sym)
            cnt = market_ohlcv.write_ohlcv(norm_df, con=con_ohlcv)
            total_bars += cnt
            success_cnt += 1
            max_d_crawled = norm_df['date'].max()
            if i % 10 == 0 or i == len(to_crawl):
                print(f"  [{i:03d}/{len(to_crawl)}] Đã nạp {sym}: +{cnt} nến (max date: {max_d_crawled}). Tổng nến: {total_bars:,}")
    except Exception as e:
        print(f"  [{i:03d}/{len(to_crawl)}] {sym}: Lỗi {e}")

con_ohlcv.close()
print(f"✅ Hoàn tất đồng bộ OHLCV: {success_cnt}/{len(to_crawl)} mã thành công, nạp thêm +{total_bars:,} nến vào core.market_ohlcv_daily!")
