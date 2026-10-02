import duckdb

for db_name in ['vesta_snapshot.duckdb', 'vesta_ohlcv.duckdb', 'vesta_news.duckdb']:
    print(f"*** DB: {db_name} ***")
    conn = duckdb.connect(f"d:/VESTA/db/{db_name}")
    tables = conn.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'main') ORDER BY table_schema, table_name").fetchall()
    for schema, table in tables:
        cols = [c[0] for c in conn.execute(f"DESCRIBE {schema}.{table}").fetchall()]
        time_cols = [c for c in cols if any(k in c.lower() for k in ['date', 'time', 'published', 'created', 'updated'])]
        cnt = conn.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
        max_val = None
        if time_cols:
            tc = time_cols[0]
            try:
                max_val = conn.execute(f"SELECT max({tc}) FROM {schema}.{table}").fetchone()[0]
            except Exception as e:
                max_val = str(e)
            print(f"  {schema}.{table}: count={cnt:,}, col={tc}, max={max_val}")
        else:
            print(f"  {schema}.{table}: count={cnt:,}, no time col")
    conn.close()
