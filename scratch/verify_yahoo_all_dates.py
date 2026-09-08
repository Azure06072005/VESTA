import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
total = conn.execute("SELECT COUNT(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
min_date, max_date = conn.execute("SELECT MIN(published_at), MAX(published_at) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()

print(f"Total Yahoo Finance records in core.macro_policy: {total}")
print(f"Date span across all dates: {min_date} -> {max_date}")

# Distribution by year/month
dist = conn.execute("""
    SELECT strftime(published_at, '%Y-%m') AS ym, COUNT(*) 
    FROM core.macro_policy 
    WHERE source = 'yahoo_finance' 
    GROUP BY ym 
    ORDER BY ym DESC
""").fetchall()

print("\nDistribution of articles by month:")
for ym, cnt in dist:
    print(f"  {ym}: {cnt} articles")

print("\nRecent 5 articles:")
rows = conn.execute("""
    SELECT published_at, issuing_body, headline, source_url
    FROM core.macro_policy
    WHERE source = 'yahoo_finance'
    ORDER BY published_at DESC
    LIMIT 5
""").fetchall()

for r in rows:
    print(f"[{r[0]}] {r[1]}\n  Title: {r[2]}\n  URL: {r[3]}\n")

conn.close()
