import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

cnt_before = con.execute("SELECT count(*) FROM core.news WHERE published_at < TIMESTAMP '2000-01-01'").fetchone()[0]
cnt_after = con.execute("SELECT count(*) FROM core.news WHERE published_at > TIMESTAMP '2026-12-31'").fetchone()[0]
cnt_null = con.execute("SELECT count(*) FROM core.news WHERE published_at IS NULL").fetchone()[0]
total = con.execute("SELECT count(*) FROM core.news").fetchone()[0]

print(f"Total core.news: {total}")
print(f"Before 2000: {cnt_before}")
print(f"After 2026: {cnt_after}")
print(f"NULL: {cnt_null}")

# Check missing body text in core.news
cnt_no_body = con.execute("SELECT count(*) FROM core.news WHERE body IS NULL OR length(trim(body)) = 0").fetchone()[0]
print(f"No body: {cnt_no_body} ({cnt_no_body/total*100:.2f}%)")

# Check source breakdown of no body
print("\nNo body by source:")
print(con.execute("SELECT source, count(*) as cnt, sum(CASE WHEN body IS NULL OR length(trim(body)) = 0 THEN 1 ELSE 0 END) as no_body FROM core.news GROUP BY source").df().to_string())

con.close()
