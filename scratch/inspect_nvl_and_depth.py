import duckdb
import sys

sys.stdout.reconfigure(encoding="utf-8")

con = None
for p in ["db/admin/vesta_ohlcv.duckdb", "db/vesta_ohlcv.duckdb"]:
    try:
        con = duckdb.connect(p, read_only=True, config={"access_mode": "read_only"})
        print(f"Connected to {p}")
        break
    except Exception as e:
        continue

if con is None:
    print("Cannot connect to any duckdb copy!")
    sys.exit(1)

# 1. Check NVL in market_ohlcv_daily
nvl_daily = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM core.market_ohlcv_daily WHERE symbol = 'NVL'").fetchone()
print(f"NVL in core.market_ohlcv_daily: count={nvl_daily[0]}, min={nvl_daily[1]}, max={nvl_daily[2]}")

# 2. Check NVL in market_ohlcv_1m
nvl_1m = con.execute("SELECT COUNT(*), MIN(time), MAX(time) FROM core.market_ohlcv_1m WHERE symbol = 'NVL'").fetchone()
print(f"NVL in core.market_ohlcv_1m: count={nvl_1m[0]}, min={nvl_1m[1]}, max={nvl_1m[2]}")

# 3. Check distribution of row counts across symbols in market_ohlcv_daily
symbol_stats = con.execute("""
    SELECT symbol, COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date,
           ROUND(date_diff('day', MIN(date), MAX(date)) / 365.25, 1) as years_span
    FROM core.market_ohlcv_daily
    GROUP BY symbol
""").fetchall()

total_symbols = len(symbol_stats)
print(f"\nTotal distinct symbols in core.market_ohlcv_daily: {total_symbols}")

over_10y = [s for s in symbol_stats if s[4] is not None and s[4] >= 10.0]
over_5y = [s for s in symbol_stats if s[4] is not None and 5.0 <= s[4] < 10.0]
over_1y = [s for s in symbol_stats if s[4] is not None and 1.0 <= s[4] < 5.0]
under_1y = [s for s in symbol_stats if s[4] is None or s[4] < 1.0]

print(f"Symbols with >= 10 years of data: {len(over_10y)}")
print(f"Symbols with 5 - 10 years of data:  {len(over_5y)}")
print(f"Symbols with 1 - 5 years of data:   {len(over_1y)}")
print(f"Symbols with < 1 year of data:      {len(under_1y)}")

# Print why NVL has only 63 rows if that's true:
nvl_rows = con.execute("SELECT date, open, close, volume FROM core.market_ohlcv_daily WHERE symbol = 'NVL' ORDER BY date ASC").fetchall()
print(f"\nFirst 5 rows of NVL daily:")
for r in nvl_rows[:5]:
    print("  ", r)
print(f"Last 5 rows of NVL daily:")
for r in nvl_rows[-5:]:
    print("  ", r)

con.close()
