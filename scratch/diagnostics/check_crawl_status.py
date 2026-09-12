import duckdb

for db_path in ['db/crawlers_staging.duckdb', 'db/vesta_latest_backup.duckdb', 'db/vesta.duckdb']:
    try:
        con = duckdb.connect(db_path, read_only=True)
        print(f"=== {db_path} ===")
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'main')").fetchall()
        for schema, tbl in tables:
            if any(k in tbl for k in ['macro', 'news', 'article', 'policy']):
                try:
                    cnt = con.execute(f"SELECT count(*) FROM {schema}.{tbl}").fetchone()[0]
                    sources = con.execute(f"SELECT source, count(*) FROM {schema}.{tbl} GROUP BY source").fetchall()
                    print(f"  {schema}.{tbl}: {cnt:,} rows")
                    for s, scnt in sorted(sources, key=lambda x: x[1], reverse=True):
                        print(f"      - {s}: {scnt:,}")
                except Exception as e:
                    print(f"  {schema}.{tbl}: error {e}")
        con.close()
    except Exception as e:
        print(f"=== {db_path} (FAILED: {e}) ===")
