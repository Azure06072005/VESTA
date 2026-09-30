import duckdb

con = duckdb.connect("d:/VESTA/db/vesta_snapshot.duckdb", read_only=True)
tables = con.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_name LIKE '%news%' OR table_name LIKE '%crawl%'
    ORDER BY table_schema, table_name
""").fetchall()

print("Found tables:")
for s, t in tables:
    try:
        cnt = con.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
        print(f"  {s}.{t}: {cnt:,} rows")
    except Exception as e:
        print(f"  {s}.{t}: Error {e}")

# Check DDL of these tables
for s, t in tables:
    if "news" in t:
        ddl = con.execute(f"SELECT sql FROM duckdb_tables() WHERE schema_name = '{s}' AND table_name = '{t}'").fetchone()
        if ddl:
            print(f"\n--- DDL for {s}.{t} ---")
            print(ddl[0])

con.close()
