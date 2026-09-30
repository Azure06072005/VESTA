import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

def inspect_db(path):
    print(f"\n=================== Inspecting {path} ===================")
    try:
        con = duckdb.connect(path, read_only=True)
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables").fetchall()
        print(f"Total tables: {len(tables)}")
        for schema, name in sorted(tables):
            try:
                cnt = con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
                print(f"  - {schema}.{name}: {cnt:,} rows")
            except Exception as e:
                print(f"  - {schema}.{name}: Error querying count -> {e}")
        con.close()
    except Exception as e:
        print(f"Error opening {path}: {e}")

inspect_db('db/vesta_snapshot.duckdb')
inspect_db('db/vesta_news.duckdb')
inspect_db('db/vesta_intraday_1m.duckdb')
