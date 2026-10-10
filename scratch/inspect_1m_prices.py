import duckdb

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
row_old = con.execute("SELECT time, open, high, low, close FROM core.market_ohlcv_1m WHERE symbol = 'VIC' ORDER BY time ASC LIMIT 3").fetchall()
row_sep18 = con.execute("SELECT time, open, high, low, close FROM core.market_ohlcv_1m WHERE symbol = 'VIC' AND time >= '2026-09-18' ORDER BY time ASC LIMIT 3").fetchall()
row_sep21 = con.execute("SELECT time, open, high, low, close FROM core.market_ohlcv_1m WHERE symbol = 'VIC' AND time >= '2026-09-21' ORDER BY time ASC LIMIT 3").fetchall()

print("OLD 1m bars:")
for r in row_old:
    print(" ", r)

print("\nSEP 18 1m bars:")
for r in row_sep18:
    print(" ", r)

print("\nSEP 21 1m bars:")
for r in row_sep21:
    print(" ", r)
con.close()
