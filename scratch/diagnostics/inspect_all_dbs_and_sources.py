import duckdb
import pathlib

dbs = {
    "vesta_latest_backup.duckdb": "d:/VESTA/db/vesta_latest_backup.duckdb",
    "vesta.duckdb": "d:/VESTA/db/vesta.duckdb",
    "crawlers_staging.duckdb": "d:/VESTA/db/crawlers_staging.duckdb",
    "vesta_staging.duckdb": "d:/VESTA/db/vesta_staging.duckdb",
}

for name, path in dbs.items():
    print(f"\n==========================================")
    print(f"DATABASE: {name} ({pathlib.Path(path).stat().st_size:,} bytes)")
    print(f"==========================================")
    try:
        con = duckdb.connect(path, read_only=True)
    except Exception as e:
        print(f"  Error opening: {e}")
        continue
    
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging') ORDER BY table_schema, table_name").fetchall()
    for s, t in tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
        extra = ""
        # Check sources if table has source column
        cols = [r[0] for r in con.execute(f"DESCRIBE {s}.{t}").fetchall()]
        if "source" in cols:
            srcs = con.execute(f"SELECT source, COUNT(*) FROM {s}.{t} GROUP BY source").fetchall()
            extra = f" -> sources: {srcs}"
        print(f"  {s}.{t:30s}: {cnt:>10,} rows{extra}")
    con.close()
