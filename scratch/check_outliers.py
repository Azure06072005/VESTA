import sys
sys.stdout.reconfigure(encoding="utf-8")
import duckdb
con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
print("Future outliers in core.news_resources (> 2026-09-18):")
rows = con.execute("""
    SELECT source, published_at, headline, source_url 
    FROM core.news_resources 
    WHERE published_at > '2026-09-18 23:59:59'
    LIMIT 5
""").fetchall()
for r in rows:
    print(r)

print("\nPast outliers in core.news_resources (< 2000-01-01):")
rows2 = con.execute("""
    SELECT source, published_at, headline, source_url 
    FROM core.news_resources 
    WHERE published_at < '2000-01-01'
    LIMIT 5
""").fetchall()
for r in rows2:
    print(r)

print("\nCorporate events outliers (> 2026-09-18):")
rows3 = con.execute("""
    SELECT symbol, event_type, event_date 
    FROM core.corporate_events 
    WHERE event_date > '2026-09-18'
    LIMIT 5
""").fetchall()
for r in rows3:
    print(r)

con.close()
