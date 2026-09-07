import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

print("--- Total rows ---")
print("core.fundamentals:", con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0])
print("staging.fundamentals:", con.execute("SELECT count(*) FROM staging.fundamentals").fetchone()[0])

print("\n--- Diagnostic: date split (< 2026-09-06 vs >= 2026-09-06) ---")
print("Fetched before 2026-09-06:", con.execute("SELECT count(*) FROM core.fundamentals WHERE fetched_at < '2026-09-06'").fetchone()[0])
print("Fetched on/after 2026-09-06:", con.execute("SELECT count(*) FROM core.fundamentals WHERE fetched_at >= '2026-09-06'").fetchone()[0])

print("\n--- Diagnostic: exact migration classification condition ---")
res = con.execute("""
    SELECT 
        CASE 
            WHEN fetched_at < '2026-09-06' 
                 OR data_json LIKE '%"BS_%' 
                 OR data_json LIKE '%"IS_%' 
                 OR data_json LIKE '%"CF_%' 
                 OR data_json LIKE '%"RT_%' 
            THEN 'vnstock_data' 
            ELSE 'cafef' 
        END AS classified_source,
        count(*) 
    FROM core.fundamentals 
    GROUP BY 1
""").fetchall()
for r in res:
    print(r)

print("\n--- Breakdown by fetched_at date and prefix match ---")
breakdown = con.execute("""
    SELECT 
        date_trunc('day', fetched_at) as fetch_day,
        (data_json LIKE '%"BS_%' OR data_json LIKE '%"IS_%' OR data_json LIKE '%"CF_%' OR data_json LIKE '%"RT_%') as has_english_prefix,
        count(*)
    FROM core.fundamentals
    GROUP BY 1, 2
    ORDER BY 1, 2
""").fetchall()
for r in breakdown:
    print(r)
