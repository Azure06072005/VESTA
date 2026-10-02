import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL core.market_screener_snapshot ===")
print(con.execute("DESCRIBE core.market_screener_snapshot").df())
print("\n=== SAMPLE DATA ===")
print(con.execute("SELECT * FROM core.market_screener_snapshot LIMIT 2").df())
con.close()
