import duckdb
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NEWS_DB = "d:/VESTA/db/vesta_news.duckdb"

con = duckdb.connect(NEWS_DB, read_only=False)

# Xóa các views rỗng
views = con.execute("SELECT table_schema, table_name FROM information_schema.views WHERE table_schema IN ('core', 'staging')").fetchall()
for schema, name in views:
    con.execute(f"DROP VIEW IF EXISTS {schema}.{name};")
    print(f"Dropped empty view: {schema}.{name}")

# Xóa các bảng rỗng còn lại
news_tables_to_keep = {
    'core.news', 'staging.news',
    'core.news_resources', 'staging.news_resources',
    'core.sector_news_signal',
    'core.macro_policy', 'staging.macro_policy'
}

tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()
for schema, name in tables:
    full_name = f"{schema}.{name}"
    if full_name not in news_tables_to_keep:
        try:
            cnt = con.execute(f"SELECT count(*) FROM {full_name}").fetchone()[0]
            if cnt == 0:
                con.execute(f"DROP TABLE IF EXISTS {full_name};")
                print(f"Dropped empty table: {full_name}")
        except Exception as e:
            con.execute(f"DROP VIEW IF EXISTS {full_name};")
            con.execute(f"DROP TABLE IF EXISTS {full_name};")
            print(f"Dropped {full_name}: {e}")

con.execute("CHECKPOINT;")
con.close()

# Inspect lại kết quả vesta_news.duckdb
con = duckdb.connect(NEWS_DB, read_only=True)
remaining = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()
print(f"\n=== Remaining Tables in vesta_news.duckdb ({len(remaining)}) ===")
for schema, name in sorted(remaining):
    cnt = con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
    print(f"  - {schema}.{name}: {cnt:,} rows")
con.close()
