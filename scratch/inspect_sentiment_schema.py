import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
print("=== DDL core.market_sentiment_snapshot ===")
print(con.execute("DESCRIBE core.market_sentiment_snapshot").df())
print("\n=== CURRENT SAMPLE DATA ===")
print(con.execute("SELECT * FROM core.market_sentiment_snapshot").df())
con.close()
