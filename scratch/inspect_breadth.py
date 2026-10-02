import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
cols = con.execute('PRAGMA table_info("core.market_breadth_series")').fetchall()
print('market_breadth_series columns:')
for c in cols:
    print(f'  {c[1]} ({c[2]})')
sample = con.execute('SELECT * FROM core.market_breadth_series LIMIT 3').fetchdf()
print(sample)
con.close()
