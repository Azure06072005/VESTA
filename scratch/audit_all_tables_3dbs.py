import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH 'db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH 'db/vesta_news.duckdb' AS news_db (READ_ONLY);")

def show_tables(db_name, prefix=''):
    tables = con.execute(f"""
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables 
        WHERE table_catalog = '{db_name}' AND table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name;
    """).fetchall()
    print(f"\n=======================================================")
    print(f"=== DANH SÁCH BẢNG TRONG DATABASE: {db_name} ===")
    print(f"=======================================================")
    for s, t, typ in tables:
        full_t = f"{prefix}{s}.{t}"
        try:
            cnt = con.execute(f"SELECT count(*) FROM {full_t}").fetchone()[0]
            print(f"  {full_t:<45} ({typ:<5}): {cnt:>12,} rows")
        except Exception as e:
            print(f"  {full_t:<45} ({typ:<5}): error {e}")

show_tables('vesta_snapshot', '')
show_tables('ohlcv_db', 'ohlcv_db.')
show_tables('news_db', 'news_db.')

con.close()
