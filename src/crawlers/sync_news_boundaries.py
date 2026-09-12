"""Master Boundary Sync & Gap Filler Crawler (2000 - Today 2026).

File: src/crawlers/sync_news_boundaries.py
Mục đích:
    1. Kiểm tra min_date và max_date của từng nguồn tin tức trong core.news và core.macro_policy.
    2. Đồng bộ tiến trình tương lai: Cào từ max_date đến hôm nay (2026-09-12).
    3. Đồng bộ vét cạn lịch sử: Cào từ min_date lùi dần về năm 2000 (hoặc giới hạn sớm nhất của server).
    4. Cách ly ghi qua staging DB để không xung đột khóa DuckDB với tiến trình nền đang chạy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
import sys
import time
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger("sync_news_boundaries")

DEFAULT_MAIN_DB = "d:/VESTA/db/vesta.duckdb"
DEFAULT_STAGING_DB = "d:/VESTA/db/staging_sync.duckdb"

# Giới hạn kỹ thuật thực tế (Domain Launch / Inception Date) của từng báo:
# Không thể cào trước thời điểm server/domain ra đời.
DOMAIN_ORIGIN_LIMITS: dict[str, str] = {
    "cafef": "2007-02-01 (Domain đăng ký 2007, bắt đầu lưu trữ số hóa)",
    "tuoitre": "2003-09-10 (Trang 5.004 là bài viết sớm nhất được số hóa trên CMS)",
    "tinnhanhchungkhoan": "2000-01-01 (Sitemap lưu trữ từ thời kỳ đầu TTCK)",
    "ssc": "2004-10-13 (Cổng thông tin điện tử UBCKNN đi vào vận hành)",
    "baochinhphu": "2009-08-01 (Hệ thống CMS điện tử Chính phủ)",
    "vietstock": "2025-09-01 (Endpoint ChannelContentPage giới hạn ~550 trang phân trang)",
    "vneconomy": "2021-05-27 (Kiến trúc CMS hiện tại)",
    "thoibaonganhang": "2026-09-05 (Cần scroll phân trang sâu)",
}


def init_staging_db(staging_db: str = DEFAULT_STAGING_DB, main_db: str = DEFAULT_MAIN_DB) -> None:
    """Khởi tạo schema và nạp dim_symbol vào file staging để cách ly lock hoàn toàn."""
    from etl.db import bootstrap_schema
    con = bootstrap_schema(staging_db)
    try:
        # Nếu chưa có core.dim_symbol trong staging, copy nhanh từ main_db
        con.execute(f"ATTACH '{main_db}' AS main_src (READ_ONLY)")
        con.execute("CREATE OR REPLACE TABLE core.dim_symbol AS SELECT * FROM main_src.core.dim_symbol")
        con.execute("DETACH main_src")
    except Exception as e:
        logger.warning(f"Không thể copy dim_symbol từ {main_db}: {e}")
    con.close()


def audit_sources(main_db: str = DEFAULT_MAIN_DB) -> pd.DataFrame:
    """Kiểm tra toàn bộ min_date, max_date và khoảng trống (gap) của từng nguồn."""
    if not Path(main_db).exists():
        raise FileNotFoundError(f"Không tìm thấy database {main_db}")

    con = duckdb.connect(main_db, read_only=True)
    query = """
    WITH union_news AS (
        SELECT 'core.news' as table_name, source, published_at FROM core.news
        UNION ALL
        SELECT 'core.macro_policy' as table_name, source, published_at FROM core.macro_policy
    )
    SELECT 
        table_name,
        source,
        COUNT(*) as total_articles,
        STRFTIME(MIN(published_at), '%Y-%m-%d %H:%M') as min_date,
        STRFTIME(MAX(published_at), '%Y-%m-%d %H:%M') as max_date
    FROM union_news
    GROUP BY table_name, source
    ORDER BY total_articles DESC
    """
    df = con.execute(query).df()
    con.close()

    def evaluate_gaps(row: pd.Series) -> pd.Series:
        max_d = str(row["max_date"])[:10]
        min_d = str(row["min_date"])[:10]
        
        # Kiểm tra chiều tiến (Forward) tới 2026-09-12
        if max_d >= "2026-09-11":
            fwd_status = "Đạt (Đến hôm nay)"
        else:
            fwd_status = f"Thiếu ({max_d} -> 2026-09-12)"

        # Kiểm tra chiều lùi (Backward) về 2000
        if min_d <= "2000-12-31":
            bwd_status = "Đạt (Đã chạm mốc 2000)"
        else:
            limit_note = DOMAIN_ORIGIN_LIMITS.get(row["source"], "Cần cào lùi về 2000")
            bwd_status = f"Cần lùi ({min_d} -> 2000) [Giới hạn: {limit_note}]"

        return pd.Series([fwd_status, bwd_status], index=["forward_gap", "backward_gap"])

    df[["forward_gap", "backward_gap"]] = df.apply(evaluate_gaps, axis=1)
    return df


def run_forward_catchup(sources: list[str] | None = None, staging_db: str = DEFAULT_STAGING_DB) -> dict[str, int]:
    """Cào bù tin tức mới nhất từ max_date đến hôm nay (2026-09-12)."""
    init_staging_db(staging_db)
    results: dict[str, int] = {}
    target_sources = set(sources) if sources else {"cafef", "vietstock", "tuoitre", "baochinhphu", "vneconomy", "thoibaonganhang"}

    # 1. CafeF Forward (2026-09-07 -> 2026-09-12)
    if "cafef" in target_sources:
        try:
            logger.info("=== [FORWARD] Cào CafeF danh mục (10 trang mới nhất đến hôm nay) ===")
            from crawlers.cafef_category_orchestrator import run_category_orchestrator
            res = run_category_orchestrator(
                categories=["thi-truong-chung-khoan", "tai-chinh-ngan-hang", "doanh-nghiep", "bat-dong-san", "vi-mo-dau-tu"],
                max_pages=10,
                db_path=staging_db,
                max_concurrency=2,
            )
            results["cafef"] = res.get("total_written", 0)
        except Exception as e:
            logger.error(f"Lỗi forward crawl CafeF: {e}")
            results["cafef"] = 0

    # 2. Vietstock Forward (2026-09-09 -> 2026-09-12)
    if "vietstock" in target_sources:
        try:
            logger.info("=== [FORWARD] Cào Vietstock (5 trang mới nhất đến hôm nay) ===")
            from crawlers.vietstock_crawler import VietstockCrawler
            v_crawler = VietstockCrawler(db_path=staging_db, request_delay=0.6)
            records = v_crawler.crawl(max_pages=5)
            results["vietstock"] = len(records)
        except Exception as e:
            logger.error(f"Lỗi forward crawl Vietstock: {e}")
            results["vietstock"] = 0

    # 3. Tuổi Trẻ Forward
    if "tuoitre" in target_sources:
        try:
            logger.info("=== [FORWARD] Cào Tuổi Trẻ (5 trang mới nhất) ===")
            from crawlers.tuoitre_crawler import run_tuoitre_crawler
            res_tt = run_tuoitre_crawler(
                mode="deep",
                start_page=1,
                max_pages=5,
                zones=[11, 89, 3],
                db_path=staging_db,
            )
            results["tuoitre"] = res_tt.get("total_written", 0)
        except Exception as e:
            logger.error(f"Lỗi forward crawl Tuổi Trẻ: {e}")
            results["tuoitre"] = 0

    # 4. VnEconomy Forward (2026-09-09 -> 2026-09-12)
    if "vneconomy" in target_sources:
        try:
            logger.info("=== [FORWARD] Cào VnEconomy (5 trang mới nhất) ===")
            from crawlers.vneconomy_crawler import VnEconomyCrawler
            vne_crawler = VnEconomyCrawler(duckdb_path=staging_db, delay=1.0)
            res_vne = vne_crawler.crawl(max_pages=5)
            results["vneconomy"] = res_vne
        except Exception as e:
            logger.error(f"Lỗi forward crawl VnEconomy: {e}")
            results["vneconomy"] = 0

    # 5. Thời báo Ngân hàng Forward
    if "thoibaonganhang" in target_sources:
        try:
            logger.info("=== [FORWARD] Cào Thời báo Ngân hàng (10 trang mới nhất) ===")
            from crawlers.thoibaonganhang_crawler import ThoiBaoNganHangCrawler
            tbnh_crawler = ThoiBaoNganHangCrawler(duckdb_path=staging_db, delay=0.6)
            res_tbnh = tbnh_crawler.crawl(max_pages=10)
            results["thoibaonganhang"] = res_tbnh
        except Exception as e:
            logger.error(f"Lỗi forward crawl Thời báo Ngân hàng: {e}")
            results["thoibaonganhang"] = 0

    return results


def run_backward_backfill(sources: list[str] | None = None, staging_db: str = DEFAULT_STAGING_DB) -> dict[str, int]:
    """Cào vét ngược lịch sử từ min_date về năm 2000."""
    init_staging_db(staging_db)
    results: dict[str, int] = {}
    target_sources = set(sources) if sources else {"tuoitre", "thoibaonganhang"}

    # 1. Tuổi Trẻ: Lùi từ trang 4,200 về trang 5,004 (2006 -> 2003)
    if "tuoitre" in target_sources:
        try:
            logger.info("=== [BACKWARD] Cào Báo Tuổi Trẻ vét cạn trang 4,200 đến 5,004 (2006 -> 2003) ===")
            from crawlers.tuoitre_crawler import run_tuoitre_crawler
            res_tt = run_tuoitre_crawler(
                mode="deep",
                start_page=4200,
                max_pages=805,  # 4200 + 805 = 5005
                zones=[11, 89],
                db_path=staging_db,
            )
            results["tuoitre"] = res_tt.get("total_written", 0)
        except Exception as e:
            logger.error(f"Lỗi backward crawl Tuổi Trẻ: {e}")
            results["tuoitre"] = 0

    # 2. Thời báo Ngân hàng: Cào 150 trang lịch sử
    if "thoibaonganhang" in target_sources:
        try:
            logger.info("=== [BACKWARD] Cào Thời báo Ngân hàng phân trang lịch sử (150 trang) ===")
            from crawlers.thoibaonganhang_crawler import ThoiBaoNganHangCrawler
            tbnh = ThoiBaoNganHangCrawler(duckdb_path=staging_db, delay=0.5)
            cnt = tbnh.crawl(max_pages=150)
            results["thoibaonganhang"] = cnt
        except Exception as e:
            logger.error(f"Lỗi backward crawl TBNH: {e}")
            results["thoibaonganhang"] = 0

    return results


def merge_staging_to_main(staging_db: str = DEFAULT_STAGING_DB, main_db: str = DEFAULT_MAIN_DB) -> dict[str, int]:
    """Gộp dữ liệu từ file staging vào main vesta.duckdb an toàn và khử trùng lặp."""
    if not Path(staging_db).exists():
        logger.info(f"Không có file staging {staging_db} để merge.")
        return {"news_merged": 0, "macro_merged": 0}

    con = duckdb.connect(main_db, read_only=False)
    con.execute(f"ATTACH '{staging_db}' AS stg (READ_ONLY)")

    # 1. Merge core.news nếu có
    news_merged = 0
    try:
        res = con.execute("""
            INSERT OR IGNORE INTO core.news 
            SELECT * FROM stg.core.news
        """)
        row = con.execute("SELECT changes()").fetchone()
        news_merged = row[0] if row else 0
        logger.info(f"Đã merge {news_merged} bài viết vào core.news.")
    except Exception as e:
        logger.warning(f"Bỏ qua merge core.news ({e})")

    # 2. Merge core.macro_policy nếu có
    macro_merged = 0
    try:
        con.execute("""
            INSERT INTO core.macro_policy (
                source, issuing_body, doc_type, doc_number,
                published_at, available_at, headline, summary,
                body, source_url, fetched_at
            )
            SELECT 
                source, issuing_body, doc_type, doc_number,
                published_at, available_at, headline, summary,
                body, source_url, fetched_at
            FROM stg.core.macro_policy
            ON CONFLICT (source_url) DO UPDATE SET
                headline = EXCLUDED.headline,
                summary = EXCLUDED.summary,
                body = EXCLUDED.body,
                fetched_at = EXCLUDED.fetched_at
        """)
        row = con.execute("SELECT changes()").fetchone()
        macro_merged = row[0] if row else 0
        logger.info(f"Đã merge {macro_merged} bài viết vào core.macro_policy.")
    except Exception as e:
        logger.warning(f"Bỏ qua merge core.macro_policy ({e})")

    con.execute("DETACH stg")
    con.close()
    return {"news_merged": news_merged, "macro_merged": macro_merged}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Master Boundary Sync & Gap Filler Crawler (2000 - 2026)")
    parser.add_argument("--audit", action="store_true", help="Chỉ kiểm tra và in bảng báo cáo min/max date")
    parser.add_argument("--forward", action="store_true", help="Cào từ max_date đến hôm nay (2026-09-12)")
    parser.add_argument("--backward", action="store_true", help="Cào từ min_date lùi về năm 2000")
    parser.add_argument("--merge", action="store_true", help="Merge dữ liệu từ staging DB vào vesta.duckdb")
    parser.add_argument("--sources", nargs="+", help="Danh sách nguồn chỉ định")
    parser.add_argument("--main-db", default=DEFAULT_MAIN_DB, help="Đường dẫn vesta.duckdb chính")
    parser.add_argument("--staging-db", default=DEFAULT_STAGING_DB, help="Đường dẫn staging DuckDB")
    args = parser.parse_args()

    if args.audit or (not args.forward and not args.backward and not args.merge):
        df_audit = audit_sources(args.main_db)
        print("\n" + "=" * 105)
        print("BẢNG ĐÁNH GIÁ PHẠM VI DỮ LIỆU TIN TỨC (MIN DATE - MAX DATE - GAPS)")
        print("=" * 105)
        print(df_audit.to_string(index=False))
        print("=" * 105)
        return

    if args.forward:
        logger.info("Bắt đầu chiến dịch Forward Catch-Up...")
        res_fwd = run_forward_catchup(sources=args.sources, staging_db=args.staging_db)
        print("Kết quả Forward:", res_fwd)

    if args.backward:
        logger.info("Bắt đầu chiến dịch Backward Backfill...")
        res_bwd = run_backward_backfill(sources=args.sources, staging_db=args.staging_db)
        print("Kết quả Backward:", res_bwd)

    if args.merge:
        logger.info("Bắt đầu gộp dữ liệu staging vào main database...")
        res_merge = merge_staging_to_main(staging_db=args.staging_db, main_db=args.main_db)
        print("Kết quả Merge:", res_merge)


if __name__ == "__main__":
    main()
