import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("=== DANH SÁCH TẤT CẢ CÁC BẢNG TRONG vesta_snapshot.duckdb ===")
tables = con.execute("""
    SELECT table_schema, table_name, table_type 
    FROM information_schema.tables 
    WHERE table_schema IN ('core', 'staging', 'meta') 
    ORDER BY table_schema, table_name
""").fetchall()

for s, n, t in tables:
    try:
        cnt = con.execute(f"SELECT COUNT(*) FROM {s}.{n}").fetchone()[0]
        print(f"  {s}.{n:35s} ({t}): {cnt:>12,d} rows")
    except Exception as e:
        print(f"  {s}.{n:35s} ({t}): LỖI -> {e}")

print("\n=== SCHEMA BẢNG meta.crawl_progress ===")
cols = con.execute("PRAGMA table_info('meta.crawl_progress')").fetchall()
for c in cols:
    print(f"  Col: {c[1]:20s} | Type: {c[2]:15s}")

print("\n=== THỐNG KÊ LỖI TRONG meta.crawl_progress ===")
failed_summary = con.execute("""
    SELECT dataset_name, status, COUNT(*)
    FROM meta.crawl_progress
    GROUP BY dataset_name, status
    ORDER BY dataset_name, COUNT(*) DESC
""").fetchall()

for d, st, cnt in failed_summary:
    print(f"  Dataset: {d:25s} | Status: {st:15s} | Count: {cnt:>8,d}")

con.close()
