"""Master Crawling Session Runner for VESTA.

Executes comprehensive multi-stage crawling across:
1. CafeF Category News (bridging 2026-08-30 to 2026-09-07 in core.news)
2. Government & Regulatory Directives (baochinhphu, moj, vnanet in core.macro_policy)
3. Financial Media & Macro Portals (tinnhanhchungkhoan, yahoo_finance)

All data is written directly to `d:/VESTA/db/vesta_latest_backup.duckdb`.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import time
from pathlib import Path

import duckdb

# Setup paths and encoding
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from etl import db
from crawlers.cafef_category_orchestrator import run_category_orchestrator
from crawlers import baochinhphu_crawler, tinnhanhchungkhoan_crawler, unified_macro_crawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crawling_session")

DB_PATH = "d:/VESTA/db/vesta_latest_backup.duckdb"


def print_database_status(con: duckdb.DuckDBPyConnection, stage_name: str) -> dict[str, Any]:
    print(f"\n=========================================================================")
    print(f">>> TRẠNG THÁI DATABASE ({stage_name.upper()}) <<<")
    print(f"=========================================================================")
    news_cnt = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    news_max = con.execute("SELECT max(published_at) FROM core.news").fetchone()[0]
    macro_cnt = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    macro_max = con.execute("SELECT max(published_at) FROM core.macro_policy").fetchone()[0]

    print(f"  * core.news         : {news_cnt:7,d} bài viết | Ngày mới nhất: {news_max}")
    print(f"  * core.macro_policy : {macro_cnt:7,d} văn bản/bài | Ngày mới nhất: {macro_max}")
    return {
        "news_cnt": news_cnt,
        "news_max": news_max,
        "macro_cnt": macro_cnt,
        "macro_max": macro_max,
    }


def main() -> None:
    session_start = time.time()
    logger.info("=========================================================================")
    logger.info(">>> KHỞI ĐỘNG PHIÊN CÀO DỮ LIỆU TỔNG HỢP VESTA (ALL DATES & REALTIME) <<<")
    logger.info(f"Target Database: {DB_PATH}")
    logger.info("=========================================================================")

    con = duckdb.connect(DB_PATH, read_only=True)
    before_status = print_database_status(con, "TRƯỚC KHI CÀO")
    con.close()

    results = {}

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 1: Cào gia tăng tin tức CafeF (2026-08-30 -> 2026-09-07)
    # ------------------------------------------------------------------
    print("\n-------------------------------------------------------------------------")
    print(">>> GIAI ĐOẠN 1: CÀO TIN TỨC CHỨNG KHOÁN & DOANH NGHIỆP TỪ CAFEF <<<")
    print("-------------------------------------------------------------------------")
    cafef_categories = [
        "thi-truong-chung-khoan",
        "vi-mo-dau-tu",
        "tai-chinh-ngan-hang",
        "doanh-nghiep",
        "bat-dong-san",
    ]
    try:
        cafef_res = run_category_orchestrator(
            categories=cafef_categories,
            max_pages=4,
            db_path=DB_PATH,
            max_concurrency=1,
        )
        results["cafef_written"] = cafef_res.get("total_written", 0)
        logger.info(f"Hoàn thành Giai đoạn 1 (CafeF): +{results['cafef_written']} bài viết mới vào core.news.")
    except Exception as e:
        logger.error(f"Lỗi khi cào CafeF: {e}")
        results["cafef_written"] = 0

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 2: Cào chỉ đạo điều hành Chính phủ (Báo Chính phủ mới nhất)
    # ------------------------------------------------------------------
    print("\n-------------------------------------------------------------------------")
    print(">>> GIAI ĐOẠN 2: CÀO VĂN BẢN CHỈ ĐẠO CHÍNH PHỦ (BAOCHINHPHU.VN) <<<")
    print("-------------------------------------------------------------------------")
    try:
        bcp_crawler = baochinhphu_crawler.BaoChinhPhuCrawler(duckdb_path=DB_PATH)
        bcp_count = bcp_crawler.crawl(
            categories=["chi-dao-dieu-hanh", "kinh-te/chung-khoan", "kinh-te/ngan-hang"],
            max_pages=2,
        )
        results["baochinhphu_written"] = bcp_count
        logger.info(f"Hoàn thành Giai đoạn 2 (Báo Chính phủ): +{bcp_count} văn bản chỉ đạo mới.")
    except Exception as e:
        logger.error(f"Lỗi khi cào Báo Chính phủ: {e}")
        results["baochinhphu_written"] = 0

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 3: Cào Tin nhanh Chứng khoán (TNCK)
    # ------------------------------------------------------------------
    print("\n-------------------------------------------------------------------------")
    print(">>> GIAI ĐOẠN 3: CÀO TIN NHANH CHỨNG KHOÁN (TINNHANHCHUNGKHOAN.VN) <<<")
    print("-------------------------------------------------------------------------")
    try:
        tnck = tinnhanhchungkhoan_crawler.TinNhanhChungKhoanCrawler(duckdb_path=DB_PATH, delay=0.5)
        tnck_count = tnck.crawl(max_pages=3)
        results["tinnhanhchungkhoan_written"] = tnck_count
        logger.info(f"Hoàn thành Giai đoạn 3 (Tin nhanh CK): +{tnck_count} bài viết mới.")
    except Exception as e:
        logger.error(f"Lỗi khi cào Tin nhanh CK: {e}")
        results["tinnhanhchungkhoan_written"] = 0

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 4: Cào Unified Macro (Yahoo Finance, MOJ, TTXVN)
    # ------------------------------------------------------------------
    print("\n-------------------------------------------------------------------------")
    print(">>> GIAI ĐOẠN 4: CÀO UNIFIED MACRO (YAHOO FINANCE, BỘ TƯ PHÁP, TTXVN) <<<")
    print("-------------------------------------------------------------------------")
    try:
        unified_res = unified_macro_crawler.run_pipeline()
        results["unified_core_inserted"] = unified_res.get("core_new_inserted", 0)
        logger.info(f"Hoàn thành Giai đoạn 4 (Unified Macro): +{results['unified_core_inserted']} bản ghi mới.")
    except Exception as e:
        logger.error(f"Lỗi khi chạy Unified Macro: {e}")
        results["unified_core_inserted"] = 0

    # ------------------------------------------------------------------
    # TỔNG KẾT & KIỂM TOÁN SAU PHIÊN CÀO
    # ------------------------------------------------------------------
    duration = time.time() - session_start
    con = duckdb.connect(DB_PATH, read_only=True)
    after_status = print_database_status(con, "SAU KHI HOÀN TẤT PHIÊN CÀO")
    
    # Check distinct sources count
    total_sources = con.execute("SELECT count(DISTINCT source) FROM core.macro_policy").fetchone()[0]
    orphans_fund = con.execute("SELECT count(DISTINCT symbol) FROM core.fundamentals WHERE symbol NOT IN (SELECT symbol FROM core.dim_symbol)").fetchone()[0]
    orphans_corp = con.execute("SELECT count(DISTINCT symbol) FROM core.corporate_events WHERE symbol NOT IN (SELECT symbol FROM core.dim_symbol)").fetchone()[0]
    con.close()

    net_news = after_status["news_cnt"] - before_status["news_cnt"]
    net_macro = after_status["macro_cnt"] - before_status["macro_cnt"]

    print("\n=========================================================================")
    print(">>> TỔNG KẾT TOÀN DIỆN PHIÊN CÀO DỮ LIỆU <<<")
    print("=========================================================================")
    print(f"  * Thời gian thực thi        : {duration:.2f} giây ({duration/60:.2f} phút)")
    print(f"  * Bài viết core.news mới     : +{net_news:,} bài (Tổng: {after_status['news_cnt']:,})")
    print(f"  * Văn bản core.macro mới     : +{net_macro:,} văn bản (Tổng: {after_status['macro_cnt']:,})")
    print(f"  * Tổng số nguồn vĩ mô        : {total_sources} nguồn/cơ quan")
    print(f"  * Ngày mới nhất core.news   : {after_status['news_max']}")
    print(f"  * Ngày mới nhất core.macro  : {after_status['macro_max']}")
    print(f"  * Kiểm toán Orphan BCTC      : {orphans_fund} (0 = Hoàn hảo)")
    print(f"  * Kiểm toán Orphan Sự kiện   : {orphans_corp} (0 = Hoàn hảo)")
    print("=========================================================================\n")


if __name__ == "__main__":
    main()
