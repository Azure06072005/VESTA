import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=True)
print("--- Database Verification for GDT & MOF ---")
gdt_cnt = con.execute("SELECT count(*) FROM core.macro_policy WHERE source='gdt'").fetchone()[0]
mof_cnt = con.execute("SELECT count(*) FROM core.macro_policy WHERE source='mof'").fetchone()[0]
print(f"GDT records in core.macro_policy: {gdt_cnt}")
print(f"MOF records in core.macro_policy: {mof_cnt}")

print("\n--- Sample GDT Record ---")
row_gdt = con.execute("SELECT headline, published_at, length(body) FROM core.macro_policy WHERE source='gdt' LIMIT 1").fetchone()
if row_gdt:
    print("Headline:", row_gdt[0])
    print("Date:", row_gdt[1])
    print("Body Length:", row_gdt[2])

print("\n--- Sample MOF Record ---")
row_mof = con.execute("SELECT headline, published_at, length(body) FROM core.macro_policy WHERE source='mof' LIMIT 1").fetchone()
if row_mof:
    print("Headline:", row_mof[0])
    print("Date:", row_mof[1])
    print("Body Length:", row_mof[2])

con.close()
