"""src/crawlers/master_fundamentals_crawler.py

VESTA Master Fundamentals & Quantitative Numeric Crawler Orchestrator.
Hợp nhất toàn bộ luồng thu thập dữ liệu cơ bản & định lượng số học vào một script tổng:
1. vnstock Fundamentals: Cân đối kế toán, KQKD, Lưu chuyển tiền tệ, Chỉ số tài chính.
2. CafeF Finance Enhancer: Báo cáo tài chính & chỉ số chuyên sâu từ web API CafeF.
3. Vietstock Finance Enhancer: Báo cáo phân tích CTCK, Giá mục tiêu, Khuyến nghị Mua/Bán.
4. Financial Notes: Thuyết minh báo cáo tài chính chi tiết (FVTPL, cơ cấu nợ, nợ xấu).
5. Corporate Events: Lịch sự kiện doanh nghiệp, chia cổ tức tiền mặt & cổ phiếu, ĐHCĐ.
6. Proprietary Flow: Dòng tiền tự doanh các công ty chứng khoán.
7. Foreign Flow: Giao dịch khối ngoại mua/bán ròng và tỷ lệ sở hữu (foreign room).
8. Macro Rates: Lãi suất liên ngân hàng (Overnight, 1W, 1M) & Lợi suất TPCP VN10Y.
9. Market OHLCV: Dữ liệu giá & khối lượng giao dịch lịch sử.

Toàn bộ dữ liệu được tự động định tuyến và lưu trữ vào database:
    d:/VESTA/db/vesta_snapshot.duckdb (kèm cơ chế lock-resilient & buffer sync).

CƠ CHẾ MỞ RỘNG (IMPORT NGUỒN MỚI):
Khi có crawler mới, chỉ cần import class/hàm và sử dụng decorator:
    @register_fundamental(name="ten_nguon", description="Mô tả nguồn")
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
logger = logging.getLogger("master_fundamentals_crawler")


# =============================================================================
# REGISTRY PATTERN FOR DYNAMIC CRAWLER EXTENSION
# =============================================================================

class FundamentalCrawlerSpec:
    """Quy chuẩn một mô-đun cào dữ liệu cơ bản/định lượng."""

    def __init__(
        self,
        name: str,
        description: str,
        runner: Callable[[List[str], ResilientDuckDBWriter, argparse.Namespace], int],
        default_enabled: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.runner = runner
        self.default_enabled = default_enabled


FUNDAMENTAL_REGISTRY: Dict[str, FundamentalCrawlerSpec] = {}


def register_fundamental(name: str, description: str, default_enabled: bool = True):
    """Decorator để đăng ký thêm nguồn cào dữ liệu cơ bản mới vào hệ thống."""
    def decorator(func: Callable[[List[str], ResilientDuckDBWriter, argparse.Namespace], int]):
        FUNDAMENTAL_REGISTRY[name.lower()] = FundamentalCrawlerSpec(
            name=name.lower(),
            description=description,
            runner=func,
            default_enabled=default_enabled,
        )
        return func
    return decorator


# =============================================================================
# BUILT-IN FUNDAMENTAL RUNNERS
# =============================================================================

@register_fundamental("vnstock_fundamentals", "vnstock: Bảng CĐKT, KQKD, LCTT, Ratios (core.fundamentals)")
def run_vnstock_fundamentals(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào BCTC & chỉ số tài chính từ vnstock_data."""
    from crawlers import fundamentals
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "fundamentals", symbols, force=getattr(args, "force", False), date_column="period_end"
    )
    if not active_symbols:
        logger.info("[vnstock_fundamentals] Toàn bộ %d mã đã có dữ liệu BCTC -> BỎ QUA.", len(symbols))
        return 0

    total = 0
    report_type = getattr(args, "report_type", "all")
    period = getattr(args, "period", "quarter")

    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[vnstock_fundamentals] Đang lấy BCTC cho %s (period=%s)...", sym, period)
        try:
            n = fundamentals.run(sym, report_type=report_type, period=period)
            total += n
            logger.info("  -> [OK] %s: +%d bản ghi BCTC vnstock.", sym, n)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào BCTC vnstock cho %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_fundamental("cafef_finance", "CafeF Web API: BCTC chi tiết & Financial Indicators (core.fundamentals)")
def run_cafef_finance(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào BCTC chuyên sâu từ web API CafeF."""
    from crawlers.cafef_finance_enhancer import CafeFFinanceEnhancer
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "fundamentals", symbols, force=getattr(args, "force", False), date_column="period_end"
    )
    if not active_symbols:
        logger.info("[cafef_finance] Toàn bộ %d mã đã có dữ liệu BCTC -> BỎ QUA.", len(symbols))
        return 0

    enhancer = CafeFFinanceEnhancer(duckdb_path=writer.target_db, delay=getattr(args, "delay", 0.8))
    total = 0

    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[cafef_finance] Đang nạp BCTC CafeF cho %s...", sym)
        try:
            cnt = enhancer.enhance_symbol(sym, page_size=getattr(args, "limit_quarters", 4))
            total += cnt
            logger.info("  -> [OK] %s: +%d báo cáo CafeF.", sym, cnt)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào CafeF cho %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.8))
    return total


@register_fundamental("vietstock_finance", "Vietstock: Báo cáo phân tích CTCK, Target Price (core.stock_research_reports)")
def run_vietstock_finance(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào báo cáo phân tích và khuyến nghị giá mục tiêu từ Vietstock Finance."""
    from crawlers.vietstock_finance_enhancer import VietstockFinanceEnhancer
    enhancer = VietstockFinanceEnhancer(duckdb_path=writer.target_db, delay=getattr(args, "delay", 1.0))
    pages = 2 if getattr(args, "smoke_test", False) else getattr(args, "pages", 5)
    logger.info("[vietstock_finance] Khởi chạy cào %d trang báo cáo phân tích...", pages)
    try:
        cnt = enhancer.crawl(max_pages=pages)
        logger.info("  -> [OK] Vietstock: Đã lưu +%d báo cáo phân tích.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào Vietstock Finance: %s", e)
        return 0


@register_fundamental("financial_notes", "vnstock: Thuyết minh BCTC chi tiết - FVTPL, nợ vay, nợ xấu (core.financial_notes)")
def run_financial_notes(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào thuyết minh báo cáo tài chính từ vnstock note()."""
    from crawlers.financial_notes import FinancialNotesCrawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "financial_notes", symbols, force=getattr(args, "force", False), date_column="fetched_at"
    )
    if not active_symbols:
        logger.info("[financial_notes] Toàn bộ %d mã đã có thuyết minh BCTC -> BỎ QUA.", len(symbols))
        return 0

    crawler = FinancialNotesCrawler(db_path=writer.target_db)
    total = 0

    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[financial_notes] Đang lấy thuyết minh BCTC cho %s...", sym)
        try:
            cnt = crawler.crawl_symbol(sym)
            total += cnt
            logger.info("  -> [OK] %s: +%d mục thuyết minh tài chính.", sym, cnt)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào thuyết minh cho %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_fundamental("corporate_events", "vnstock: Sự kiện quyền, cổ tức, ĐHCĐ (core.corporate_events)")
def run_corporate_events(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào sự kiện doanh nghiệp và cổ tức."""
    from crawlers import corporate_events
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "corporate_events", symbols, force=getattr(args, "force", False), date_column="fetched_at"
    )
    if not active_symbols:
        logger.info("[corporate_events] Toàn bộ %d mã đã có sự kiện quyền -> BỎ QUA.", len(symbols))
        return 0

    total = 0
    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[corporate_events] Đang lấy sự kiện cổ tức cho %s...", sym)
        try:
            n = corporate_events.run(sym)
            total += n
            logger.info("  -> [OK] %s: +%d sự kiện doanh nghiệp.", sym, n)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào sự kiện doanh nghiệp %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_fundamental("proprietary_flow", "Dòng tiền Khối Tự Doanh CTCK hàng ngày (core.proprietary_flow)")
def run_proprietary_flow(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào giao dịch tự doanh công ty chứng khoán."""
    from crawlers.proprietary_flow import ProprietaryFlowCrawler
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "proprietary_flow", symbols, force=getattr(args, "force", False), date_column="date"
    )
    if not active_symbols:
        logger.info("[proprietary_flow] Toàn bộ %d mã đã có dòng tiền tự doanh -> BỎ QUA.", len(symbols))
        return 0

    crawler = ProprietaryFlowCrawler(db_path=writer.target_db)
    total = 0

    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[proprietary_flow] Đang lấy dòng tiền tự doanh cho %s...", sym)
        try:
            cnt = crawler.crawl_symbol(sym)
            total += cnt
            logger.info("  -> [OK] %s: +%d phiên tự doanh.", sym, cnt)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào tự doanh %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_fundamental("foreign_flow", "Khối ngoại mua/bán ròng và room ngoại CafeF (core.market_foreign_flow_daily)")
def run_foreign_flow(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào dòng tiền khối ngoại từ CafeF."""
    from crawlers.cafef_foreign_flow import CafeFForeignFlowIngester, run_cafef_foreign_flow
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "market_foreign_flow_daily", symbols, force=getattr(args, "force", False), date_column="date"
    )
    if not active_symbols:
        logger.info("[foreign_flow] Toàn bộ %d mã đã có dữ liệu khối ngoại -> BỎ QUA.", len(symbols))
        return 0

    logger.info("[foreign_flow] Đang nạp dòng tiền và room khối ngoại CafeF cho %d mã...", len(active_symbols))
    try:
        cnt = run_cafef_foreign_flow(duckdb_path=writer.target_db, symbols=active_symbols)
        logger.info("  -> [OK] Khối ngoại CafeF: Đã nạp +%d bản ghi.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi nạp khối ngoại CafeF: %s", e)
        return 0


@register_fundamental("macro_rates", "Lãi suất liên ngân hàng (ON, 1W, 1M) & TPCP VN10Y (core.macro_rates)")
def run_macro_rates(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào và cập nhật lãi suất điều hành & liên ngân hàng."""
    from crawlers.macro_rates import MacroRatesCrawler
    crawler = MacroRatesCrawler(db_path=writer.target_db)
    logger.info("[macro_rates] Đang trích xuất lãi suất liên ngân hàng & trái phiếu chính phủ...")
    try:
        res = crawler.run()
        cnt = res.get("total_promoted", 0)
        logger.info("  -> [OK] Macro Rates: Đã lưu +%d mốc lãi suất.", cnt)
        return cnt
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào lãi suất: %s", e)
        return 0


@register_fundamental("market_ohlcv", "Giá & khối lượng giao dịch OHLCV lịch sử (core.market_ohlcv_daily)")
def run_market_ohlcv(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào giá nến ngày OHLCV."""
    from crawlers import market_ohlcv
    boundary_mgr = BoundaryManager(db_path=writer.target_db)
    active_symbols, _ = boundary_mgr.filter_symbols_to_crawl(
        "market_ohlcv_daily", symbols, force=getattr(args, "force", False), date_column="date"
    )
    if not active_symbols:
        logger.info("[market_ohlcv] Toàn bộ %d mã đã có đầy đủ nến OHLCV -> BỎ QUA.", len(symbols))
        return 0

    total = 0
    for sym in active_symbols:
        sym = sym.upper().strip()
        logger.info("[market_ohlcv] Đang cập nhật giá OHLCV cho %s...", sym)
        try:
            n = market_ohlcv.run(sym)
            total += n
            logger.info("  -> [OK] %s: +%d nến OHLCV.", sym, n)
        except Exception as e:
            logger.warning("  -> [Skip] Lỗi cào giá %s: %s", sym, e)
        time.sleep(getattr(args, "delay", 0.5))
    return total


@register_fundamental("vnstock_macro", "Trọn bộ 9 chỉ số Vĩ mô Vnstock (core.macro_economic_series & core.macro_rates)")
def run_vnstock_macro(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào trọn bộ 9 chỉ số kinh tế vĩ mô từ Vnstock."""
    from crawlers.vnstock_macro_series import VnstockMacroSeriesCrawler
    crawler = VnstockMacroSeriesCrawler(writer=writer)
    logger.info("[vnstock_macro] Đang nạp trọn bộ 9 chỉ số vĩ mô từ vnstock...")
    try:
        res = crawler.crawl_all()
        total = sum(res.values())
        logger.info("  -> [OK] Vnstock Macro: Đã lưu +%d bản ghi.", total)
        return total
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào vĩ mô vnstock: %s", e)
        return 0


@register_fundamental("vnstock_governance", "Hồ sơ chuyên sâu & Cổ đông lớn VN30 (core.company_overview & core.company_shareholders)")
def run_vnstock_governance(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào hồ sơ chuyên sâu và cơ cấu cổ đông lớn từ vnstock."""
    from crawlers.vnstock_company_governance import VnstockCompanyGovernanceCrawler
    crawler = VnstockCompanyGovernanceCrawler(writer=writer)
    logger.info("[vnstock_governance] Đang nạp hồ sơ & cổ đông lớn cho %d mã...", len(symbols))
    try:
        res = crawler.crawl_symbols(symbols, delay_seconds=getattr(args, "delay", 0.3))
        total = res.get("overview", 0) + res.get("shareholders", 0)
        logger.info(
            "  -> [OK] Vnstock Governance: Đã lưu +%d bản ghi (%d overview, %d cổ đông).",
            total, res.get("overview", 0), res.get("shareholders", 0)
        )
        return total
    except Exception as e:
        logger.warning("  -> [Skip] Lỗi cào hồ sơ & cổ đông vnstock: %s", e)
        return 0


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
        description="VESTA Master Fundamentals & Quantitative Numeric Crawler Orchestrator"
    )
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn file DuckDB chính")
    parser.add_argument("--symbols", default="VCB,FPT,SSI", help="Danh sách mã cổ phiếu (phân tách bởi dấu phẩy, 'vn30', hoặc 'all')")
    parser.add_argument("--all", action="store_true", help="Cào toàn bộ mã cổ phiếu trên thị trường (tương đương --symbols all)")
    parser.add_argument("--sources", default="all", help="Danh sách nguồn cào (all hoặc phân tách bởi dấu phẩy)")
    parser.add_argument("--period", default="quarter", choices=["quarter", "year"], help="Kỳ báo cáo tài chính")
    parser.add_argument("--report-type", default="all", help="Loại báo cáo tài chính (all, balance_sheet, income_statement...)")
    parser.add_argument("--delay", type=float, default=0.5, help="Thời gian nghỉ giữa các request (giây)")
    parser.add_argument("--smoke-test", action="store_true", help="Chạy thử nghiệm nhanh với số lượng mẫu nhỏ")
    parser.add_argument("--force", action="store_true", help="Bắt buộc cào lại toàn bộ, không bỏ qua các mã đã có dữ liệu")
    parser.add_argument("--sync", action="store_true", help="Kích hoạt đồng bộ dữ liệu đệm vào database đích")
    parser.add_argument("--list", action="store_true", help="Liệt kê toàn bộ nguồn cào cơ bản đã đăng ký")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if getattr(args, "all", False):
        args.symbols = "all"

    if args.list:
        print("\n" + "=" * 70)
        print("DANH SÁCH CÁC NGUỒN CÀO DỮ LIỆU CƠ BẢN ĐÃ ĐĂNG KÝ (FUNDAMENTAL REGISTRY)")
        print("=" * 70)
        for name, spec in FUNDAMENTAL_REGISTRY.items():
            print(f"• [{name}]: {spec.description}")
        print("=" * 70)
        return 0

    writer = ResilientDuckDBWriter(target_db=args.db)
    os.environ["VESTA_DB_PATH"] = os.path.abspath(args.db)
    db.DB_PATH = pathlib.Path(os.path.abspath(args.db))

    # Đồng bộ nếu được yêu cầu
    if args.sync:
        logger.info("Đang kiểm tra và đồng bộ dữ liệu từ bộ đệm vào %s...", args.db)
        synced = writer.sync_buffer_to_target()
        logger.info("Đã đồng bộ thành công %d bảng vào database đích.", synced)
        if not args.symbols and args.sources == "none":
            return 0

    raw_symbols = args.symbols.strip()
    if raw_symbols.lower() == "vn30":
        from crawlers.track_crawling_progress import VN30_SYMBOLS
        symbols = VN30_SYMBOLS.copy()
        logger.info(">>> Đã tự động nạp rổ chỉ số VN30 (%d mã) <<<", len(symbols))
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

    # Lựa chọn nguồn chạy
    if args.sources.lower() == "all":
        active_specs = list(FUNDAMENTAL_REGISTRY.values())
    else:
        req_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        active_specs = [
            FUNDAMENTAL_REGISTRY[s] for s in req_sources if s in FUNDAMENTAL_REGISTRY
        ]
        if not active_specs:
            logger.error("Không tìm thấy nguồn nào hợp lệ trong: %s", args.sources)
            return 1

    logger.info("=" * 80)
    logger.info("KHỞI CHẠY MASTER FUNDAMENTALS CRAWLER (%d nguồn, %d mã cổ phiếu)", len(active_specs), len(symbols))
    logger.info("Database đích: %s", writer.target_db)
    logger.info("=" * 80)

    start_time = time.time()
    grand_total = 0
    results: Dict[str, int] = {}

    for spec in active_specs:
        logger.info("\n--- BẮT ĐẦU NGUỒN: %s ---", spec.name.upper())
        try:
            cnt = spec.runner(symbols, writer, args)
            results[spec.name] = cnt
            grand_total += cnt
        except Exception as e:
            logger.error("Lỗi nghiêm trọng khi chạy nguồn %s: %s", spec.name, e)
            results[spec.name] = 0

    # Tự động thử đồng bộ lại nếu có bản ghi ghi vào buffer
    writer.sync_buffer_to_target()

    duration = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("HOÀN TẤT MASTER FUNDAMENTALS CRAWLER TRONG %.2f GIÂY", duration)
    logger.info("Tổng bản ghi nạp thành công: +%d", grand_total)
    for name, cnt in results.items():
        logger.info("  • %-22s: +%d bản ghi", name, cnt)
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
