import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

print("=== KIỂM TRA NGÀY MỚI NHẤT (MAX DATE) CỦA CÁC HỒ DỮ LIỆU ===")

# 1. OHLCV
con_ohlcv = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
max_1d = con_ohlcv.execute("SELECT MAX(date) FROM core.market_ohlcv_daily").fetchone()[0]
cnt_1d = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
max_1m = con_ohlcv.execute("SELECT MAX(time) FROM core.market_ohlcv_1m").fetchone()[0]
cnt_1m = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
print(f"1. OHLCV Lakehouse (db/vesta_ohlcv.duckdb):")
print(f"   • Nến ngày 1D: Max Date = {max_1d} ({cnt_1d:,} dòng)")
print(f"   • Nến phút 1M: Max Time = {max_1m} ({cnt_1m:,} dòng)")
hpg_sample = con_ohlcv.execute("SELECT symbol, date, open, high, low, close, volume FROM core.market_ohlcv_daily WHERE symbol='HPG' ORDER BY date DESC LIMIT 3").df()
print("   • Mẫu HPG mới nhất:\n", hpg_sample.to_string(index=False))
con_ohlcv.close()

# 2. News
con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
max_news = con_news.execute("SELECT MAX(published_at) FROM core.news").fetchone()[0]
cnt_news = con_news.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
print(f"\n2. News Lakehouse (db/vesta_news.duckdb):")
print(f"   • Tin tức: Max Published = {max_news} ({cnt_news:,} bài báo)")
con_news.close()

# 3. Snapshots
con_snap = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
max_scr = con_snap.execute("SELECT MAX(snapshot_date) FROM core.market_screener_snapshot").fetchone()[0]
cnt_scr = con_snap.execute("SELECT COUNT(*) FROM core.market_screener_snapshot").fetchone()[0]
max_quote = con_snap.execute("SELECT MAX(snapshot_at) FROM core.realtime_quote_snapshot").fetchone()[0]
cnt_quote = con_snap.execute("SELECT COUNT(*) FROM core.realtime_quote_snapshot").fetchone()[0]
max_ob = con_snap.execute("SELECT MAX(timestamp) FROM core.order_book_depth").fetchone()[0]
cnt_ob = con_snap.execute("SELECT COUNT(*) FROM core.order_book_depth").fetchone()[0]
max_trades = con_snap.execute("SELECT MAX(time) FROM core.intraday_trades").fetchone()[0]
cnt_trades = con_snap.execute("SELECT COUNT(*) FROM core.intraday_trades").fetchone()[0]
print(f"\n3. Snapshots Lakehouse (db/vesta_snapshot.duckdb):")
print(f"   • Deep Screener: Max Date = {max_scr} ({cnt_scr:,} dòng)")
print(f"   • Bảng giá Snapshot: Max Time = {max_quote} ({cnt_quote:,} dòng)")
print(f"   • Sổ lệnh Level 2: Max Time = {max_ob} ({cnt_ob:,} dòng)")
print(f"   • Khớp lệnh Intraday: Max Time = {max_trades} ({cnt_trades:,} dòng)")
con_snap.close()
