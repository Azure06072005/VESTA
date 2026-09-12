import duckdb
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=True)

print("=== 1. Checking Báo Đầu tư Date Patterns ===")
total_bdt = con.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'baodautu'").fetchone()[0]
sample_bdt = con.execute("SELECT source_url, headline, summary, body FROM core.macro_policy WHERE source = 'baodautu' LIMIT 10").fetchall()

date_regex = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b")
found_bdt = 0
for u, h, s, b in con.execute("SELECT source_url, headline, summary, body FROM core.macro_policy WHERE source = 'baodautu' LIMIT 1000").fetchall():
    text = (s or "") + " " + (b[:300] if b else "")
    if date_regex.search(text):
        found_bdt += 1
print(f"Báo Đầu tư: {found_bdt}/1000 sample articles contain an explicit date in the opening text ({found_bdt/10:.1f}%)")

print("\n=== 2. Checking Thời báo Ngân hàng Date Patterns ===")
total_tbnh = con.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'thoibaonganhang'").fetchone()[0]
found_tbnh = 0
for u, h, s, b in con.execute("SELECT source_url, headline, summary, body FROM core.macro_policy WHERE source = 'thoibaonganhang' LIMIT 1000").fetchall():
    text = (s or "") + " " + (b[:300] if b else "")
    if date_regex.search(text):
        found_tbnh += 1
print(f"Thời báo Ngân hàng: {found_tbnh}/1000 sample articles contain an explicit date in the opening text ({found_tbnh/10:.1f}%)")

print("\n=== 3. Sample Date Extractions ===")
for u, h, s, b in sample_bdt[:3]:
    m = date_regex.search((s or "") + " " + (b[:300] if b else ""))
    print(f"[BDT] {h[:50]} -> Extracted: {m.group(0) if m else 'None'} from {u}")

con.close()
