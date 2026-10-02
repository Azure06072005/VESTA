import duckdb
import os

db_candidates = ['db/vesta_snapshot.duckdb', 'db/vesta_backup.duckdb']
db_path = None
con = None

for cand in db_candidates:
    if os.path.exists(cand):
        try:
            con = duckdb.connect(cand, read_only=True)
            db_path = cand
            print(f"Successfully opened {cand}")
            break
        except Exception as e:
            print(f"Could not open {cand}: {e}")

if not con:
    print("Cannot connect to any DB candidate.")
    exit(1)

tables = con.execute("""
    SELECT table_schema, table_name, table_type 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
""").fetchall()

print(f"\n=== DATABASE: {db_path} ===")
print(f"Total user tables/views: {len(tables)}")

schemas = {}
for s, t, ty in tables:
    schemas.setdefault(s, []).append((t, ty))

for s, tbls in schemas.items():
    print(f"\n==========================================")
    print(f"SCHEMA: [{s}] ({len(tbls)} tables/views)")
    print(f"==========================================")
    for t, ty in tbls:
        try:
            cnt = con.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        except Exception as e:
            cnt = f"ERR: {e}"
        print(f"  - {s}.{t} ({ty}): {cnt:,} rows" if isinstance(cnt, int) else f"  - {s}.{t} ({ty}): {cnt}")

con.close()
