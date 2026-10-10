import duckdb
import sys

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/admin/vesta_market_index.duckdb", read_only=True)
tables = con.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'core' 
    ORDER BY table_name
""").fetchall()
print("Tables in vesta_market_index.core:")
for (t,) in tables:
    cnt = con.execute(f'SELECT COUNT(*) FROM core."{t}"').fetchone()[0]
    print(f"  • {t}: {cnt:,} rows")

print("\nSample macro_rates:")
try:
    print(con.execute("SELECT * FROM core.macro_rates LIMIT 5").fetchdf())
except Exception as e:
    print("macro_rates error:", e)

print("\nSample macro_economic_series:")
try:
    print(con.execute("SELECT * FROM core.macro_economic_series LIMIT 5").fetchdf())
except Exception as e:
    print("macro_economic_series error:", e)

print("\nSample market_global_equity_daily:")
try:
    print(con.execute("SELECT * FROM core.market_global_equity_daily LIMIT 5").fetchdf())
except Exception as e:
    print("market_global_equity_daily error:", e)

print("\nSample dim_sector:")
try:
    print(con.execute("SELECT * FROM core.dim_sector LIMIT 5").fetchdf())
except Exception as e:
    print("dim_sector error:", e)

con.close()
