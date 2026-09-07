import duckdb
import glob
import os

print("--- Databases in d:/VESTA/db/ ---")
for p in glob.glob("d:/VESTA/db/*.duckdb") + glob.glob("d:/VESTA/db/**/*.duckdb"):
    sz = os.path.getsize(p) / (1024*1024)
    print(f"{p}: {sz:.2f} MB")

print("\n--- Tables in vesta.duckdb ---")
con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging') ORDER BY 1, 2").fetchall()
for schema, name in tables:
    t = f"{schema}.{name}"
    try:
        cnt = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"{t}: {cnt:,} rows")
    except Exception as e:
        print(f"{t}: {e}")

print("\n--- Checking source breakdown in core.macro_policy (if exists) ---")
try:
    macro_src = con.execute("SELECT source, count(*) FROM core.macro_policy GROUP BY 1 ORDER BY 2 DESC").fetchall()
    for s, c in macro_src:
        print(f"  {s}: {c:,} rows")
except Exception as e:
    print("core.macro_policy query failed:", e)

print("\n--- Checking other databases (vesta_staging.duckdb, etc.) ---")
for p in glob.glob("d:/VESTA/db/*.duckdb"):
    if "vesta.duckdb" in p:
        continue
    con_other = duckdb.connect(p, read_only=True)
    print(f"Tables in {p}:")
    for schema, name in con_other.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging') ORDER BY 1, 2").fetchall():
        cnt = con_other.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
        if cnt > 0:
            print(f"  {schema}.{name}: {cnt:,} rows")
