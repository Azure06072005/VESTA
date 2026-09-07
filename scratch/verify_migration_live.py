import duckdb
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path("d:/VESTA/src")))
from etl import migrations

# Connect in-memory and copy core.fundamentals from production DB
mem_con = duckdb.connect(":memory:")
mem_con.execute("CREATE SCHEMA core")
mem_con.execute("CREATE SCHEMA staging")

print("Attaching production database (read-only)...")
mem_con.execute("ATTACH 'd:/VESTA/db/vesta.duckdb' AS prod (READ_ONLY)")

print("Copying core.fundamentals (179,135 rows) to memory...")
mem_con.execute("CREATE TABLE core.fundamentals AS SELECT * FROM prod.core.fundamentals")
mem_con.execute("DETACH prod")

count_before = mem_con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0]
print(f"Loaded {count_before} rows into memory.")

print("Running migrate_fundamentals_add_source_column()...")
ran = migrations.migrate_fundamentals_add_source_column(mem_con)
print(f"Migration returned: {ran}")

print("\n--- Post-migration verification ---")
res = mem_con.execute("""
    SELECT source, count(*) 
    FROM core.fundamentals 
    GROUP BY source 
    ORDER BY source
""").fetchall()

for src, cnt in res:
    print(f"  source='{src}': {cnt:,} rows")

total_post = sum(cnt for _, cnt in res)
print(f"Total post-migration: {total_post:,} (matches {count_before:,}: {total_post == count_before})")

null_count = mem_con.execute("SELECT count(*) FROM core.fundamentals WHERE source IS NULL").fetchone()[0]
print(f"NULL source count: {null_count}")

# Verify date vs source alignment
align = mem_con.execute("""
    SELECT 
        CAST(fetched_at AS DATE) as fetch_date,
        source,
        count(*)
    FROM core.fundamentals
    GROUP BY 1, 2
    ORDER BY 1, 2
""").fetchall()
print("\n--- Date and source distribution ---")
for dt, src, cnt in align:
    print(f"  Date {dt} | source='{src}' | {cnt:,} rows")

print("\n--- Testing idempotency: running migration second time ---")
ran_second = migrations.migrate_fundamentals_add_source_column(mem_con)
print(f"Second run returned: {ran_second} (expected False)")
res_second = mem_con.execute("SELECT source, count(*) FROM core.fundamentals GROUP BY source ORDER BY source").fetchall()
print(f"Counts after second run identical: {res == res_second}")
