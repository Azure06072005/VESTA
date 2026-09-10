import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
count = conn.execute("SELECT COUNT(*) FROM core.macro_policy WHERE source = 'luatvietnam'").fetchone()[0]
rows = conn.execute("SELECT published_at, issuing_body, doc_number, headline, source_url FROM core.macro_policy WHERE source = 'luatvietnam' ORDER BY published_at DESC").fetchall()
print(f"Total luatvietnam records in core.macro_policy: {count}")
for r in rows:
    print(f"[{r[0]}] Doc: {r[2]} | {r[1]}")
    print(f"  Title: {r[3]}")
    print(f"  URL: {r[4]}\n")
conn.close()
