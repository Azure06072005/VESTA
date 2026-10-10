import duckdb

con = duckdb.connect('db/admin/vesta_ohlcv.duckdb', read_only=False)
views = con.execute("""
    SELECT schema_name, view_name, sql 
    FROM duckdb_views()
""").fetchall()

print("Views in vesta_ohlcv.duckdb:")
for schema, name, sql in views:
    print(f"- {schema}.{name}")
    try:
        con.execute(f"SELECT * FROM \"{schema}\".\"{name}\" LIMIT 1")
        print("  Status: OK")
    except Exception as e:
        print(f"  Status: Broken ({e})")
con.close()
