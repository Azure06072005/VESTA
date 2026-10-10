import duckdb
import glob
import os

snapshot_p = 'db/admin/vesta_snapshot.duckdb'

con_snap = duckdb.connect(snapshot_p, read_only=True)
snap_tables = set()
for schema, tbl in con_snap.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
""").fetchall():
    try:
        cnt = con_snap.execute(f'SELECT COUNT(*) FROM "{schema}"."{tbl}"').fetchone()[0]
        snap_tables.add((schema, tbl, cnt))
    except Exception as e:
        snap_tables.add((schema, tbl, -1))
con_snap.close()

mission_dbs = glob.glob('db/admin/*.duckdb')
mission_tables = set()
for mdb in mission_dbs:
    if 'vesta_snapshot' in mdb or 'temp' in mdb:
        continue
    try:
        con_m = duckdb.connect(mdb, read_only=True)
        for schema, tbl in con_m.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        """).fetchall():
            mission_tables.add((schema, tbl))
        con_m.close()
    except Exception:
        pass

missing_in_mission = []
for schema, tbl, cnt in sorted(snap_tables):
    if (schema, tbl) not in mission_tables:
        missing_in_mission.append((schema, tbl, cnt))

print(f"Total tables/views in vesta_snapshot: {len(snap_tables)}")
print(f"Tables in snapshot NOT in any of the 5 mission DBs: {len(missing_in_mission)}")
for s, t, c in missing_in_mission:
    print(f"  • {s}.{t}: {c:,} rows")
