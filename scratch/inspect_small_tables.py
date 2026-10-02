import duckdb

con = duckdb.connect("db/vesta_backup.duckdb", read_only=True)

print("=== SAMPLE: core.foreign_flow_intraday ===")
try:
    print(con.execute("SELECT * FROM core.foreign_flow_intraday").df())
except Exception as e:
    print(e)

print("\n=== SAMPLE: core.foreign_ownership_room ===")
try:
    print(con.execute("SELECT * FROM core.foreign_ownership_room").df())
except Exception as e:
    print(e)

print("\n=== SAMPLE: core.market_sentiment_snapshot ===")
try:
    print(con.execute("SELECT * FROM core.market_sentiment_snapshot").df())
except Exception as e:
    print(e)

print("\n=== SAMPLE: core.order_book_depth (First 3 rows & summary) ===")
try:
    df_ob = con.execute("SELECT * FROM core.order_book_depth LIMIT 3").df()
    print(df_ob)
    print("Unique symbols in order_book_depth:", con.execute("SELECT count(DISTINCT symbol), min(fetched_at), max(fetched_at) FROM core.order_book_depth").df())
except Exception as e:
    print(e)

con.close()
