import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY);")

dbs = [
    ('vesta_snapshot (main)', 'vesta_snapshot'),
    ('vesta_ohlcv (ohlcv_db)', 'ohlcv_db'),
    ('vesta_news (news_db)', 'news_db')
]

for db_label, db_alias in dbs:
    print(f"\n{'='*70}")
    print(f"DATABASE: {db_label}")
    print(f"{'='*70}")
    tables = con.execute(f"""
        SELECT table_schema, table_name, table_type 
        FROM information_schema.tables 
        WHERE table_catalog = '{db_alias}' AND table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
    """).fetchall()
    for s, t, ty in tables:
        try:
            cnt = con.execute(f"SELECT count(*) FROM {db_alias}.{s}.{t}").fetchone()[0]
            print(f"  [{s:10s}] {t:35s} ({ty:10s}): {cnt:>12,} dòng")
        except Exception as e:
            print(f"  [{s:10s}] {t:35s} ({ty:10s}): [ERROR: {e}]")
