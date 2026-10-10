import duckdb
import sys

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/admin/vesta_news.duckdb", read_only=True)
print("News source / category breakdown:")
try:
    print(con.execute("""
        SELECT source, COUNT(*), MIN(published_at), MAX(published_at) 
        FROM core.news 
        GROUP BY source
    """).fetchdf())
except Exception as e:
    print("Error:", e)

print("\nSample news with global/world tags or macro:")
try:
    print(con.execute("""
        SELECT title, source, published_at 
        FROM core.news 
        WHERE title ILIKE '%thế giới%' OR title ILIKE '%quốc tế%' OR title ILIKE '%fed%' OR title ILIKE '%mỹ%' OR title ILIKE '%trung quốc%'
        ORDER BY published_at DESC LIMIT 5
    """).fetchdf())
except Exception as e:
    print("Error:", e)

con.close()
