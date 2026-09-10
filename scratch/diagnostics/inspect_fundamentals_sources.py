import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

total = con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0]
vnstock_cnt = con.execute("""
    SELECT count(*) FROM core.fundamentals 
    WHERE data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%'
""").fetchone()[0]

cafef_cnt = con.execute("""
    SELECT count(*) FROM core.fundamentals 
    WHERE NOT (data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%')
""").fetchone()[0]

print(f"Total rows: {total:,}")
print(f"vnstock_data format rows (standard English codes): {vnstock_cnt:,}")
print(f"cafef format rows (Vietnamese strings/numeric keys): {cafef_cnt:,}")
print(f"Sum check: {vnstock_cnt + cafef_cnt:,} == {total:,}")

# Check breakdown by report type
print("\nBreakdown by report_type:")
rows = con.execute("""
    SELECT report_type,
           count(*) FILTER (WHERE data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%') as vnstock_rows,
           count(*) FILTER (WHERE NOT (data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%')) as cafef_rows,
           count(*) as total
    FROM core.fundamentals
    GROUP BY report_type
    ORDER BY report_type
""").fetchall()

for rt, v, c, t in rows:
    print(f"  {rt:20s}: vnstock={v:6,d} | cafef={c:6,d} | total={t:6,d}")

con.close()
