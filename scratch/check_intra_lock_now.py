import duckdb

try:
    con = duckdb.connect('db/vesta_intraday_1m.duckdb', read_only=True)
    print("vesta_intraday_1m.duckdb open read_only: SUCCESS!")
    cnt = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    print(f"Total 1m bars in vesta_intraday_1m: {cnt:,}")
    con.close()
except Exception as e:
    print("Still locked:", e)
