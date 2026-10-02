import sys
import duckdb

sys.path.insert(0, 'src')
from crawlers.crawl_cafef_disclosures import crawl_live_disclosures

sys.stdout.reconfigure(encoding='utf-8')

print("=== [DISCLOSURES] CẬP NHẬT CÔNG BỐ THÔNG TIN LIVE MỚI NHẤT (2026-10-02) ===")
# Cào 10 trang công bố thông tin gần nhất toàn thị trường vào vesta_snapshot.duckdb
n = crawl_live_disclosures(max_pages=10, symbol="", delay=0.5, db_path="d:/VESTA/db/vesta_snapshot.duckdb")
print(f"✅ Hoàn tất cập nhật Disclosures: +{n} bản ghi mới!")
