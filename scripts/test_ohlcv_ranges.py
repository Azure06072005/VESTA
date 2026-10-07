import duckdb

OHLCV_DB = "db/vesta_ohlcv.duckdb"

print("1. Testing 5Y daily bars for FPT:")
with duckdb.connect(OHLCV_DB, read_only=True) as con:
    rows = con.execute("""
        SELECT date, open, high, low, close, volume
        FROM core.market_ohlcv_daily
        WHERE symbol = 'FPT'
        ORDER BY date DESC
        LIMIT 1260
    """).fetchall()
    print(f"   FPT 5Y daily bars count: {len(rows)} (earliest: {rows[-1][0]}, latest: {rows[0][0]})")

print("\n2. Testing 1m intraday bars for FPT:")
with duckdb.connect(OHLCV_DB, read_only=True) as con:
    rows_1m = con.execute("""
        SELECT time, open, high, low, close, volume
        FROM core.market_ohlcv_1m
        WHERE symbol = 'FPT'
        ORDER BY time DESC
        LIMIT 200
    """).fetchall()
    print(f"   FPT 1m bars count: {len(rows_1m)} (sample: {rows_1m[0] if rows_1m else 'None'})")

print("\n3. Testing Index VNINDEX 5Y bars:")
with duckdb.connect(OHLCV_DB, read_only=True) as con:
    rows_idx = con.execute("""
        SELECT date, open, high, low, close, volume
        FROM core.market_index_daily
        WHERE index_code = 'VNINDEX'
        ORDER BY date DESC
        LIMIT 1260
    """).fetchall()
    print(f"   VNINDEX 5Y bars count: {len(rows_idx)} (earliest: {rows_idx[-1][0]}, latest: {rows_idx[0][0]})")
