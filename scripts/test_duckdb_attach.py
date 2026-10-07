import duckdb

con = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
try:
    con.execute("ATTACH 'db/vesta_snapshot.duckdb' AS snapshot (READ_ONLY)")
    con.execute("ATTACH 'db/vesta_news.duckdb' AS news_db (READ_ONLY)")
    print("Attached successfully!")
    print("Querying core.dim_symbol via snapshot:", con.execute("SELECT COUNT(*) FROM snapshot.core.dim_symbol").fetchone()[0])
    print("Querying core.news via news_db:", con.execute("SELECT COUNT(*) FROM news_db.core.news").fetchone()[0])
except Exception as e:
    print("Attach test error:", e)
finally:
    con.close()
