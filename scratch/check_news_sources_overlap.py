import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)

print("=== SOURCES IN core.news ===")
res = con.execute("SELECT source, count(*) FROM core.news GROUP BY source ORDER BY count(*) DESC").fetchall()
for s, c in res:
    print(f"  {s}: {c:,}")

print("\n=== SOURCES IN core.news_resources ===")
res = con.execute("SELECT source, count(*) FROM core.news_resources GROUP BY source ORDER BY count(*) DESC").fetchall()
for s, c in res:
    print(f"  {s}: {c:,}")

print("\n=== SOURCES IN core.macro_policy ===")
res = con.execute("SELECT source, count(*) FROM core.macro_policy GROUP BY source ORDER BY count(*) DESC").fetchall()
for s, c in res:
    print(f"  {s}: {c:,}")

print("\n=== OVERLAPS ===")
overlap_np_nr = con.execute("""
    SELECT count(*) FROM core.macro_policy mp
    JOIN core.news_resources nr ON mp.source_url = nr.source_url
""").fetchone()[0]
print(f"Overlap between macro_policy and news_resources (by source_url): {overlap_np_nr}")

overlap_news_nr = con.execute("""
    SELECT count(*) FROM core.news n
    JOIN core.news_resources nr ON n.source_url = nr.source_url
""").fetchone()[0]
print(f"Overlap between news and news_resources (by source_url): {overlap_news_nr}")

overlap_news_mp = con.execute("""
    SELECT count(*) FROM core.news n
    JOIN core.macro_policy mp ON n.source_url = mp.source_url
""").fetchone()[0]
print(f"Overlap between news and macro_policy (by source_url): {overlap_news_mp}")

print("\n=== DOC_TYPE IN core.news_resources ===")
res = con.execute("SELECT doc_type, count(*) FROM core.news_resources GROUP BY doc_type ORDER BY count(*) DESC LIMIT 10").fetchall()
for d, c in res:
    print(f"  {d}: {c:,}")

print("\n=== DOC_TYPE IN core.macro_policy ===")
res = con.execute("SELECT doc_type, count(*) FROM core.macro_policy GROUP BY doc_type ORDER BY count(*) DESC LIMIT 10").fetchall()
for d, c in res:
    print(f"  {d}: {c:,}")

con.close()
