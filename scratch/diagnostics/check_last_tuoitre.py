import sys
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/crawlers_staging.duckdb", read_only=True)
res = con.execute("""
    SELECT published_at, headline, source_url 
    FROM core.macro_policy 
    WHERE source = 'tuoitre' 
    ORDER BY fetched_at DESC 
    LIMIT 20
""").fetchall()

print("Last 20 articles fetched by Tuoi Tre crawler:")
for p, h, u in res:
    print(f"  [{p}] {h[:60]} ({u})")
con.close()
