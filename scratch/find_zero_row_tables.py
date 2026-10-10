import duckdb
import glob
import sys

sys.stdout.reconfigure(encoding="utf-8")

db_files = [
    "db/admin/vesta_ohlcv.duckdb",
    "db/admin/vesta_market_index.duckdb",
    "db/admin/vesta_news.duckdb",
    "db/admin/vesta_fundamentals.duckdb",
    "db/admin/vesta_events.duckdb",
]

print("=== KIỂM TRA CÁC BẢNG CÓ 0 HÀNG (ZERO ROWS) TRONG 5 CSDL NHIỆM VỤ ===")
zero_tables = []
for db_path in db_files:
    try:
        con = duckdb.connect(db_path, read_only=True, config={"access_mode": "read_only"})
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'meta') ORDER BY table_schema, table_name").fetchall()
        print(f"\n📁 CSDL: {db_path}")
        for s, t in tables:
            cnt = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
            if cnt == 0:
                print(f"  ❌ {s}.{t}: 0 rows (TRỐNG)")
                zero_tables.append((db_path, s, t))
            else:
                # print first few non-zero
                pass
        con.close()
    except Exception as e:
        print(f"Error {db_path}: {e}")

print(f"\nTổng số bảng có 0 hàng tìm thấy: {len(zero_tables)}")
