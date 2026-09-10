import duckdb

con = duckdb.connect(":memory:")
con.execute("ATTACH 'd:/VESTA/db/vesta.duckdb' AS live (READ_ONLY)")
con.execute("ATTACH 'd:/VESTA/db/vesta_latest_backup.duckdb' AS bak (READ_ONLY)")

# Test dim_symbol reconciliation
con.execute("CREATE TABLE mem_dim_symbol AS SELECT * FROM live.core.dim_symbol")
con.execute("INSERT INTO mem_dim_symbol SELECT * FROM bak.core.dim_symbol WHERE symbol NOT IN (SELECT symbol FROM mem_dim_symbol)")
count = con.execute("SELECT count(*) FROM mem_dim_symbol").fetchone()[0]
print("Reconciled dim_symbol count:", count)

# Test orphan check on live fundamentals against reconciled dim_symbol
orphans = con.execute("SELECT count(DISTINCT symbol) FROM live.core.fundamentals WHERE symbol NOT IN (SELECT symbol FROM mem_dim_symbol)").fetchone()[0]
print("Orphan fundamentals against reconciled dim_symbol:", orphans)

# Test orphan check on live corporate events against reconciled dim_symbol
orphans_corp = con.execute("SELECT count(DISTINCT symbol) FROM live.core.corporate_events WHERE symbol NOT IN (SELECT symbol FROM mem_dim_symbol)").fetchone()[0]
print("Orphan corporate events against reconciled dim_symbol:", orphans_corp)
