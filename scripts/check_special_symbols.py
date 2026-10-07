import duckdb

con = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
cols = con.execute("PRAGMA table_info('core.market_index_daily')").fetchall()
print("Columns of core.market_index_daily:")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

sample = con.execute("SELECT * FROM core.market_index_daily LIMIT 2").fetchall()
print("\nSample rows:")
for s in sample:
    print(s)

con.close()
