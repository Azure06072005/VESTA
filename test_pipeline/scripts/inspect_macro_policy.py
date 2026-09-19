import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta.duckdb', read_only=True)
print("=== CORE.MACRO_POLICY SCHEMA ===")
cols = con.execute("PRAGMA table_info('core.macro_policy')").fetchall()
for c in cols:
    print(f" - {c[1]}: {c[2]}")

print("\n=== SAMPLE RECORDS ===")
df = con.execute("SELECT * FROM core.macro_policy LIMIT 10").df()
for i, row in df.iterrows():
    print(f"\n--- RECORD {i+1} ---")
    for k, v in row.items():
        val_str = str(v)
        if len(val_str) > 120:
            val_str = val_str[:120] + "..."
        print(f"  {k}: {val_str}")

con.close()
