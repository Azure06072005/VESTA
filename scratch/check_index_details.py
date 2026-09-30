import duckdb
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("=== 1. Check core.dim_index_metadata ===")
try:
    df_meta = con.execute("SELECT index_code, index_name, exchange, description FROM core.dim_index_metadata").fetchdf()
    print(df_meta.to_string())
except Exception as e:
    print(f"Error dim_index_metadata: {e}")

print("\n=== 2. Check all distinct index_code in core.market_index_daily ===")
df_idx = con.execute("""
    SELECT index_code, min(date) as min_dt, max(date) as max_dt, count(*) as cnt 
    FROM core.market_index_daily 
    GROUP BY index_code 
    ORDER BY index_code
""").fetchdf()
print(df_idx.to_string())

print("\n=== 3. Check core.market_ohlcv_1m in vesta_snapshot ===")
try:
    cnt_1m = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    print(f"Count of rows in core.market_ohlcv_1m (in vesta_snapshot): {cnt_1m}")
    if cnt_1m > 0:
        symbols_1m = con.execute("SELECT symbol, count(*) FROM core.market_ohlcv_1m GROUP BY symbol ORDER BY count(*) DESC LIMIT 10").fetchdf()
        print("Sample symbols in 1m snapshot:")
        print(symbols_1m)
except Exception as e:
    print(f"Error 1m in snapshot: {e}")

print("\n=== 4. Check core.dim_index_constituents ===")
try:
    cnt_const = con.execute("SELECT index_code, count(*) as constituents_count FROM core.dim_index_constituents GROUP BY index_code").fetchdf()
    print(cnt_const.to_string())
except Exception as e:
    print(f"Error constituents: {e}")

print("\n=== 5. Check foreign room tables ===")
try:
    print("foreign_ownership_room sample:")
    print(con.execute("SELECT * FROM core.foreign_ownership_room LIMIT 5").fetchdf().to_string())
except Exception as e:
    print(f"Error room: {e}")

try:
    print("market_foreign_flow_daily sample:")
    print(con.execute("SELECT symbol, min(date), max(date), count(*) FROM core.market_foreign_flow_daily GROUP BY symbol ORDER BY count(*) DESC LIMIT 5").fetchdf().to_string())
except Exception as e:
    print(f"Error foreign flow: {e}")

