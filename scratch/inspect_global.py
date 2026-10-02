import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
cols = con.execute('PRAGMA table_info("core.market_global_equity_daily")').fetchall()
print('market_global_equity_daily columns:')
for c in cols:
    print(f'  {c[1]} ({c[2]})')
symbols = con.execute('SELECT DISTINCT symbol FROM core.market_global_equity_daily').fetchall()
print('symbols:', [s[0] for s in symbols])
con.close()
