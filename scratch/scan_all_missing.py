import duckdb

db_c = "db/vesta.duckdb"
db_s = "db/vesta_snapshot.duckdb"

con = duckdb.connect(db_s, read_only=True)
con.execute(f"ATTACH '{db_c}' AS vesta (READ_ONLY)")

tables_v = con.execute("SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = 'vesta' AND schema_name IN ('core', 'staging', 'meta', 'preprocessed')").fetchall()

print("Scanning all tables for any missing data...")
for s, t in tables_v:
    full_v = f"vesta.{s}.{t}"
    full_s = f"{s}.{t}"
    
    # Check if table exists in snapshot
    exists = con.execute(f"SELECT count(*) FROM duckdb_tables() WHERE database_name = 'vesta_snapshot' AND schema_name='{s}' AND table_name='{t}'").fetchone()[0]
    if exists == 0:
        cnt_v = con.execute(f"SELECT count(*) FROM {full_v}").fetchone()[0]
        print(f"[MISSING TABLE] {full_s} -> exists only in vesta with {cnt_v:,} rows")
        continue

    cnt_v = con.execute(f"SELECT count(*) FROM {full_v}").fetchone()[0]
    cnt_s = con.execute(f"SELECT count(*) FROM {full_s}").fetchone()[0]
    if cnt_v > 0 and cnt_s == 0:
        print(f"[EMPTY IN SNAPSHOT] {full_s} -> Vesta has {cnt_v:,} rows, Snapshot has 0 rows")
    elif cnt_v > cnt_s:
        print(f"[MORE IN VESTA] {full_s} -> Vesta: {cnt_v:,} | Snapshot: {cnt_s:,} (diff: +{cnt_v - cnt_s:,})")

con.close()
