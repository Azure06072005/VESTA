import duckdb

con = duckdb.connect(':memory:')
con.execute("ATTACH 'db/vesta_snapshot.duckdb' AS snap (READ_ONLY);")
con.execute("ATTACH 'db/vesta_news.duckdb' AS news (READ_ONLY);")

print("Checking news_resources overlap:")
missing_res = con.execute("""
    SELECT count(*) 
    FROM snap.core.news_resources s
    WHERE s.source_url NOT IN (SELECT source_url FROM news.core.news_resources)
""").fetchone()[0]
print(f"Number of resources in snap.core.news_resources not yet in news.core.news_resources: {missing_res}")
con.close()
