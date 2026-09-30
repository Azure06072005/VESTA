import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
df = con.execute("""
    SELECT index_code, min(date) as min_dt, max(date) as max_dt, count(*) as cnt
    FROM core.market_index_daily
    WHERE index_code IN ('VNINDEX', 'VN30', 'HNX-INDEX', 'HNX30', 'UPCOM-INDEX', 'VN100')
    GROUP BY index_code
    ORDER BY index_code
""").fetchdf()
print("=== Updated Vietnam Indices in core.market_index_daily ===")
print(df.to_string())
