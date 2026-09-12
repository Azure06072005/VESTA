"""Master Multi-Site Historical Crawler (All Dates & Max Pages).

Coordinates full-history deep crawls across all major financial portals:
1. Tin Nhanh Chứng Khoán (tinnhanhchungkhoan.vn): All sitemaps 2026 -> 2000 (26 years).
2. Báo Tuổi Trẻ (tuoitre.vn): Deep timeline pagination (Zone 11: Kinh doanh, Zone 89: BĐS) from Page 1,881+.
3. Thời báo Ngân hàng (thoibaonganhang.vn): Infinite scroll across monetary & banking categories.
4. Thời báo Tài chính VN (thoibaotaichinhvietnam.vn): Fiscal & securities articles.

All crawlers write idempotently into `core.macro_policy` with 3-tier DB lock resilience
(fallback to `crawlers_staging.duckdb` if `vesta.duckdb` is locked).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger("run_all_sites_all_dates")


def run_tinnhanhchungkhoan(start_year: int = 2000, end_year: int = 2026, max_articles: int = 0) -> int:
    from crawlers.tinnhanhchungkhoan_crawler import TinNhanhChungKhoanCrawler
    logger.info(f"=== [1/4] Khởi động Tin Nhanh Chứng Khoán ALL DATES ({end_year} -> {start_year}) ===")
    crawler = TinNhanhChungKhoanCrawler(delay=0.35)
    return crawler.crawl(
        all_dates=True,
        start_year=start_year,
        end_year=end_year,
        max_articles=max_articles,
    )


def run_tuoitre(start_page: int = 1881, max_pages: int = 1500, zones: list[int] = [11, 89]) -> int:
    from crawlers.tuoitre_crawler import run_tuoitre_crawler
    logger.info(f"=== [2/4] Khởi động Báo Tuổi Trẻ Deep Crawl (Trang {start_page}+, Zones {zones}) ===")
    res = run_tuoitre_crawler(
        mode="deep",
        start_page=start_page,
        max_pages=max_pages,
        zones=zones,
    )
    return res.get("total_written", 0)


def run_thoibaonganhang(max_pages: int = 200) -> int:
    from crawlers.thoibaonganhang_crawler import ThoiBaoNganHangCrawler
    logger.info(f"=== [3/4] Khởi động Thời báo Ngân hàng (Tối đa {max_pages} trang/chuyên mục) ===")
    crawler = ThoiBaoNganHangCrawler(delay=0.5)
    return crawler.crawl(max_pages=max_pages)


def run_thoibaotaichinh(max_articles: int = 300) -> int:
    from crawlers.thoibaotaichinh_crawler import run_thoibaotaichinh_crawler
    logger.info(f"=== [4/4] Khởi động Thời báo Tài chính Việt Nam ===")
    res = run_thoibaotaichinh_crawler(max_articles=max_articles, delay_seconds=0.6)
    return res.get("total_written", 0)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Master Multi-Site Historical News Crawler")
    parser.add_argument("--sites", nargs="+", default=["tinnhanhchungkhoan", "tuoitre", "thoibaonganhang", "thoibaotaichinh"],
                        help="Danh sách trang cần cào (tinnhanhchungkhoan, tuoitre, thoibaonganhang, thoibaotaichinh)")
    parser.add_argument("--start-year", type=int, default=2000, help="Năm bắt đầu cho sitemap Tin Nhanh CK")
    parser.add_argument("--end-year", type=int, default=2026, help="Năm kết thúc cho sitemap Tin Nhanh CK")
    parser.add_argument("--tuoitre-start-page", type=int, default=1881, help="Trang bắt đầu Tuổi Trẻ")
    parser.add_argument("--tuoitre-pages", type=int, default=1000, help="Số trang tối đa Tuổi Trẻ")
    parser.add_argument("--tbnh-pages", type=int, default=150, help="Số trang Thời báo Ngân hàng")
    parser.add_argument("--tbtc-articles", type=int, default=300, help="Số bài Thời báo Tài chính")
    args = parser.parse_args()

    t0 = time.time()
    results = {}

    for site in args.sites:
        try:
            if site == "tinnhanhchungkhoan":
                c = run_tinnhanhchungkhoan(start_year=args.start_year, end_year=args.end_year, max_articles=0)
                results[site] = c
            elif site == "tuoitre":
                c = run_tuoitre(start_page=args.tuoitre_start_page, max_pages=args.tuoitre_pages, zones=[11, 89])
                results[site] = c
            elif site == "thoibaonganhang":
                c = run_thoibaonganhang(max_pages=args.tbnh_pages)
                results[site] = c
            elif site == "thoibaotaichinh":
                c = run_thoibaotaichinh(max_articles=args.tbtc_articles)
                results[site] = c
        except Exception as e:
            logger.error(f"Lỗi khi cào trang '{site}': {e}", exc_info=True)
            results[site] = 0

    dur = time.time() - t0
    print("\n" + "=" * 65)
    print("MASTER ALL-DATES CRAWLER COMPLETED")
    print("=" * 65)
    total = 0
    for s, count in results.items():
        total += count
        print(f"  - {s:<25}: {count:,} articles written")
    print("-" * 65)
    print(f"TOTAL ARTICLES CRAWLED: {total:,} in {dur/60:.2f} minutes")


if __name__ == "__main__":
    main()
