"""scratch/execute_lakehouse_mission_split.py

Thực hiện phân tách hồ dữ liệu VESTA thành 5 CSDL chuyên biệt theo đúng nghiệp vụ:
1. vesta_ohlcv.duckdb: Giá nến ngày, nến 1m, sổ lệnh L2, khớp lệnh intraday, timeline giao dịch.
2. vesta_news.duckdb: 1.15M tin tức, bản đồ thực thể (entity map), tín hiệu tin theo ngành, vĩ mô chính sách.
3. vesta_fundamentals.duckdb: Báo cáo tài chính (CĐKT, KQKD, LCTT, Chỉ số tài chính), Thuyết minh BCTC, CBTT CafeF.
4. vesta_events.duckdb: Sự kiện doanh nghiệp, sự kiện điều chỉnh giá/cổ tức, sự kiện Point-in-Time (PIT).
5. vesta_market_index.duckdb: Danh mục mã, rổ chỉ số VN30/VN100, dòng tiền ngoại & tự doanh, độ rộng thị trường, định giá P/E P/B, vĩ mô.

Đồng thời:
- Xóa sạch 100% bảng có 0 dòng trong vesta_ohlcv và vesta_news.
- Tự động tạo bản sao lưu đồng bộ trong db/admin/.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time
import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
DB_DIR = REPO_ROOT / "db"
ADMIN_DIR = DB_DIR / "admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_SNAPSHOT_DB = ADMIN_DIR / "vesta_snapshot.duckdb"
OHLCV_DB = DB_DIR / "vesta_ohlcv.duckdb"
NEWS_DB = DB_DIR / "vesta_news.duckdb"
FUNDAMENTALS_DB = DB_DIR / "vesta_fundamentals.duckdb"
EVENTS_DB = DB_DIR / "vesta_events.duckdb"
MARKET_INDEX_DB = DB_DIR / "vesta_market_index.duckdb"

print("=" * 80)
print("BẮT ĐẦU QUY TRÌNH PHÂN TÁCH 5 CSDL CHUYÊN BIỆT & DỌN DẸP BẢNG 0 DÒNG")
print("=" * 80)

# =============================================================================
# BƯỚC 1: DỌN DẸP BẢNG 0 DÒNG TRONG vesta_ohlcv.duckdb
# =============================================================================
print("\n>>> BƯỚC 1: Dọn dẹp bảng 0 dòng trong vesta_ohlcv.duckdb...")
con_ohlcv = duckdb.connect(str(OHLCV_DB), read_only=False)
tables_ohlcv = con_ohlcv.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema') AND table_type = 'BASE TABLE'
""").fetchall()

dropped_ohlcv = 0
for schema, tbl in tables_ohlcv:
    try:
        cnt = con_ohlcv.execute(f'SELECT count(*) FROM "{schema}"."{tbl}"').fetchone()[0]
        if cnt == 0:
            con_ohlcv.execute(f'DROP TABLE "{schema}"."{tbl}"')
            print(f"  [-] Đã xóa bảng rỗng: {schema}.{tbl}")
            dropped_ohlcv += 1
    except Exception as e:
        print(f"  [!] Lỗi kiểm tra {schema}.{tbl}: {e}")

# Copy thêm intraday_trades và order_book_depth vào ohlcv nếu chưa có
con_ohlcv.execute(f"ATTACH '{SOURCE_SNAPSHOT_DB.as_posix()}' AS src_snap (READ_ONLY);")
for t in ["intraday_trades", "order_book_depth"]:
    try:
        has_t = con_ohlcv.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_schema = 'core' AND table_name = '{t}'").fetchone()[0] > 0
        if not has_t:
            con_ohlcv.execute(f"CREATE TABLE core.{t} AS SELECT * FROM src_snap.core.{t};")
            r_cnt = con_ohlcv.execute(f"SELECT count(*) FROM core.{t}").fetchone()[0]
            print(f"  [+] Đã chuyển bảng vi mô giá {t} vào vesta_ohlcv: {r_cnt:,} dòng.")
    except Exception as ex_t:
        print(f"  [!] Chuyển {t}: {ex_t}")

con_ohlcv.execute("DETACH src_snap;")
con_ohlcv.close()
print(f"  => Hoàn tất ohlcv: Đã xóa {dropped_ohlcv} bảng 0 dòng.")


# =============================================================================
# BƯỚC 2: DỌN DẸP BẢNG 0 DÒNG TRONG vesta_news.duckdb
# =============================================================================
print("\n>>> BƯỚC 2: Dọn dẹp bảng 0 dòng trong vesta_news.duckdb...")
con_news = duckdb.connect(str(NEWS_DB), read_only=False)
tables_news = con_news.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema') AND table_type = 'BASE TABLE'
""").fetchall()

dropped_news = 0
for schema, tbl in tables_news:
    try:
        cnt = con_news.execute(f'SELECT count(*) FROM "{schema}"."{tbl}"').fetchone()[0]
        if cnt == 0:
            con_news.execute(f'DROP TABLE "{schema}"."{tbl}"')
            print(f"  [-] Đã xóa bảng rỗng: {schema}.{tbl}")
            dropped_news += 1
    except Exception as e:
        print(f"  [!] Lỗi kiểm tra {schema}.{tbl}: {e}")

con_news.close()
print(f"  => Hoàn tất news: Đã xóa {dropped_news} bảng 0 dòng.")


# =============================================================================
# BƯỚC 3: TẠO CSDL 3: vesta_fundamentals.duckdb
# =============================================================================
print("\n>>> BƯỚC 3: Khởi tạo vesta_fundamentals.duckdb...")
con_fund = duckdb.connect(str(FUNDAMENTALS_DB), read_only=False)
con_fund.execute(f"ATTACH '{SOURCE_SNAPSHOT_DB.as_posix()}' AS src (READ_ONLY);")
con_fund.execute("CREATE SCHEMA IF NOT EXISTS core; CREATE SCHEMA IF NOT EXISTS preprocessed; CREATE SCHEMA IF NOT EXISTS staging;")

fund_tables = [
    ("core", "fundamentals"),
    ("core", "financial_notes"),
    ("core", "cafef_disclosures"),
    ("preprocessed", "fundamentals_ratios"),
    ("staging", "fundamentals"),
    ("staging", "financial_notes"),
    ("staging", "cafef_disclosures"),
]

for s, t in fund_tables:
    try:
        con_fund.execute(f'CREATE TABLE "{s}"."{t}" AS SELECT * FROM src."{s}"."{t}";')
        cnt = con_fund.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        print(f"  [+] Đã chuyển {s}.{t}: {cnt:,} dòng.")
    except Exception as e:
        print(f"  [!] Bỏ qua {s}.{t}: {e}")

con_fund.execute("DETACH src;")
con_fund.close()
print(f"  => Đã tạo xong vesta_fundamentals.duckdb ({FUNDAMENTALS_DB.stat().st_size / (1024*1024):.2f} MB).")


# =============================================================================
# BƯỚC 4: TẠO CSDL 4: vesta_events.duckdb
# =============================================================================
print("\n>>> BƯỚC 4: Khởi tạo vesta_events.duckdb...")
con_evt = duckdb.connect(str(EVENTS_DB), read_only=False)
con_evt.execute(f"ATTACH '{SOURCE_SNAPSHOT_DB.as_posix()}' AS src (READ_ONLY);")
con_evt.execute("CREATE SCHEMA IF NOT EXISTS core; CREATE SCHEMA IF NOT EXISTS preprocessed; CREATE SCHEMA IF NOT EXISTS staging;")

event_tables = [
    ("core", "corporate_events"),
    ("core", "price_adjustment_events"),
    ("core", "pit_events"),
    ("preprocessed", "events"),
    ("staging", "corporate_events"),
    ("staging", "pit_events"),
]

for s, t in event_tables:
    try:
        con_evt.execute(f'CREATE TABLE "{s}"."{t}" AS SELECT * FROM src."{s}"."{t}";')
        cnt = con_evt.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        print(f"  [+] Đã chuyển {s}.{t}: {cnt:,} dòng.")
    except Exception as e:
        print(f"  [!] Bỏ qua {s}.{t}: {e}")

con_evt.execute("DETACH src;")
con_evt.close()
print(f"  => Đã tạo xong vesta_events.duckdb ({EVENTS_DB.stat().st_size / (1024*1024):.2f} MB).")


# =============================================================================
# BƯỚC 5: TẠO CSDL 5: vesta_market_index.duckdb
# =============================================================================
print("\n>>> BƯỚC 5: Khởi tạo vesta_market_index.duckdb...")
con_mkt = duckdb.connect(str(MARKET_INDEX_DB), read_only=False)
con_mkt.execute(f"ATTACH '{SOURCE_SNAPSHOT_DB.as_posix()}' AS src (READ_ONLY);")
con_mkt.execute("CREATE SCHEMA IF NOT EXISTS core; CREATE SCHEMA IF NOT EXISTS preprocessed; CREATE SCHEMA IF NOT EXISTS staging; CREATE SCHEMA IF NOT EXISTS meta;")

market_tables = [
    # Danh mục & Phân ngành
    ("core", "dim_symbol"),
    ("core", "dim_sector"),
    ("core", "dim_symbol_sector"),
    ("core", "dim_icb_hierarchy"),
    ("core", "dim_index_metadata"),
    ("core", "dim_index_constituents"),
    ("core", "dim_symbol_cafef"),
    ("core", "symbol_exchange_history"),
    # Hồ sơ & Cổ đông
    ("core", "company_overview"),
    ("core", "company_shareholders"),
    # Dòng tiền, Độ rộng & Định giá
    ("core", "market_foreign_flow_daily"),
    ("core", "proprietary_flow"),
    ("core", "market_screener_snapshot"),
    ("core", "market_sentiment_snapshot"),
    ("core", "market_breadth_series"),
    ("core", "index_valuation_series"),
    ("core", "realtime_quote_snapshot"),
    ("core", "stock_research_reports"),
    # Vĩ mô & Quốc tế
    ("core", "macro_rates"),
    ("core", "macro_economic_series"),
    ("core", "market_global_equity_daily"),
    ("preprocessed", "market_regimes"),
    # Meta
    ("meta", "crawl_progress"),
]

for s, t in market_tables:
    try:
        con_mkt.execute(f'CREATE TABLE "{s}"."{t}" AS SELECT * FROM src."{s}"."{t}";')
        cnt = con_mkt.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        print(f"  [+] Đã chuyển {s}.{t}: {cnt:,} dòng.")
    except Exception as e:
        print(f"  [!] Bỏ qua {s}.{t}: {e}")

con_mkt.execute("DETACH src;")
con_mkt.close()
print(f"  => Đã tạo xong vesta_market_index.duckdb ({MARKET_INDEX_DB.stat().st_size / (1024*1024):.2f} MB).")


# =============================================================================
# BƯỚC 6: ĐỒNG BỘ BẢN SAO SANG db/admin/
# =============================================================================
print("\n>>> BƯỚC 6: Đồng bộ bản sao sang db/admin/...")
import shutil
for f_name in ["vesta_fundamentals.duckdb", "vesta_events.duckdb", "vesta_market_index.duckdb", "vesta_ohlcv.duckdb", "vesta_news.duckdb"]:
    src_f = DB_DIR / f_name
    tgt_f = ADMIN_DIR / f_name
    if src_f.exists():
        shutil.copy2(src_f, tgt_f)
        print(f"  [✓] Đã đồng bộ {f_name} sang admin/")

print("\n" + "=" * 80)
print("HOÀN TẤT 100% PHÂN TÁCH 5 CSDL CHUYÊN BIỆT & DỌN DẸP BẢNG 0 DÒNG!")
print("=" * 80)
