import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=False)
future_cnt = con.execute("SELECT count(*) FROM core.news_resources WHERE published_at > '2026-09-18 23:59:59'").fetchone()[0]
past_cnt = con.execute("SELECT count(*) FROM core.news_resources WHERE published_at < '1990-01-01'").fetchone()[0]
print(f"Future outliers: {future_cnt}, Ancient outliers: {past_cnt}")
if future_cnt > 0:
    con.execute("UPDATE core.news_resources SET published_at = fetched_at WHERE published_at > '2026-09-18 23:59:59'")
    print("Cleaned future outliers to fetched_at")
if past_cnt > 0:
    con.execute("UPDATE core.news_resources SET published_at = fetched_at WHERE published_at < '1990-01-01'")
    print("Cleaned ancient outliers to fetched_at")
con.close()
print("Outlier sanitization completed successfully.")
