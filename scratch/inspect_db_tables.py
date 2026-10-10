import duckdb
import glob

for db_path in glob.glob("db/*.duckdb"):
    try:
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'meta') ORDER BY table_schema, table_name").fetchall()
        print(f"\n=== {db_path} ===")
        for s, t in tables:
            cnt = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
            print(f"  {s}.{t}: {cnt:,} rows")
        con.close()
    except Exception as e:
        print(f"Error {db_path}: {e}")
