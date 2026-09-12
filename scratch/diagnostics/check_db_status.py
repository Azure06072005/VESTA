import duckdb
import os

dbs = [
    ('db/vesta.duckdb', 'Main DB'),
    ('db/vesta_latest_backup.duckdb', 'Backup DB'),
    ('db/vesta_consolidated.duckdb', 'Consolidated Snapshot'),
    ('db/crawlers_staging.duckdb', 'Staging DB')
]

for db_path, name in dbs:
    if not os.path.exists(db_path):
        print(f"=== {name} ({db_path}) NOT FOUND ===")
        continue
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"=== {name} ({db_path}, {size_mb:.1f} MB) ===")
    try:
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'main') ORDER BY table_schema, table_name").fetchall()
        for s, t in tables:
            cnt = con.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
            print(f"  {s}.{t}: {cnt:,}")
        con.close()
    except Exception as e:
        print(f"  Error: {e}")
