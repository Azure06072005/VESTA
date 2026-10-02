import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL core.realtime_quote_snapshot ===")
print(con.execute("DESCRIBE core.realtime_quote_snapshot").df())
print("\n=== SAMPLE DATA ===")
print(con.execute("SELECT * FROM core.realtime_quote_snapshot LIMIT 2").df())
con.close()
