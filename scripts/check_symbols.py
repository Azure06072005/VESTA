import duckdb

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
sample = con.execute("SELECT symbol, organ_name, en_organ_name, exchange, industry_name FROM core.dim_symbol WHERE is_delisted = false LIMIT 5").fetchall()
print("Sample active symbols:")
for s in sample:
    print(f"  {s}")

etfs = con.execute("SELECT symbol, organ_name, exchange FROM core.dim_symbol WHERE symbol LIKE 'E1%' OR symbol LIKE 'FU%' OR organ_name ILIKE '%quỹ%' LIMIT 10").fetchall()
print(f"\nETFs in dim_symbol ({len(etfs)}):")
for e in etfs:
    print(f"  {e}")

con.close()
