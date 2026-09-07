import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

# 1. Check breakdown of all 179,135 rows
print("=== Total rows in core.fundamentals ===")
total = con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0]
print(f"Total: {total}")

print("\n=== Exact classification condition evaluation ===")
# The condition in migration:
# WHERE NOT (
#     fetched_at < '2026-09-06'
#     OR data_json LIKE '%"BS_%'
#     OR data_json LIKE '%"IS_%'
#     OR data_json LIKE '%"CF_%'
#     OR data_json LIKE '%"RT_%'
# )
# Rows satisfying this are SET source = 'cafef'
# All other rows remain default 'vnstock_data'

q = """
SELECT 
    CASE 
        WHEN NOT (
            fetched_at < '2026-09-06'
            OR data_json LIKE '%"BS_%'
            OR data_json LIKE '%"IS_%'
            OR data_json LIKE '%"CF_%'
            OR data_json LIKE '%"RT_%'
        ) THEN 'cafef'
        ELSE 'vnstock_data'
    END AS final_source,
    count(*) as row_count
FROM core.fundamentals
GROUP BY 1
ORDER BY 1
"""
for r in con.execute(q).fetchall():
    print(f"  {r[0]}: {r[1]:,}")

print("\n=== Breakdown by fetched_at date ===")
q_dates = """
SELECT 
    CAST(fetched_at AS DATE) as crawl_date,
    count(*) as total_rows,
    count(CASE WHEN data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%' THEN 1 END) as with_std_prefixes,
    count(CASE WHEN NOT (data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%') THEN 1 END) as without_std_prefixes
FROM core.fundamentals
GROUP BY 1
ORDER BY 1
"""
for r in con.execute(q_dates).fetchall():
    print(f"  Date {r[0]}: total={r[1]:,}, with_std_prefixes={r[2]:,}, without_std_prefixes={r[3]:,}")
