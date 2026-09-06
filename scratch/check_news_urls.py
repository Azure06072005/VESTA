import duckdb

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
res = con.execute("SELECT source_url FROM core.news WHERE source_url NOT LIKE 'http%' LIMIT 5").fetchall()
print("Sample non-http URLs in core.news:")
for r in res:
    print(" ", r[0])
con.close()
