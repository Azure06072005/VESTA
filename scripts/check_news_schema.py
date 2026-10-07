import duckdb

con = duckdb.connect("db/vesta_news.duckdb", read_only=True)
sample = con.execute("SELECT symbol, headline, summary, source, published_at, source_url FROM core.news WHERE headline IS NOT NULL ORDER BY published_at DESC LIMIT 5").fetchall()
print("\nSample news:")
for s in sample:
    print(f"  [{s[0]}] ({s[3]}) {s[1][:80]}... | Date: {s[4]} | URL: {s[5]}")
    if s[2]:
        print(f"    Summary: {s[2][:100]}...")

# Also check news for VIC
vic_news = con.execute("SELECT symbol, headline, source, published_at FROM core.news WHERE symbol = 'VIC' AND headline IS NOT NULL ORDER BY published_at DESC LIMIT 3").fetchall()
print(f"\nVIC news count: {con.execute('SELECT count(*) FROM core.news WHERE symbol = \'VIC\'').fetchone()[0]}")
for vn in vic_news:
    print(f"  VIC: {vn[1]} ({vn[2]}, {vn[3]})")

con.close()
