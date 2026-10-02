import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL core.intraday_trades ===")
print(con.execute("DESCRIBE core.intraday_trades").df())
print("\n=== SAMPLE DATA ===")
print(con.execute("SELECT * FROM core.intraday_trades LIMIT 2").df())
con.close()
