import duckdb
import os
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from src.crawlers import snapshots

db_targets = ["db/vesta_snapshot.duckdb", "db/vesta_backup.duckdb"]

con_read = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
all_symbols = [r[0] for r in con_read.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
con_read.close()

print(f"=== BẮT ĐẦU CÀO REALTIME QUOTE SNAPSHOT CHO TOÀN BỘ {len(all_symbols)} MÃ THỊ TRƯỜNG ===")
start_time = time.time()

# 1. Tải toàn bộ dữ liệu từ Vietcap Direct API (đã chunking mượt mà)
raw_df = snapshots.fetch_raw_vietcap(all_symbols)
print(f"✅ Đã tải thành công {len(raw_df)} mã từ Vietcap Direct REST API (thời gian: {time.time() - start_time:.2f}s)!")

# 2. Chuẩn hóa schema theo chuẩn VESTA
norm_df = snapshots.normalize_snapshot(raw_df)
print(f"✅ Đã chuẩn hóa {len(norm_df)} bản ghi snapshot!")

# 3. Ghi vào database snapshot
for target in db_targets:
    if not os.path.exists(target):
        continue
    con = duckdb.connect(target, read_only=False)
    try:
        cnt = snapshots.write_snapshot(norm_df, con=con)
        con.execute("CHECKPOINT;")
        total_now = con.execute("SELECT count(*) FROM core.realtime_quote_snapshot").fetchone()[0]
        max_ts = con.execute("SELECT max(snapshot_at) FROM core.realtime_quote_snapshot").fetchone()[0]
        print(f"🎉 Ghi thành công vào {target}: +{cnt} bản ghi (Tổng hiện tại: {total_now:,} dòng, Mốc thời gian mới nhất: {max_ts})!")
    finally:
        con.close()
