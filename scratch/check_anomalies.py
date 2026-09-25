import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

cnt_before = con.execute("SELECT count(*) FROM preprocessed.macro_policy WHERE published_at < TIMESTAMP '1990-01-01'").fetchone()[0]
cnt_after = con.execute("SELECT count(*) FROM preprocessed.macro_policy WHERE published_at > TIMESTAMP '2026-12-31'").fetchone()[0]
cnt_null = con.execute("SELECT count(*) FROM preprocessed.macro_policy WHERE published_at IS NULL").fetchone()[0]
total = con.execute("SELECT count(*) FROM preprocessed.macro_policy").fetchone()[0]

print(f"Total macro_policy: {total}")
print(f"Before 1990: {cnt_before} ({cnt_before/total*100:.4f}%)")
print(f"After 2026: {cnt_after} ({cnt_after/total*100:.4f}%)")
print(f"NULL: {cnt_null} ({cnt_null/total*100:.4f}%)")

con.close()
