import duckdb
con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=False)
con.execute("ATTACH 'd:/VESTA/db/vesta_latest_backup.duckdb' AS bak (READ_ONLY)")
con.execute("INSERT INTO core.dim_symbol SELECT * FROM bak.core.dim_symbol WHERE symbol NOT IN (SELECT symbol FROM core.dim_symbol)")
count = con.execute("SELECT count(*) FROM core.dim_symbol").fetchone()[0]
orphans = con.execute("SELECT count(DISTINCT symbol) FROM core.fundamentals WHERE symbol NOT IN (SELECT symbol FROM core.dim_symbol)").fetchone()[0]
print(f"vesta.duckdb dim_symbol count: {count}, orphan fundamentals: {orphans}")
con.close()
