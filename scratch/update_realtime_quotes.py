import sys
import duckdb
import datetime as dt

sys.path.insert(0, 'src')
from crawlers import snapshots

sys.stdout.reconfigure(encoding='utf-8')

print("=== [REALTIME QUOTE] CẬP NHẬT SNAPSHOT BẢNG GIÁ REALTIME (2026-10-02) ===")

con_snap = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb')

# Lấy danh sách VN100
vn100 = [r[0] for r in con_snap.execute("SELECT DISTINCT symbol FROM core.dim_index_constituents WHERE index_code IN ('VN100', 'VN30')").fetchall()]
print(f"Tổng số mã rổ VN100/VN30: {len(vn100)} mã.")

# Gọi snapshots.run với connection tới vesta_snapshot.duckdb
count = snapshots.run(vn100, con=con_snap)
print(f"✅ Hoàn tất cập nhật Realtime Quotes: +{count} bản ghi đã lưu vào core.realtime_quote_snapshot lúc {dt.datetime.now()}!")

con_snap.close()
