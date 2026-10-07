import duckdb

print("\nChecking db/vesta_ohlcv.duckdb:")
try:
    con = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')").fetchall()
    print("Tables in vesta_ohlcv.duckdb:")
    for s, t in tables:
        cnt = con.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        print(f"  {s}.{t}: {cnt} rows")
        if "ohlcv" in t.lower() and cnt > 0:
            sample = con.execute(f'SELECT * FROM "{s}"."{t}" LIMIT 2').fetchall()
            print(f"    sample: {sample}")
    con.close()
except Exception as e:
    print(f"Error reading vesta_ohlcv.duckdb: {e}")
