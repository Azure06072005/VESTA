"""src/crawlers/master_news_crawler.py

VESTA Master Financial, Macro & Policy News Crawler Orchestrator.
Hợp nhất toàn bộ luồng thu thập tin tức tài chính, công bố thông tin và văn bản điều hành:
1. vnstock News: Tin tức doanh nghiệp và công bố thông tin niêm yết theo mã (core.news).
2. CafeF News: Tin tức chi tiết theo từng mã chứng khoán (core.news).
3. CafeF Disclosures: Văn bản công bố thông tin & BCTC PDF (core.cafef_disclosures).
4. Phân vùng chuyên đề & Báo chí tài chính (core.news_resources):
   - CafeF 8 phân vùng, Tin Nhanh Chứng Khoán (TNCK), VnEconomy, Báo Đầu Tư, Tuổi Trẻ,
   - Tiền Phong, Thời báo Ngân hàng, Thời báo Tài chính Việt Nam, Người Quan Sát, VietnamFinance.
5. Cơ quan quản lý & Chính sách điều hành (core.news_resources):
   - Ngân hàng Nhà nước (SBV), Ủy ban Chứng khoán Nhà nước (SSC), Báo Chính Phủ,
   - Báo Nhân Dân, Bộ Tài chính, Bộ Công thương, Thư Viện Pháp Luật.
6. 20+ Hiệp hội ngành nghề chiến lược (core.news_resources):
   - BĐS (HoREA), Thủy sản (VASEP), Ngân hàng (VNBA), Thép (VSA), Dầu khí, Dệt may,
   - Ô tô, Nông sản, Logistics, In ấn, Thương mại điện tử...
7. Quốc tế & Vĩ mô toàn cầu (core.news_resources):
   - Yahoo Finance News & World Bank Macro Series.

Toàn bộ dữ liệu được lưu trữ vào database:
    d:/VESTA/db/vesta_snapshot.duckdb (core.news, core.news_resources, core.cafef_disclosures).

CƠ CHẾ BỎ QUA & BIÊN NGÀY (BOUNDARY MANAGEMENT):
- Bỏ qua mã cổ phiếu đã có đủ tin tức (bật tắt qua cờ --force).
- Tự động nhận diện dải ngày đã cào (ví dụ 2020 - 2026):
  - Ưu tiên 1 (Forward): Cào tiến từ max_date đến hôm nay (2026 - nay).
  - Ưu tiên 2 (Backward): Cào lùi từ min_date về mốc 2000.
  - Bỏ qua dải ngày 2020 - 2026 đã có sẵn trong database.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
import time
from typing import Any, Callable, Dict, List, Optional

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
VENV_SITE = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(1, str(VENV_SITE))

from crawlers.db_writer import ResilientDuckDBWriter, DEFAULT_TARGET_DB
from crawlers.boundary_manager import BoundaryManager
from etl import db

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("master_news_crawler")


# =============================================================================
# REGISTRY PATTERN FOR DYNAMIC NEWS CRAWLERS
# =============================================================================

class NewsCrawlerSpec:
    """Đặc tả thông số của một crawler tin tức hoặc văn bản chính sách."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        runner: Callable[[List[str], ResilientDuckDBWriter, argparse.Namespace], int],
        default_enabled: bool = True,
    ) -> None:
        self.name = name
        self.category = category  # 'equity', 'portals', 'policy', 'associations', 'international'
        self.description = description
        self.runner = runner
        self.default_enabled = default_enabled


NEWS_REGISTRY: Dict[str, NewsCrawlerSpec] = {}


def register_news(name: str, category: str, description: str, default_enabled: bool = True):
    """Decorator để đăng ký thêm crawler tin tức mới vào master orchestrator."""
    def decorator(func: Callable[[List[str], ResilientDuckDBWriter, argparse.Namespace], int]):
        NEWS_REGISTRY[name.lower()] = NewsCrawlerSpec(
            name=name.lower(),
            category=category.lower(),
            description=description,
            runner=func,
            default_enabled=default_enabled,
        )
        return func
    return decorator


# =============================================================================
# 1. EQUITY & COMPANY SPECIFIC NEWS RUNNERS
# =============================================================================

@register_news("vnstock_news", "equity", "vnstock: Tin tức & thông báo doanh nghiệp niêm yết (core.news)")
def run_vnstock_news(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers import vnstock_news
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "news", symbols, force=getattr(args, "force", False), date_column="published_at"
    )
    if not active_symbols:
        logger.info("[vnstock_news] Toàn bộ %d mã đã có tin tức -> BỎ QUA.", len(symbols))
        return 0

    total = 0
    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[vnstock_news] Đang lấy tin tức vnstock cho %s...", sym)
        try:
            n = vnstock_news.run(sym)
            total += n
            logger.info("  -> [OK] %s: +%d tin vnstock.", sym, n)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào tin vnstock cho %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_news("cafef_news", "equity", "CafeF: Tin tức chi tiết theo từng mã chứng khoán (core.news)")
def run_cafef_news(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers import cafef_news
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "news", symbols, force=getattr(args, "force", False), date_column="published_at"
    )
    if not active_symbols:
        logger.info("[cafef_news] Toàn bộ %d mã đã có tin tức -> BỎ QUA.", len(symbols))
        return 0

    total = 0
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "cafef_pages", 5)
    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[cafef_news] Đang lấy tin tức CafeF cho %s (%d trang)...", sym, pages)
        try:
            n = cafef_news.run(sym, max_pages=pages)
            total += n
            logger.info("  -> [OK] %s: +%d tin tức CafeF.", sym, n)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào tin CafeF cho %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_news("cafef_disclosures", "equity", "CafeF: Văn bản công bố thông tin & BCTC PDF (core.cafef_disclosures)")
def run_cafef_disclosures(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.crawl_cafef_disclosures import crawl_disclosures_range
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "disclosure_pages", 10)
    logger.info("[cafef_disclosures] Đang thu thập công bố thông tin doanh nghiệp (%d trang)...", pages)
    try:
        cnt = crawl_disclosures_range(start_page=1, end_page=pages, duckdb_path=writer.target_db)
        logger.info("  -> [OK] CafeF Disclosures: Đã lưu +%d văn bản.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào công bố thông tin: %s", e)
        return 0


# =============================================================================
# 2. FINANCIAL MEDIA & CATEGORY NEWS RUNNERS
# =============================================================================

@register_news("cafef_categories", "portals", "CafeF: 8 phân vùng chuyên đề vĩ mô, TTCK, BĐS, Ngân hàng (core.news & core.news_resources)")
def run_cafef_categories(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.cafef_category_orchestrator import CafeFCategoryOrchestrator
    orchestrator = CafeFCategoryOrchestrator(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.5))
    pages = 1 if getattr(args, "smoke_test", False) else getattr(args, "category_pages", 3)
    logger.info("[cafef_categories] Đang cào 8 phân vùng tin tức CafeF (%d trang/vùng)...", pages)
    try:
        cnt = orchestrator.run_all_zones(pages_per_zone=pages)
        logger.info("  -> [OK] CafeF Category: Đã nạp +%d tin tức ngành.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào danh mục CafeF: %s", e)
        return 0


@register_news("vietstock_news", "portals", "Vietstock: Tin tức tài chính, vĩ mô và doanh nghiệp (core.news & core.news_resources)")
def run_vietstock_news(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.vietstock_crawler import VietstockCrawler
    crawler = VietstockCrawler(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "vietstock_pages", 5)
    logger.info("[vietstock_news] Đang lấy tin tức Vietstock (%d trang)...", pages)
    try:
        cnt = crawler.crawl(max_pages=pages)
        logger.info("  -> [OK] Vietstock News: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Vietstock News: %s", e)
        return 0


@register_news("tinnhanhchungkhoan", "portals", "Tin Nhanh Chứng Khoán: Tin tức thị trường, doanh nghiệp (core.news_resources)")
def run_tinnhanhchungkhoan(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.tinnhanhchungkhoan_crawler import TinNhanhChungKhoanCrawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "tinnhanhchungkhoan", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    crawler = TinNhanhChungKhoanCrawler(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    max_art = 20 if getattr(args, "smoke_test", False) else getattr(args, "limit", 150)
    logger.info("[tinnhanhchungkhoan] Đang lấy bài viết Tin Nhanh Chứng Khoán (tối đa %d tin)...", max_art)
    try:
        now = dt.datetime.now()
        months = [f"{now.year}-{now.month}"]
        cnt = crawler.crawl(months=months, max_articles=max_art)
        logger.info("  -> [OK] TNCK: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Tin Nhanh Chứng Khoán: %s", e)
        return 0


@register_news("vneconomy", "portals", "VnEconomy: Tạp chí kinh tế & chính sách vĩ mô (core.news_resources)")
def run_vneconomy(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.vneconomy_crawler import VnEconomyCrawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "vneconomy", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    crawler = VnEconomyCrawler(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "vneconomy_pages", 5)
    logger.info("[vneconomy] Đang cào tin tức VnEconomy (%d trang)...", pages)
    try:
        cnt = crawler.crawl(max_pages=pages)
        logger.info("  -> [OK] VnEconomy: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào VnEconomy: %s", e)
        return 0


@register_news("thoibaonganhang", "portals", "Thời báo Ngân hàng: Tiền tệ, lãi suất & ngân hàng (core.news_resources)")
def run_thoibaonganhang(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.thoibaonganhang_crawler import ThoiBaoNganHangCrawler
    crawler = ThoiBaoNganHangCrawler(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    pages = 2 if getattr(args, "smoke_test", False) else 5
    logger.info("[thoibaonganhang] Đang cào Thời báo Ngân hàng...")
    try:
        cnt = crawler.crawl(max_pages=pages)
        logger.info("  -> [OK] Thời báo Ngân hàng: +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Thời báo Ngân hàng: %s", e)
        return 0


@register_news("vietnamfinance", "portals", "VietnamFinance: Tạp chí Đầu tư Tài chính (core.news_resources)")
def run_vietnamfinance(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.vietnamfinance_crawler import run_vietnamfinance_crawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "vietnamfinance", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    max_art = 10 if getattr(args, "smoke_test", False) else getattr(args, "limit", 50)
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "vnf_pages", 10)
    logger.info("[vietnamfinance] Đang cào VietnamFinance (tối đa %d bài/chuyên mục)...", max_art)
    try:
        res = run_vietnamfinance_crawler(
            max_articles_per_cat=max_art,
            max_pages_per_cat=pages,
            db_path=writer.target_db,
            delay_seconds=getattr(args, "delay", 0.5),
        )
        cnt = res.get("total_written", 0)
        logger.info("  -> [OK] VietnamFinance: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào VietnamFinance: %s", e)
        return 0


@register_news("thoibaotaichinh", "portals", "Thời báo Tài chính VN: Quản lý tài chính, ngân sách, thuế (core.news_resources)")
def run_thoibaotaichinh(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.thoibaotaichinh_crawler import run_thoibaotaichinh_crawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "thoibaotaichinh", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    max_art = 10 if getattr(args, "smoke_test", False) else getattr(args, "limit", 50)
    offsets = 2 if getattr(args, "smoke_test", False) else getattr(args, "tbtc_offsets", 10)
    logger.info("[thoibaotaichinh] Đang cào Thời báo Tài chính (API offset & sitemap)...")
    try:
        res = run_thoibaotaichinh_crawler(
            max_articles_per_cat=max_art,
            max_offsets=offsets,
            db_path=writer.target_db,
            delay_seconds=getattr(args, "delay", 0.5),
        )
        cnt = res.get("total_written", 0)
        logger.info("  -> [OK] Thời báo Tài chính: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Thời báo Tài chính: %s", e)
        return 0


# =============================================================================
# 3. GOVERNMENT POLICY & REGULATORY AUTHORITIES
# =============================================================================

@register_news("sbv_policy", "policy", "Ngân hàng Nhà nước VN: Thông tư, quyết định lãi suất & tỷ giá (core.news_resources)")
def run_sbv_policy(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.sbv_crawler import crawl_sbv_policy
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "sbv", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    max_items = 20 if getattr(args, "smoke_test", False) else getattr(args, "limit", 100)
    logger.info("[sbv_policy] Đang trích xuất văn bản pháp quy từ Ngân hàng Nhà nước...")
    try:
        cnt = crawl_sbv_policy(max_articles=max_items, duckdb_path=writer.target_db)
        logger.info("  -> [OK] SBV: Đã nạp +%d văn bản chỉ đạo.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào SBV: %s", e)
        return 0


@register_news("ssc_policy", "policy", "Ủy ban Chứng khoán Nhà nước: Quyết định xử phạt, cấp phép & văn bản điều hành (core.news_resources)")
def run_ssc_policy(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.ssc_crawler import SscCrawler
    crawler = SscCrawler(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    pages = 2 if getattr(args, "smoke_test", False) else 5
    logger.info("[ssc_policy] Đang cào văn bản UBCKNN...")
    try:
        cnt = crawler.crawl(max_pages=pages)
        logger.info("  -> [OK] SSC: Đã nạp +%d văn bản pháp quy.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào UBCKNN: %s", e)
        return 0


@register_news("baochinhphu", "policy", "Báo Chính Phủ: Nghị quyết, Nghị định, Quyết định Thủ tướng (core.news_resources)")
def run_baochinhphu(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.baochinhphu_crawler import run_baochinhphu_crawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "baochinhphu", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    max_pages = 2 if getattr(args, "smoke_test", False) else 5
    logger.info("[baochinhphu] Đang thu thập chỉ đạo từ Báo Chính Phủ (%d trang)...", max_pages)
    try:
        res = run_baochinhphu_crawler(max_pages=max_pages, db_path=writer.target_db)
        cnt = res.get("total_written", 0)
        logger.info("  -> [OK] Báo Chính Phủ: +%d bài viết & nghị quyết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Báo Chính Phủ: %s", e)
        return 0


@register_news("nhandan", "policy", "Báo Nhân Dân: Cơ quan ngôn luận Trung ương Đảng, sitemap 2000-2026 (core.news_resources)")
def run_nhandan(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    from crawlers.nhandan_crawler import run_nhandan_crawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    b_info = boundary_mgr.audit_source_date_boundary(
        "news_resources", "nhandan", target_earliest_year=getattr(args, "target_earliest_year", 2000)
    )
    boundary_mgr.print_crawling_strategy(b_info)

    max_art = 20 if getattr(args, "smoke_test", False) else getattr(args, "limit", 100)
    logger.info("[nhandan] Đang cào Báo Nhân Dân (lịch sử sitemap, tối đa %d bài)...", max_art)
    try:
        res = run_nhandan_crawler(
            max_articles=max_art,
            start_year=getattr(args, "nhandan_start_year", 2026),
            end_year=getattr(args, "nhandan_end_year", 2000),
            db_path=writer.target_db,
            delay_seconds=getattr(args, "delay", 0.5),
        )
        cnt = res.get("total_written", 0)
        logger.info("  -> [OK] Báo Nhân Dân: Đã lưu +%d bài viết.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Báo Nhân Dân: %s", e)
        return 0


# =============================================================================
# 4. INDUSTRY ASSOCIATIONS RUNNER
# =============================================================================

@register_news("associations", "associations", "20+ Hiệp hội ngành nghề: BĐS (HoREA), Thủy sản (VASEP), Ngân hàng (VNBA), Thép (VSA)... (core.news_resources)")
def run_associations(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Tập hợp chạy các hiệp hội kinh tế & ngành nghề trọng yếu."""
    total = 0
    days = 7 if getattr(args, "smoke_test", False) else getattr(args, "days", 30)

    # 1. VASEP (Thủy sản)
    try:
        from crawlers.vasep_crawler import VasepCrawler
        vasep = VasepCrawler(duckdb_path=writer.target_db, delay=0.8)
        cnt = vasep.crawl(days_back=days, max_articles=50)
        total += cnt
        logger.info("  -> [OK] VASEP: +%d bài viết.", cnt)
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào VASEP: %s", e)

    # 2. HoREA (Bất động sản)
    try:
        from crawlers.horea_crawler import run_horea_crawler
        res = run_horea_crawler(max_pages=2, db_path=writer.target_db)
        cnt = res.get("total_written", 0)
        total += cnt
        logger.info("  -> [OK] HoREA: +%d kiến nghị chính sách BĐS.", cnt)
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào HoREA: %s", e)

    # 3. VNBA (Hiệp hội Ngân hàng)
    try:
        from crawlers.vnba_crawler import run_vnba_crawler
        res = run_vnba_crawler(max_articles_per_cat=15, db_path=writer.target_db)
        cnt = res.get("total_written", 0)
        total += cnt
        logger.info("  -> [OK] VNBA: +%d bài viết ngành ngân hàng.", cnt)
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào VNBA: %s", e)

    # 4. VSA (Thép Việt Nam)
    try:
        from crawlers.vsa_crawler import run_vsa_crawler
        res = run_vsa_crawler(max_articles_per_cat=15, db_path=writer.target_db)
        cnt = res.get("total_written", 0)
        total += cnt
        logger.info("  -> [OK] VSA: +%d bài viết ngành thép.", cnt)
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào VSA: %s", e)

    return total


# =============================================================================
# 5. INTERNATIONAL MACRO RUNNER
# =============================================================================

@register_news("international", "international", "Yahoo Finance & World Bank: Tin tức tài chính quốc tế & Chỉ số vĩ mô (core.news_resources)")
def run_international(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    total = 0
    # Yahoo Finance
    try:
        from crawlers.unified_macro_crawler import crawl_yahoo_finance
        limit = 30 if getattr(args, "smoke_test", False) else 150
        records = crawl_yahoo_finance(max_articles=limit, all_dates=False)
        if records:
            # Lưu trữ vào core.news_resources qua db_writer (và mirror sang macro_policy)
            def _save_yahoo(con: duckdb.DuckDBPyConnection):
                now = dt.datetime.now(dt.timezone.utc)
                inserted = 0
                for r in records:
                    con.execute("""
                        INSERT OR IGNORE INTO core.news_resources
                        (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r.get("source", "Yahoo Finance"),
                        "Yahoo Editorial",
                        "International News",
                        None,
                        r.get("published_at", now),
                        r.get("available_at", now),
                        r.get("headline", ""),
                        r.get("summary", ""),
                        r.get("body", ""),
                        r.get("source_url", ""),
                        now,
                    ))
                    # Mirror sang macro_policy
                    con.execute("""
                        INSERT OR IGNORE INTO core.macro_policy
                        (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r.get("source", "Yahoo Finance"),
                        "Yahoo Editorial",
                        "International News",
                        None,
                        r.get("published_at", now),
                        r.get("available_at", now),
                        r.get("headline", ""),
                        r.get("summary", ""),
                        r.get("body", ""),
                        r.get("source_url", ""),
                        now,
                    ))
                    inserted += 1
                return inserted

            cnt = writer.execute_with_retry(_save_yahoo)
            total += cnt
            logger.info("  -> [OK] Yahoo Finance: +%d tin tức vĩ mô toàn cầu.", cnt)
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Yahoo Finance: %s", e)

    return total


# =============================================================================
# ORCHESTRATION ENGINE & CLI
# =============================================================================

def sanitize_argv() -> None:
    """Xử lý phòng thủ các trường hợp người dùng gõ '--symbols -all' hoặc '-symbols'."""
    for i in range(1, len(sys.argv)):
        if sys.argv[i - 1] in ("--symbols", "-symbols") and sys.argv[i].startswith("-"):
            val = sys.argv[i].lstrip("-")
            if val.lower() in ("all", "vn30") or "," in val or len(val) == 3:
                sys.argv[i] = val
        elif sys.argv[i] == "-symbols":
            sys.argv[i] = "--symbols"


def parse_args() -> argparse.Namespace:
    sanitize_argv()
    parser = argparse.ArgumentParser(
        description="VESTA Master Financial, Macro & Policy News Crawler Orchestrator"
    )
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn file DuckDB chính")
    parser.add_argument("--symbols", default="VCB,FPT,SSI", help="Danh sách mã cổ phiếu cho tin doanh nghiệp ('vn30', 'all', hoặc mã cụ thể)")
    parser.add_argument("--all", action="store_true", help="Cào toàn bộ mã cổ phiếu trên thị trường (tương đương --symbols all)")
    parser.add_argument("--sources", default="all", help="Danh sách nguồn cào (all hoặc phân tách bởi dấu phẩy)")
    parser.add_argument("--categories", default="all", help="Lọc theo nhóm nguồn: equity, portals, policy, associations, international")
    parser.add_argument("--days", type=int, default=7, help="Khoảng thời gian lấy tin tức (ngày)")
    parser.add_argument("--limit", type=int, default=100, help="Giới hạn số lượng tin tức tối đa mỗi nguồn")
    parser.add_argument("--delay", type=float, default=0.5, help="Thời gian nghỉ giữa các request (giây)")
    parser.add_argument("--smoke-test", action="store_true", help="Chạy thử nghiệm nhanh với số lượng trang tối thiểu")
    parser.add_argument("--force", action="store_true", help="Bắt buộc cào lại toàn bộ, không bỏ qua các mã hoặc dải ngày đã có")
    parser.add_argument("--priority", default="forward", choices=["forward", "backward", "both"], 
                        help="Thứ tự ưu tiên cào: forward (ưu tiên đến hôm nay trước), backward (vét cạn 2000), both (cả hai)")
    parser.add_argument("--target-earliest-year", type=int, default=2000, help="Mốc năm sớm nhất cần cào lùi về (mặc định: 2000)")
    parser.add_argument("--sync", action="store_true", help="Kích hoạt đồng bộ dữ liệu đệm vào database đích")
    parser.add_argument("--list", action="store_true", help="Liệt kê toàn bộ nguồn tin tức đã đăng ký")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if getattr(args, "all", False):
        args.symbols = "all"

    if args.list:
        print("\n" + "=" * 80)
        print("DANH SÁCH CÁC NGUỒN CÀO TIN TỨC & CHÍNH SÁCH ĐÃ ĐĂNG KÝ (NEWS REGISTRY)")
        print("=" * 80)
        for name, spec in NEWS_REGISTRY.items():
            print(f"• [{name:<20}] ({spec.category:<13}): {spec.description}")
        print("=" * 80)
        return 0

    writer = ResilientDuckDBWriter(target_db=args.db)

    if args.sync:
        logger.info("Đang kiểm tra và đồng bộ dữ liệu tin tức từ bộ đệm vào %s...", args.db)
        synced = writer.sync_buffer_to_target()
        logger.info("Đã đồng bộ thành công %d bảng vào database đích.", synced)
        if not args.symbols and args.sources == "none":
            return 0

    raw_symbols = args.symbols.strip()
    if raw_symbols.lower() == "vn30":
        from crawlers.track_crawling_progress import VN30_SYMBOLS
        symbols = VN30_SYMBOLS.copy()
        logger.info(">>> Đã tự động nạp rổ chỉ số VN30 (%d mã) cho tin doanh nghiệp <<<", len(symbols))
    elif raw_symbols.lower() == "all":
        try:
            con = duckdb.connect(writer.target_db, read_only=True)
            df_sym = con.execute("SELECT symbol FROM core.dim_symbol WHERE is_delisted IS NOT TRUE ORDER BY symbol").fetchdf()
            symbols = df_sym["symbol"].tolist()
            con.close()
            logger.info(">>> Đã tự động nạp toàn bộ %d mã từ core.dim_symbol <<<", len(symbols))
        except Exception:
            from crawlers.track_crawling_progress import VN30_SYMBOLS
            symbols = VN30_SYMBOLS.copy()
            logger.info(">>> Không đọc được dim_symbol, fallback về VN30 (%d mã) <<<", len(symbols))
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.smoke_test:
        symbols = symbols[:2]
        logger.info(">>> KÍCH HOẠT CHẾ ĐỘ SMOKE TEST (2 mã: %s) <<<", symbols)

    # Lọc danh sách nguồn theo category và source name
    selected_specs = list(NEWS_REGISTRY.values())

    if args.categories.lower() != "all":
        req_cats = [c.strip().lower() for c in args.categories.split(",") if c.strip()]
        selected_specs = [s for s in selected_specs if s.category in req_cats]

    if args.sources.lower() != "all":
        req_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        selected_specs = [s for s in selected_specs if s.name in req_sources]

    if not selected_specs:
        logger.error("Không có nguồn tin tức nào thỏa mãn tiêu chí lọc: sources=%s, categories=%s", args.sources, args.categories)
        return 1

    logger.info("=" * 80)
    logger.info("KHỞI CHẠY MASTER NEWS CRAWLER (%d nguồn, %d mã cổ phiếu)", len(selected_specs), len(symbols))
    logger.info("Database đích: %s", writer.target_db)
    logger.info("Chế độ ưu tiên: %s (Cào từ %d -> nay)", args.priority.upper(), args.target_earliest_year)
    logger.info("=" * 80)

    start_time = time.time()
    grand_total = 0
    results: Dict[str, int] = {}

    for spec in selected_specs:
        logger.info("\n--- BẮT ĐẦU NGUỒN: %s [%s] ---", spec.name.upper(), spec.category.upper())
        try:
            cnt = spec.runner(symbols, writer, args)
            results[spec.name] = cnt
            grand_total += cnt
        except Exception as e:
            logger.error("Lỗi nghiêm trọng khi chạy nguồn tin tức %s: %s", spec.name, e)
            results[spec.name] = 0

    # Đồng bộ buffer nếu có ghi
    writer.sync_buffer_to_target()

    duration = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("HOÀN TẤT MASTER NEWS CRAWLER TRONG %.2f GIÂY", duration)
    logger.info("Tổng bản ghi tin tức & văn bản nạp thành công: +%d", grand_total)
    for name, cnt in results.items():
        logger.info("  • %-22s: +%d tin/văn bản", name, cnt)
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
