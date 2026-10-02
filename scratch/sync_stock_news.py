import sys
import duckdb
import datetime as dt

sys.path.insert(0, 'src')
from crawlers import cafef_news
from crawlers.track_crawling_progress import VN30_SYMBOLS
from etl import db

sys.stdout.reconfigure(encoding='utf-8')

print("=== [STOCK NEWS] CẬP NHẬT TIN TỨC DOANH NGHIỆP CAFEF (2026-10-02) ===")

con_news = db.connect_news()

# Lấy VN30 + các mã thanh khoản lớn
symbols = VN30_SYMBOLS.copy()
extra_liquid = ["DIG", "VND", "NVL", "PVD", "DXG", "DGC", "KBC", "VIX", "GEX", "EIB"]
for sym in extra_liquid:
    if sym not in symbols:
        symbols.append(sym)

print(f"Bắt đầu quét tin tức doanh nghiệp cho {len(symbols)} mã (chế độ Incremental Catch-up)...")

total_new_articles = 0

for i, sym in enumerate(symbols, 1):
    try:
        cnt = cafef_news.run(sym, incremental=True, max_pages=3, con=con_news)
        total_new_articles += cnt
        if cnt > 0 or i % 10 == 0 or i == len(symbols):
            print(f"  [{i:02d}/{len(symbols)}] {sym}: +{cnt} tin mới. Tổng tin: {total_new_articles}")
    except Exception as e:
        print(f"  [{i:02d}/{len(symbols)}] {sym}: Bỏ qua ({e})")

con_news.close()
print(f"✅ Hoàn tất cập nhật Tin tức cổ phiếu CafeF: +{total_new_articles} bài viết mới đã nạp vào core.news!")
