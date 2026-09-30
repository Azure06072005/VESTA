import duckdb

try:
    c = duckdb.connect('db/vesta_intraday_1m.duckdb', read_only=True)
    res = c.execute("SELECT min(time), max(time), count(*) FROM core.market_ohlcv_1m WHERE symbol='FPT'").fetchone()
    print(f"Intraday DB FPT: Start={res[0]}, End={res[1]}, Rows={res[2]:,}")
    c.close()
except Exception as e:
    print(f"Error accessing intraday 1m db: {e}")
