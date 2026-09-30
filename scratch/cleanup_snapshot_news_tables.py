"""scratch/cleanup_snapshot_news_tables.py

Dọn dẹp các bảng tin tức khỏi vesta_snapshot.duckdb sau khi đã chuyển sang vesta_news.duckdb.
Bảo toàn nguyên vẹn vesta_backup.duckdb.
"""
import sys
import duckdb
import pathlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT_DB_PATH = PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"

print(f"Bắt đầu dọn dẹp các bảng tin tức khỏi {SNAPSHOT_DB_PATH.name}...")

con = duckdb.connect(str(SNAPSHOT_DB_PATH), read_only=False)

# Drop các bảng tin tức đã được chuyển sang vesta_news.duckdb
tables_to_drop = [
    "core.news",
    "core.news_resources",
    "core.sector_news_signal",
    "staging.news",
    "staging.news_resources",
]

for tbl in tables_to_drop:
    print(f" -> DROP TABLE IF EXISTS {tbl}...")
    con.execute(f"DROP TABLE IF EXISTS {tbl};")

# Xóa các job tin tức trong meta.crawl_progress của snapshot để không thừa thãi
del_cnt = con.execute("DELETE FROM meta.crawl_progress WHERE dataset_name IN ('F003', 'F004', 'cafef_news', 'cafef_categories', 'vietstock_news', 'news_macro')").fetchone()
print(f" -> Đã dọn dẹp tiến trình cào tin tức trong meta.crawl_progress.")

print(" -> Thực hiện CHECKPOINT để giải phóng không gian...")
con.execute("CHECKPOINT;")

remaining_tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables ORDER BY table_schema, table_name").fetchall()
print(f"\nCác bảng còn lại trong {SNAPSHOT_DB_PATH.name} ({len(remaining_tables)} bảng):")
for s, t in remaining_tables:
    print(f"  {s}.{t}")

con.close()
print("\nHoàn tất dọn dẹp snapshot database thành công!")
