import duckdb

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
rows = con.execute("""
    SELECT date, open, high, low, close, volume
    FROM core.market_ohlcv_daily
    WHERE symbol = 'VIC' AND date >= '2026-09-15'
    ORDER BY date ASC
""").fetchall()

print("VIC rows in core.market_ohlcv_daily:")
for r in rows:
    print(" ", r)

# Also check FPT and VCB
fpt_rows = con.execute("""
    SELECT date, open, high, low, close, volume
    FROM core.market_ohlcv_daily
    WHERE symbol = 'FPT' AND date >= '2026-09-15'
    ORDER BY date ASC
""").fetchall()
print("\nFPT rows in core.market_ohlcv_daily:")
for r in fpt_rows:
    print(" ", r)

# Check 1m data for VIC
vic_1m = con.execute("""
    SELECT time, open, high, low, close, volume
    FROM core.market_ohlcv_1m
    WHERE symbol = 'VIC'
    ORDER BY time DESC
    LIMIT 5
""").fetchall()
print("\nVIC 1m rows:")
for r in vic_1m:
    print(" ", r)
con.close()
