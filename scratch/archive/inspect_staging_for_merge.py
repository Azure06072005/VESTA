import duckdb
import os

staging_dbs = [
    'd:/VESTA/db/staging_tnck.duckdb',
    'd:/VESTA/db/staging_sync.duckdb',
    'd:/VESTA/db/staging_tuoitre.duckdb',
    'd:/VESTA/db/crawlers_staging.duckdb'
]

print("=" * 80)
print("INSPECTING STAGING DATABASES FOR MERGE")
print("=" * 80)

for db_path in staging_dbs:
    if not os.path.exists(db_path):
        print(f"\n[NOT FOUND] {db_path}")
        continue
    
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\nDatabase: {db_path} ({size_mb:.2f} MB)")
    try:
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema IN ('core', 'staging', 'main')
            ORDER BY table_schema, table_name
        """).fetchall()
        
        if not tables:
            print("  No tables found.")
        for schema, tbl in tables:
            count = con.execute(f"SELECT count(*) FROM {schema}.{tbl}").fetchone()[0]
            # check min/max date if published_at exists
            cols = [c[0] for c in con.execute(f"DESCRIBE {schema}.{tbl}").fetchall()]
            date_info = ""
            if 'published_at' in cols:
                min_d = con.execute(f"SELECT min(published_at) FROM {schema}.{tbl}").fetchone()[0]
                max_d = con.execute(f"SELECT max(published_at) FROM {schema}.{tbl}").fetchone()[0]
                date_info = f" | Dates: {min_d} -> {max_d}"
            elif 'date' in cols:
                min_d = con.execute(f"SELECT min(date) FROM {schema}.{tbl}").fetchone()[0]
                max_d = con.execute(f"SELECT max(date) FROM {schema}.{tbl}").fetchone()[0]
                date_info = f" | Dates: {min_d} -> {max_d}"
            print(f"  - {schema}.{tbl}: {count:,} rows{date_info}")
        con.close()
    except Exception as e:
        print(f"  Error inspecting {db_path}: {e}")
