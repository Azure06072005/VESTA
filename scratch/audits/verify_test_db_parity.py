import duckdb

con_prod = duckdb.connect("db/vesta.duckdb", read_only=True)
con_test = duckdb.connect("db/vesta_test.duckdb", read_only=True)

tables_prod = set(con_prod.execute("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall())
tables_test = set(con_test.execute("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall())

print(f"Tables in Prod: {len(tables_prod)}, Tables in Test: {len(tables_test)}")
assert tables_prod == tables_test, "Mismatch in tables!"

mismatches = []
for (tbl,) in sorted(tables_prod):
    c_prod = con_prod.execute(f'SELECT count(*) FROM {tbl}').fetchone()[0]
    c_test = con_test.execute(f'SELECT count(*) FROM {tbl}').fetchone()[0]
    if c_prod != c_test:
        mismatches.append((tbl, c_prod, c_test))
    else:
        print(f"  {tbl}: {c_prod:,} rows (MATCH)")

con_prod.close()
con_test.close()

if mismatches:
    print(f"MISMATCHES FOUND: {mismatches}")
else:
    print("\nPERFECT 100% PARITY CONFIRMED ACROSS ALL TABLES!")
