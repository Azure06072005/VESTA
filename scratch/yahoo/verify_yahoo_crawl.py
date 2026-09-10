import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
count = conn.execute("SELECT COUNT(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
min_date, max_date = conn.execute("SELECT MIN(published_at), MAX(published_at) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()

print(f"Total Yahoo Finance records in core.macro_policy: {count}")
print(f"Date coverage: {min_date} -> {max_date}")

print("\n--- Recent 5 records ---")
rows = conn.execute("""
    SELECT published_at, issuing_body, headline, length(body), source_url 
    FROM core.macro_policy 
    WHERE source = 'yahoo_finance' 
    ORDER BY published_at DESC 
    LIMIT 5
""").fetchall()

for r in rows:
    print(f"[{r[0]}] Issuing Body: {r[1]} (Body Length: {r[3]} chars)")
    print(f"  Headline: {r[2]}")
    print(f"  URL: {r[4]}\n")

conn.close()
