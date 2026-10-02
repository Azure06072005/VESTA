import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL core.order_book_depth ===")
print(con.execute("DESCRIBE core.order_book_depth").df())
print("\n=== SAMPLE DATA ===")
print(con.execute("SELECT * FROM core.order_book_depth LIMIT 2").df())
con.close()
