import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

print("--- Inspecting the 3 rows from 2026-09-05 ---")
rows = con.execute("""
    SELECT symbol, report_type, period_end, available_at, fetched_at, data_json
    FROM core.fundamentals 
    WHERE fetched_at >= '2026-09-05' AND fetched_at < '2026-09-06'
""").fetchall()
for r in rows:
    print(r[:5], r[5][:300])

print("\n--- Inspecting 3 sample rows from 2026-09-06 ---")
rows_cafef = con.execute("""
    SELECT symbol, report_type, period_end, available_at, fetched_at, data_json
    FROM core.fundamentals 
    WHERE fetched_at >= '2026-09-06'
    LIMIT 3
""").fetchall()
for r in rows_cafef:
    print(r[:5], r[5][:300])
