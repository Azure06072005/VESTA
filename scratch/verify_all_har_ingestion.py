import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=True)
sources = ["mof", "gdt", "tienphong", "tuoitre", "vneconomy", "vietstock", "vietnamfinance"]

print(f"{'Source':<18} | {'Total in core.macro_policy':<28} | {'Sample Headline'}")
print("-" * 90)
for s in sources:
    cnt = con.execute(f"SELECT count(*) FROM core.macro_policy WHERE source='{s}'").fetchone()[0]
    sample = con.execute(f"SELECT headline FROM core.macro_policy WHERE source='{s}' ORDER BY fetched_at DESC LIMIT 1").fetchone()
    sample_title = sample[0][:40] if sample else "None"
    print(f"{s:<18} | {cnt:<28,} | {sample_title}")

total_macro = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
print("-" * 90)
print(f"Grand Total in core.macro_policy: {total_macro:,} records")
con.close()
