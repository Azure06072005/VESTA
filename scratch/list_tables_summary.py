import duckdb

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
tables = conn.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema IN ('core', 'staging')
    ORDER BY table_schema, table_name
""").fetchall()

for schema, name in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM {schema}.{name}").fetchone()[0]
    print(f"{schema}.{name:<25} : {cnt:,} rows")

conn.close()
