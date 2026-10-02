import duckdb
import os

print("=== CHECKING VESTA_NEWS.DUCKDB ===")
try:
    con_news = duckdb.connect('db/vesta_news.duckdb', read_only=True)
    df_stats = con_news.execute("""
        SELECT 
            source,
            count(*) as total_news,
            count(body) as has_body,
            count(CASE WHEN length(body) > 100 THEN 1 END) as long_body,
            count(symbol) as has_symbol,
            count(CASE WHEN symbol IS NULL OR symbol = '' THEN 1 END) as missing_symbol
        FROM core.news
        GROUP BY source
        ORDER BY total_news DESC
    """).df()
    print(df_stats.to_string())
    con_news.close()
    print("Successfully connected and closed vesta_news.duckdb")
except Exception as e:
    print(f"Error accessing vesta_news.duckdb: {e}")
