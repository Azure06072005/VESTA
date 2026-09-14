"""scratch/inspect_full_vesta_db.py

Inspects table counts and sizes in db/vesta.duckdb
"""
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)
tables = con.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema IN ('core', 'meta', 'staging')
    ORDER BY table_schema, table_name
""").df()

print("=== TABLES IN db/vesta.duckdb ===")
for _, r in tables.iterrows():
    schema, tname = r['table_schema'], r['table_name']
    try:
        cnt = con.execute(f"SELECT count(*) FROM {schema}.{tname}").fetchone()[0]
        print(f" {schema}.{tname:<30} : {cnt:>12,} rows")
    except Exception as e:
        print(f" {schema}.{tname:<30} : ERROR ({e})")
con.close()
