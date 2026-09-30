import duckdb

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)
tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()

zero_row_tables = []
populated_tables = []

for schema, name in tables:
    cnt = con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
    if cnt == 0:
        zero_row_tables.append((schema, name))
    else:
        populated_tables.append((schema, name, cnt))

con.close()

print(f"=== vesta_news.duckdb Audit ===")
print(f"Populated tables ({len(populated_tables)}):")
for s, n, c in populated_tables:
    print(f"  - {s}.{n}: {c:,} rows")

print(f"\nZero-row skeleton tables ({len(zero_row_tables)}):")
for s, n in zero_row_tables[:10]:
    print(f"  - {s}.{n}")
print(f"  ... và {len(zero_row_tables)-10} bảng rỗng khác.")
