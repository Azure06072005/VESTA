import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
print(con.execute("DESCRIBE core.market_index_daily").fetchdf().to_string())
print("\nSample row:")
print(con.execute("SELECT * FROM core.market_index_daily LIMIT 2").fetchdf().to_string())
