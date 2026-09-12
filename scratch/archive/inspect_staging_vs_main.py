import duckdb

con_staging = duckdb.connect('db/crawlers_staging.duckdb', read_only=True)
tables = con_staging.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'main')").fetchall()
print("Tables in crawlers_staging.duckdb:")
for s, t in tables:
    cnt = con_staging.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
    print(f"  {s}.{t}: {cnt:,}")

total_core = con_staging.execute("SELECT count(distinct source_url) FROM core.macro_policy").fetchone()[0]
total_staging = con_staging.execute("SELECT count(distinct source_url) FROM staging.macro_policy").fetchone()[0]
print(f"Distinct URLs in crawlers_staging core.macro_policy: {total_core:,}")
print(f"Distinct URLs in crawlers_staging staging.macro_policy: {total_staging:,}")
con_staging.close()

con_comp = duckdb.connect('db/vesta.duckdb', read_only=True)
main_macro_count = con_comp.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
print(f"Total in vesta.duckdb core.macro_policy: {main_macro_count:,}")

con_comp.execute("ATTACH 'db/crawlers_staging.duckdb' AS stg (READ_ONLY)")

unmerged_core = con_comp.execute("""
    SELECT count(*) FROM stg.core.macro_policy s
    WHERE NOT EXISTS (
        SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url
    )
""").fetchone()[0]

unmerged_staging = con_comp.execute("""
    SELECT count(*) FROM stg.staging.macro_policy s
    WHERE NOT EXISTS (
        SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url
    )
""").fetchone()[0]

print(f"Unmerged URLs from stg.core.macro_policy into main core.macro_policy: {unmerged_core:,}")
print(f"Unmerged URLs from stg.staging.macro_policy into main core.macro_policy: {unmerged_staging:,}")

# Also check backup DB
con_comp.execute("ATTACH 'db/vesta_latest_backup.duckdb' AS bkp (READ_ONLY)")
unmerged_bkp_core = con_comp.execute("""
    SELECT count(*) FROM stg.core.macro_policy s
    WHERE NOT EXISTS (
        SELECT 1 FROM bkp.core.macro_policy m WHERE m.source_url = s.source_url
    )
""").fetchone()[0]
unmerged_bkp_staging = con_comp.execute("""
    SELECT count(*) FROM stg.staging.macro_policy s
    WHERE NOT EXISTS (
        SELECT 1 FROM bkp.core.macro_policy m WHERE m.source_url = s.source_url
    )
""").fetchone()[0]
print(f"Unmerged URLs from stg.core.macro_policy into backup core.macro_policy: {unmerged_bkp_core:,}")
print(f"Unmerged URLs from stg.staging.macro_policy into backup core.macro_policy: {unmerged_bkp_staging:,}")

con_comp.close()
