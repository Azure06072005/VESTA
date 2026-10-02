import duckdb

print("=== CHECKING VESTA_BACKUP.DUCKDB ===")
try:
    con = duckdb.connect('db/vesta_backup.duckdb', read_only=True)
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='core' ORDER BY table_name").fetchall()
    print("Found tables in core:")
    for s, t in tables:
        cnt = con.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
        print(f"  {s}.{t}: {cnt:,} rows")
    con.close()
    print("Successfully read vesta_backup.duckdb")
except Exception as e:
    print("Error reading vesta_backup.duckdb:", e)
