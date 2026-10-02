import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL preprocessed.fundamentals_ratios ===")
print(con.execute("DESCRIBE preprocessed.fundamentals_ratios").df())
print("\n=== SAMPLE DATA ===")
print(con.execute("SELECT * FROM preprocessed.fundamentals_ratios LIMIT 2").df())
con.close()
