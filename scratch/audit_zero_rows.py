import duckdb
import glob
import os

dbs = sorted(glob.glob('db/admin/*.duckdb'))
print('=== ZERO ROWS TABLE AUDIT ===')
empty_tables = []
for db_path in dbs:
    db_name = os.path.basename(db_path)
    try:
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """).fetchall()
        for schema, tbl in tables:
            cnt = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{tbl}"').fetchone()[0]
            if cnt == 0:
                empty_tables.append((db_name, schema, tbl))
                print(f'[EMPTY] {db_name} -> {schema}.{tbl}: 0 rows')
            else:
                print(f'[OK] {db_name} -> {schema}.{tbl}: {cnt:,} rows')
        con.close()
    except Exception as e:
        print(f'Error reading {db_name}: {e}')

print(f'\nTotal empty tables found: {len(empty_tables)}')
