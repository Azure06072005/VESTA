import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()
print(f"=== Tables in vesta_ohlcv.duckdb (Total: {len(tables)}) ===")
for schema, name in sorted(tables):
    cnt = con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
    print(f"  - {schema}.{name}: {cnt:,} rows")

print("\nSample symbols in vesta_ohlcv.core.market_ohlcv_daily:")
sample_daily = con.execute("SELECT symbol, count(*) FROM core.market_ohlcv_daily GROUP BY symbol ORDER BY count(*) DESC LIMIT 5").fetchdf()
print(sample_daily)

print("\nSample symbols in vesta_ohlcv.core.market_ohlcv_1m:")
sample_1m = con.execute("SELECT symbol, count(*) FROM core.market_ohlcv_1m GROUP BY symbol ORDER BY count(*) DESC LIMIT 5").fetchdf()
print(sample_1m)

con.close()
