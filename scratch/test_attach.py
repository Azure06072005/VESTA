import duckdb
import os

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
for alias, filename in [
    ("market_index", "db/vesta_market_index.duckdb"),
    ("snapshot", "db/vesta_market_index.duckdb"),
    ("fundamentals", "db/vesta_fundamentals.duckdb"),
    ("events", "db/vesta_events.duckdb"),
    ("news_db", "db/vesta_news.duckdb"),
]:
    if os.path.exists(filename):
        con.execute(f"ATTACH '{filename}' AS {alias} (READ_ONLY)")

print("Attached databases successfully!")
print("dim_symbol:", con.execute("SELECT COUNT(*) FROM market_index.core.dim_symbol").fetchone()[0])
print("snapshot.dim_symbol:", con.execute("SELECT COUNT(*) FROM snapshot.core.dim_symbol").fetchone()[0])
print("balance_sheet:", con.execute("SELECT COUNT(*) FROM fundamentals.core.financial_balance_sheet_quarterly").fetchone()[0])
print("events:", con.execute("SELECT COUNT(*) FROM events.core.corporate_events").fetchone()[0])
print("news:", con.execute("SELECT COUNT(*) FROM news_db.core.news_articles").fetchone()[0])
print("ohlcv daily:", con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0])
con.close()
