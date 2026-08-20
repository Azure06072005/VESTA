import sys
import pathlib
import duckdb

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db

con = db.bootstrap_schema()
print("Connected to:", db.DB_PATH)
print("Schemas:", db.verify_schemas(con))

tables = con.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema IN ('staging', 'core', 'meta') 
    ORDER BY table_schema, table_name
""").fetchall()

print("\nTables in DB:")
for s, t in tables:
    count = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
    print(f"  {s}.{t}: {count} rows")
