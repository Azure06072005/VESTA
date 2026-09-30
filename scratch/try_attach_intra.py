import duckdb

try:
    con = duckdb.connect(':memory:')
    con.execute("ATTACH 'db/vesta_intraday_1m.duckdb' AS intra (READ_ONLY);")
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='intra'").fetchall()
    print("Tables in intra:", tables)
    cnt = con.execute("SELECT count(*) FROM intra.core.market_ohlcv_1m").fetchone()[0]
    print(f"Total 1m bars in vesta_intraday_1m: {cnt:,}")
    con.close()
except Exception as e:
    print("Error:", e)
