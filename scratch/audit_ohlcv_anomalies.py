import duckdb

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
dup_daily = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT symbol, date, COUNT(*) 
        FROM core.market_ohlcv_daily 
        GROUP BY symbol, date 
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

total_daily = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
unique_daily = con.execute("SELECT COUNT(DISTINCT (symbol || '_' || CAST(date AS VARCHAR))) FROM core.market_ohlcv_daily").fetchone()[0]

large_1m = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m WHERE open > 10000").fetchone()[0]
total_1m = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
dup_1m = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT symbol, time, COUNT(*) 
        FROM core.market_ohlcv_1m 
        GROUP BY symbol, time 
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

print(f"Daily: Total rows = {total_daily:,}, Unique symbol_date = {unique_daily:,}, Duplicate groups = {dup_daily:,}")
print(f"1M: Total rows = {total_1m:,}, open > 10,000 = {large_1m:,}, Duplicate groups = {dup_1m:,}")

# Let's inspect which dates have open > 10000 in 1m
if large_1m > 0:
    dates_1m = con.execute("SELECT MIN(time), MAX(time) FROM core.market_ohlcv_1m WHERE open > 10000").fetchone()
    print(f"1M rows with open > 10,000 span from {dates_1m[0]} to {dates_1m[1]}")

con.close()
