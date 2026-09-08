import duckdb

con1 = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
con2 = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb", read_only=True)

t1 = set(r[0] + "." + r[1] for r in con1.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'meta')").fetchall())
t2 = set(r[0] + "." + r[1] for r in con2.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'meta')").fetchall())

all_tables = sorted(t1 | t2)
header = f"{'Table':<35} | {'vesta.duckdb':<15} | {'latest_backup':<15} | {'Diff':<10}"
print(header)
print("-" * len(header))
for t in all_tables:
    c1 = con1.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if t in t1 else "MISSING"
    c2 = con2.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if t in t2 else "MISSING"
    diff = (c1 - c2) if (isinstance(c1, int) and isinstance(c2, int)) else "N/A"
    print(f"{t:<35} | {str(c1):<15} | {str(c2):<15} | {str(diff):<10}")

con1.close()
con2.close()
