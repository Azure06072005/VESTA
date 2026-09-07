import duckdb

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
con.execute("ATTACH 'd:/VESTA/db/crawlers_staging.duckdb' AS staging_db (READ_ONLY);")

missing = con.execute("""
    SELECT count(*) 
    FROM staging_db.core.macro_policy s
    WHERE NOT EXISTS (
        SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url
    )
""").fetchone()[0]

print(f"Missing rows from crawlers_staging: {missing}")

# Check stock research reports in vesta_staging.duckdb
con.execute("ATTACH 'd:/VESTA/db/vesta_staging.duckdb' AS vesta_stg (READ_ONLY);")
missing_reports = con.execute("""
    SELECT count(*) 
    FROM vesta_stg.core.stock_research_reports s
    WHERE NOT EXISTS (
        SELECT 1 FROM core.stock_research_reports m WHERE m.id = s.id
    )
""").fetchone()[0]
print(f"Missing stock_research_reports from vesta_staging: {missing_reports}")
