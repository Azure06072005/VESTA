import duckdb
import os

db_list = ['db/vesta_snapshot.duckdb', 'db/vesta.duckdb', 'db/vesta_crawled_fresh.duckdb']
for db_name in db_list:
    if os.path.exists(db_name):
        try:
            con = duckdb.connect(db_name, read_only=True)
            tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%realtime_quote_snapshot%'").fetchall()
            print(f"=== {db_name} ===")
            if not tables:
                print("  No realtime_quote_snapshot tables found.")
            for schema, tbl in tables:
                cnt = con.execute(f"SELECT COUNT(*) FROM {schema}.{tbl}").fetchone()[0]
                distinct_syms = con.execute(f"SELECT COUNT(DISTINCT symbol) FROM {schema}.{tbl}").fetchone()[0]
                min_t, max_t = con.execute(f"SELECT MIN(snapshot_at), MAX(snapshot_at) FROM {schema}.{tbl}").fetchone()
                print(f"  {schema}.{tbl}: {cnt} rows, {distinct_syms} symbols, time: {min_t} -> {max_t}")
            con.close()
        except Exception as e:
            print(f"=== {db_name} (Error: {e}) ===")
