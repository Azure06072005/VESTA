import duckdb

con = duckdb.connect('db/vesta.duckdb', read_only=True)
con.execute("ATTACH 'db/crawlers_staging.duckdb' AS stg (READ_ONLY)")

# Check if any article in staging has a longer body than what's in main
diff_body = con.execute("""
    SELECT count(*)
    FROM stg.core.macro_policy s
    JOIN core.macro_policy m ON s.source_url = m.source_url
    WHERE length(s.body) > length(m.body)
""").fetchone()[0]

print(f"Articles where staging has more body text than main: {diff_body}")

# Check sample breakdown of sources in staging vs main
staging_sources = con.execute("SELECT source, count(*) FROM stg.core.macro_policy GROUP BY source ORDER BY count(*) DESC").fetchall()
print("\nBreakdown of crawlers_staging.duckdb core.macro_policy:")
for src, cnt in staging_sources:
    main_cnt = con.execute(f"SELECT count(*) FROM core.macro_policy WHERE source = '{src}'").fetchone()[0]
    print(f"  {src}: {cnt:,} in staging -> {main_cnt:,} in main DB")

con.close()
