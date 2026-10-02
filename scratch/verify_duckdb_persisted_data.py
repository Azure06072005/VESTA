import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_news.duckdb", read_only=True)

cnt_map = con.execute("SELECT COUNT(*) FROM core.news_entity_map;").fetchone()[0]
cnt_urls = con.execute("SELECT COUNT(DISTINCT source_url) FROM core.news_entity_map;").fetchone()[0]
cnt_symbols = con.execute("SELECT COUNT(DISTINCT symbol) FROM core.news_entity_map;").fetchone()[0]

cnt_meta = con.execute("SELECT COUNT(*) FROM core.news_relevance_meta;").fetchone()[0]

print("=" * 60)
print("XÁC NHẬN DỮ LIỆU ĐÃ LƯU TRỮ TRONG VESTA_NEWS.DUCKDB:")
print(f"- core.news_entity_map: {cnt_map:,} bản ghi")
print(f"  * Số bài báo độc nhất (URL): {cnt_urls:,}")
print(f"  * Số mã chứng khoán được kết nối: {cnt_symbols:,}")
print(f"- core.news_relevance_meta: {cnt_meta:,} bản ghi")

print("\nTop 10 Ticker được liên kết nhiều nhất:")
df_top_tickers = con.execute("""
    SELECT symbol, COUNT(*) as mention_count, COUNT(DISTINCT source_url) as article_count
    FROM core.news_entity_map
    GROUP BY symbol
    ORDER BY mention_count DESC
    LIMIT 10;
""").df()
print(df_top_tickers.to_string(index=False))

print("\nPhân bổ theo entity_type trong news_entity_map:")
df_type = con.execute("""
    SELECT entity_type, COUNT(*) as count, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
    FROM core.news_entity_map
    GROUP BY entity_type;
""").df()
print(df_type.to_string(index=False))

con.close()
