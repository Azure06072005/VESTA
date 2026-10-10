import duckdb

con = duckdb.connect('d:/VESTA/db/vesta_market_index.duckdb', read_only=True)
print("market_breadth_series cols:")
print(con.execute("PRAGMA table_info('core.market_breadth_series')").fetchall())
print("\nmarket_sentiment_snapshot cols:")
print(con.execute("PRAGMA table_info('core.market_sentiment_snapshot')").fetchall())

r_br = con.execute("SELECT * FROM core.market_breadth_series ORDER BY trade_date DESC LIMIT 3").fetchall()
print("\nmarket_breadth_series top 3:", r_br)

# Check date column in sentiment
for col in ['date', 'trade_date', 'snapshot_date']:
    try:
        r_sent = con.execute(f"SELECT * FROM core.market_sentiment_snapshot ORDER BY {col} DESC LIMIT 3").fetchall()
        print(f"\nmarket_sentiment_snapshot top 3 using {col}:", r_sent)
        break
    except Exception:
        pass

con.close()
