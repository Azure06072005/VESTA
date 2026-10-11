"""
VESTA Hot Data Tier Builder (Hot vs. Cold Data Tiering)
======================================================
Trích xuất phân tầng dữ liệu nóng (Hot Web DB) từ CSDL lịch sử lạnh (Cold Lakehouse).

Mục tiêu:
- Thu nhỏ toàn bộ 5 CSDL từ ~13 GB xuống < 350 MB để phục vụ triển khai Web & Cloud.
- Loại bỏ hoàn toàn các bảng staging tạm và dữ liệu thừa.
- Giữ đầy đủ:
  + Nến 1D trong 2 năm gần nhất (2024-01-01 -> nay)
  + Nến 1m trong 40 phiên gần nhất (2026-09-01 -> nay)
  + Tin tức trong 4.5 tháng gần nhất (2026-06-01 -> nay)
  + BCTC & Chỉ số tài chính trong 4 năm gần nhất (2022-01-01 -> nay)
  + Thuyết minh BCTC trong 8 quý gần nhất (2024-Q1 -> nay)
  + Dòng tiền ngoại trong ~2 năm (2025-01-01 -> nay)
  + Toàn bộ danh mục chiều (dim_symbol, dim_sector, công ty, cổ đông, F&G, độ rộng)
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
COLD_DB_DIR = REPO_ROOT / "db"
HOT_DB_DIR = REPO_ROOT / "db" / "hot"

# Cấu hình chính sách lưu giữ dữ liệu nóng (Hot Tier Retention Policy)
HOT_POLICY = {
    "ohlcv_daily_start": "2024-01-01",
    "ohlcv_1m_start": "2026-09-01",
    "news_start": "2026-06-01",
    "foreign_flow_start": "2025-01-01",
    "fundamentals_start": "2022-01-01",
    "financial_notes_start": "2024-Q1",
    "events_start": "2024-01-01",
}


def log_step(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_file_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return path.stat().st_size / (1024 * 1024)


def build_hot_ohlcv(cold_dir: Path, hot_dir: Path) -> Path:
    """Xây dựng hot CSDL vesta_ohlcv.duckdb"""
    src_db = cold_dir / "vesta_ohlcv.duckdb"
    dest_db = hot_dir / "vesta_ohlcv.duckdb"
    if dest_db.exists():
        dest_db.unlink()

    log_step(f"Đang xử lý vesta_ohlcv.duckdb (Gốc: {get_file_size_mb(src_db):.1f} MB)...")
    
    con = duckdb.connect(str(dest_db))
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    con.execute(f"ATTACH '{src_db}' AS cold (READ_ONLY);")

    # 1. core.market_ohlcv_daily (>= 2024-01-01)
    log_step("  -> Trích xuất core.market_ohlcv_daily (từ 2024)...")
    con.execute(f"""
        CREATE TABLE core.market_ohlcv_daily AS 
        SELECT * FROM cold.core.market_ohlcv_daily 
        WHERE date >= '{HOT_POLICY['ohlcv_daily_start']}';
    """)

    # 2. core.market_ohlcv_1m (>= 2026-09-01)
    log_step("  -> Trích xuất core.market_ohlcv_1m (từ 2026-09)...")
    con.execute(f"""
        CREATE TABLE core.market_ohlcv_1m AS 
        SELECT * FROM cold.core.market_ohlcv_1m 
        WHERE time >= '{HOT_POLICY['ohlcv_1m_start']}';
    """)

    # 3. meta tables (nếu có)
    try:
        con.execute("CREATE TABLE meta.crawl_progress AS SELECT * FROM cold.meta.crawl_progress;")
    except Exception:
        pass
    try:
        con.execute("CREATE TABLE meta.crawl_progress_1m AS SELECT * FROM cold.meta.crawl_progress_1m;")
    except Exception:
        pass

    con.execute("DETACH cold;")
    con.execute("CHECKPOINT; VACUUM;")
    con.close()

    log_step(f"✅ Hoàn tất vesta_ohlcv.duckdb: {get_file_size_mb(dest_db):.1f} MB")
    return dest_db


def build_hot_market_index(cold_dir: Path, hot_dir: Path) -> Path:
    """Xây dựng hot CSDL vesta_market_index.duckdb"""
    src_db = cold_dir / "vesta_market_index.duckdb"
    dest_db = hot_dir / "vesta_market_index.duckdb"
    if dest_db.exists():
        dest_db.unlink()

    log_step(f"Đang xử lý vesta_market_index.duckdb (Gốc: {get_file_size_mb(src_db):.1f} MB)...")
    
    con = duckdb.connect(str(dest_db))
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    con.execute("CREATE SCHEMA IF NOT EXISTS preprocessed;")
    con.execute(f"ATTACH '{src_db}' AS cold (READ_ONLY);")

    # Sao chép toàn bộ dimension & overview tables
    dimension_tables = [
        "company_overview", "company_shareholders", "dim_icb_hierarchy",
        "dim_index_constituents", "dim_index_metadata", "dim_sector",
        "dim_symbol", "dim_symbol_cafef", "dim_symbol_sector",
        "realtime_quote_snapshot", "market_breadth_series"
    ]
    for tbl in dimension_tables:
        try:
            con.execute(f"CREATE TABLE core.{tbl} AS SELECT * FROM cold.core.{tbl};")
        except Exception as e:
            pass

    # core.market_foreign_flow_daily (>= 2025-01-01)
    log_step("  -> Trích xuất core.market_foreign_flow_daily (từ 2025)...")
    con.execute(f"""
        CREATE TABLE core.market_foreign_flow_daily AS 
        SELECT * FROM cold.core.market_foreign_flow_daily 
        WHERE date >= '{HOT_POLICY['foreign_flow_start']}';
    """)

    # core.market_sentiment_snapshot (>= 2024-01-01)
    con.execute(f"""
        CREATE TABLE core.market_sentiment_snapshot AS 
        SELECT * FROM cold.core.market_sentiment_snapshot 
        WHERE snapshot_date >= '{HOT_POLICY['ohlcv_daily_start']}';
    """)

    # index_valuation_series & macro
    for tbl, d_col in [("index_valuation_series", "report_date"), ("macro_economic_series", "period_date"), ("macro_rates", "date"), ("market_global_equity_daily", "date")]:
        try:
            con.execute(f"""
                CREATE TABLE core.{tbl} AS 
                SELECT * FROM cold.core.{tbl} 
                WHERE "{d_col}" >= '{HOT_POLICY['fundamentals_start']}';
            """)
        except Exception:
            pass

    # preprocessed
    try:
        con.execute("CREATE TABLE preprocessed.market_regimes AS SELECT * FROM cold.preprocessed.market_regimes WHERE date >= '2024-01-01';")
    except Exception:
        pass

    con.execute("DETACH cold;")
    con.execute("CHECKPOINT; VACUUM;")
    con.close()

    log_step(f"✅ Hoàn tất vesta_market_index.duckdb: {get_file_size_mb(dest_db):.1f} MB")
    return dest_db


def build_hot_fundamentals(cold_dir: Path, hot_dir: Path) -> Path:
    """Xây dựng hot CSDL vesta_fundamentals.duckdb"""
    src_db = cold_dir / "vesta_fundamentals.duckdb"
    dest_db = hot_dir / "vesta_fundamentals.duckdb"
    if dest_db.exists():
        dest_db.unlink()

    log_step(f"Đang xử lý vesta_fundamentals.duckdb (Gốc: {get_file_size_mb(src_db):.1f} MB)...")
    
    con = duckdb.connect(str(dest_db))
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS preprocessed;")
    con.execute(f"ATTACH '{src_db}' AS cold (READ_ONLY);")

    # 1. core.fundamentals (>= 2022-01-01)
    log_step("  -> Trích xuất core.fundamentals (từ 2022)...")
    con.execute(f"""
        CREATE TABLE core.fundamentals AS 
        SELECT * FROM cold.core.fundamentals 
        WHERE period_end >= '{HOT_POLICY['fundamentals_start']}';
    """)

    # 2. preprocessed.fundamentals_ratios
    try:
        con.execute(f"""
            CREATE TABLE preprocessed.fundamentals_ratios AS 
            SELECT * FROM cold.preprocessed.fundamentals_ratios 
            WHERE period_end >= '{HOT_POLICY['fundamentals_start']}';
        """)
    except Exception:
        pass

    # 3. core.financial_notes (>= 2024-Q1)
    log_step("  -> Trích xuất core.financial_notes (từ 2024-Q1)...")
    con.execute(f"""
        CREATE TABLE core.financial_notes AS 
        SELECT * FROM cold.core.financial_notes 
        WHERE period >= '{HOT_POLICY['financial_notes_start']}';
    """)

    # 4. core.cafef_disclosures (>= 2025)
    try:
        con.execute(f"""
            CREATE TABLE core.cafef_disclosures AS 
            SELECT * FROM cold.core.cafef_disclosures 
            WHERE published_at >= '{HOT_POLICY['foreign_flow_start']}';
        """)
    except Exception:
        pass

    con.execute("DETACH cold;")
    con.execute("CHECKPOINT; VACUUM;")
    con.close()

    log_step(f"✅ Hoàn tất vesta_fundamentals.duckdb: {get_file_size_mb(dest_db):.1f} MB")
    return dest_db


def build_hot_events(cold_dir: Path, hot_dir: Path) -> Path:
    """Xây dựng hot CSDL vesta_events.duckdb"""
    src_db = cold_dir / "vesta_events.duckdb"
    dest_db = hot_dir / "vesta_events.duckdb"
    if dest_db.exists():
        dest_db.unlink()

    log_step(f"Đang xử lý vesta_events.duckdb (Gốc: {get_file_size_mb(src_db):.1f} MB)...")
    
    con = duckdb.connect(str(dest_db))
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS preprocessed;")
    con.execute(f"ATTACH '{src_db}' AS cold (READ_ONLY);")

    # 1. core.corporate_events (>= 2024)
    con.execute(f"""
        CREATE TABLE core.corporate_events AS 
        SELECT * FROM cold.core.corporate_events 
        WHERE event_date >= '{HOT_POLICY['events_start']}';
    """)

    # 2. core.price_adjustment_events
    try:
        con.execute(f"""
            CREATE TABLE core.price_adjustment_events AS 
            SELECT * FROM cold.core.price_adjustment_events 
            WHERE ex_date >= '{HOT_POLICY['events_start']}';
        """)
    except Exception:
        pass

    # 3. core.pit_events (>= 2025)
    try:
        con.execute(f"""
            CREATE TABLE core.pit_events AS 
            SELECT * FROM cold.core.pit_events 
            WHERE published_at >= '{HOT_POLICY['foreign_flow_start']}';
        """)
    except Exception:
        pass

    con.execute("DETACH cold;")
    con.execute("CHECKPOINT; VACUUM;")
    con.close()

    log_step(f"✅ Hoàn tất vesta_events.duckdb: {get_file_size_mb(dest_db):.1f} MB")
    return dest_db


def build_hot_news(cold_dir: Path, hot_dir: Path) -> Path:
    """Xây dựng hot CSDL vesta_news.duckdb"""
    src_db = cold_dir / "vesta_news.duckdb"
    dest_db = hot_dir / "vesta_news.duckdb"
    if dest_db.exists():
        dest_db.unlink()

    log_step(f"Đang xử lý vesta_news.duckdb (Gốc: {get_file_size_mb(src_db):.1f} MB)...")
    
    con = duckdb.connect(str(dest_db))
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    con.execute(f"ATTACH '{src_db}' AS cold (READ_ONLY);")

    # 1. core.news (>= 2026-06-01)
    log_step("  -> Trích xuất core.news (từ 2026-06)...")
    con.execute(f"""
        CREATE TABLE core.news AS 
        SELECT * FROM cold.core.news 
        WHERE published_at >= '{HOT_POLICY['news_start']}';
    """)

    # 2. core.news_resources
    try:
        con.execute(f"""
            CREATE TABLE core.news_resources AS 
            SELECT * FROM cold.core.news_resources 
            WHERE published_at >= '{HOT_POLICY['news_start']}';
        """)
    except Exception:
        pass

    # 3. core.macro_policy
    try:
        con.execute(f"""
            CREATE TABLE core.macro_policy AS 
            SELECT * FROM cold.core.macro_policy 
            WHERE published_at >= '{HOT_POLICY['ohlcv_daily_start']}';
        """)
    except Exception:
        pass

    # 4. Dimension & Views
    for tbl in ["news_entity_map", "news_relevance_meta", "sector_news_signal"]:
        try:
            con.execute(f"CREATE TABLE core.{tbl} AS SELECT * FROM cold.core.{tbl};")
        except Exception:
            pass

    # Tạo lại views
    con.execute("""
        CREATE OR REPLACE VIEW core.v_stock_news AS 
        SELECT * FROM core.news 
        WHERE symbol IS NOT NULL AND symbol != '';
    """)
    con.execute("""
        CREATE OR REPLACE VIEW core.v_macro_news AS 
        SELECT * FROM core.news 
        WHERE symbol IS NULL OR symbol = '';
    """)

    con.execute("DETACH cold;")
    con.execute("CHECKPOINT; VACUUM;")
    con.close()

    log_step(f"✅ Hoàn tất vesta_news.duckdb: {get_file_size_mb(dest_db):.1f} MB")
    return dest_db


def build_all_hot_databases(cold_dir: Optional[Path] = None, hot_dir: Optional[Path] = None) -> Dict[str, float]:
    """Hàm điều phối toàn diện: Trích xuất và nén 5 CSDL nóng."""
    start_time = time.time()
    cold = cold_dir or COLD_DB_DIR
    hot = hot_dir or HOT_DB_DIR
    hot.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("🚀 BẮT ĐẦU TRÍCH XUẤT PHÂN TẦNG DỮ LIỆU NÓNG (HOT DATA TIER BUILDER)")
    print(f"📂 Thư mục gốc (Cold DB): {cold}")
    print(f"🎯 Thư mục đích (Hot DB):  {hot}")
    print("=" * 75)

    sizes: Dict[str, float] = {}

    build_hot_ohlcv(cold, hot)
    build_hot_market_index(cold, hot)
    build_hot_fundamentals(cold, hot)
    build_hot_events(cold, hot)
    build_hot_news(cold, hot)

    total_cold_mb = sum(get_file_size_mb(cold / f"vesta_{name}.duckdb") for name in ["ohlcv", "market_index", "fundamentals", "events", "news"])
    total_hot_mb = sum(get_file_size_mb(hot / f"vesta_{name}.duckdb") for name in ["ohlcv", "market_index", "fundamentals", "events", "news"])
    savings_pct = (1.0 - (total_hot_mb / total_cold_mb)) * 100 if total_cold_mb > 0 else 0.0

    elapsed = time.time() - start_time

    print("\n" + "=" * 75)
    print("📊 BÁO CÁO TỔNG KẾT PHÂN TẦNG DỮ LIỆU NÓNG (HOT DATA TIER SUMMARY)")
    print("=" * 75)
    for name in ["ohlcv", "market_index", "fundamentals", "events", "news"]:
        c_mb = get_file_size_mb(cold / f"vesta_{name}.duckdb")
        h_mb = get_file_size_mb(hot / f"vesta_{name}.duckdb")
        p = (1.0 - (h_mb / c_mb)) * 100 if c_mb > 0 else 0.0
        print(f"  • vesta_{name:12}.duckdb: {c_mb:8.1f} MB  ->  {h_mb:6.1f} MB (Tiết kiệm {p:5.1f}%)")
    
    print("-" * 75)
    print(f"  🔥 TỔNG DUNG LƯỢNG LẠNH (COLD): {total_cold_mb:8.1f} MB ({total_cold_mb/1024:.2f} GB)")
    print(f"  ✨ TỔNG DUNG LƯỢNG NÓNG (HOT):  {total_hot_mb:8.1f} MB ({total_hot_mb/1024:.2f} GB)")
    print(f"  ⚡ TỶ LỆ TIẾT KIỆM BỘ NHỚ:       {savings_pct:.1f}%")
    print(f"  ⏱️  THỜI GIAN THỰC THI:          {elapsed:.2f} giây")
    print("=" * 75)

    return {"cold_mb": total_cold_mb, "hot_mb": total_hot_mb, "savings_pct": savings_pct}


if __name__ == "__main__":
    build_all_hot_databases()
