import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from src.crawlers.market_insights import fetch_market_screener

print("Đang gọi Vietcap IQ Screener API...")
df_screener = fetch_market_screener(page_size=2000)
print(f"✅ Thành công! Thu thập được: {len(df_screener)} mã cổ phiếu toàn thị trường.")
print(f"Số cột: {len(df_screener.columns)}")
print("Danh sách các cột:", list(df_screener.columns)[:25])
print("\nMẫu 3 mã đầu:")
print(df_screener[['symbol', 'exchange', 'price', 'pe', 'pb', 'roe', 'market_cap', 'rsi']].head(3))
