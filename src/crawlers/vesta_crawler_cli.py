"""src/crawlers/vesta_crawler_cli.py

VESTA UNIFIED CRAWLER SYSTEM (Hub Điều Phối Cào Dữ Liệu Toàn Diện).
Đáp ứng trọn vẹn 3 yêu cầu cốt lõi:
1. Status Inspector: Kiểm tra chi tiết độ phủ, số lượng bản ghi, min_date, max_date
   và khoảng trống ngày (gap to today) của toàn bộ các bảng dữ liệu trong Lakehouse.
2. Incremental Latest Crawl: Tự động phát hiện ngày cào cuối cùng (max_date) và cào bù
   dữ liệu mới nhất đến hôm nay cho toàn bộ phân hệ (OHLCV, BCTC, Tin tức, Vĩ mô).
3. Category-Selective Crawl: Cho phép lựa chọn chạy duy nhất 1 danh mục dữ liệu độc lập
   (ohlcv, fundamentals, news, news_macro, events, macro, governance).

Tích hợp ResilientDuckDBWriter chống xung đột khóa file trên Windows và tuân thủ
chuẩn Unified API hiện đại của Vnstock Sponsor Tier (không dính lỗi deprecation).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

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

from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
from crawlers.track_crawling_progress import VN30_SYMBOLS
from etl import db

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vesta_crawler_cli")


# =============================================================================
# 1. STATUS & BOUNDARY INSPECTOR
# =============================================================================

TABLE_METADATA_SPECS = [
    {
        "table": "core.market_ohlcv_daily",
        "name": "Giá nến ngày (OHLCV 1D)",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "market",
    },
    {
        "table": "core.market_ohlcv_1m",
        "name": "Giá nến cao tần (1m)",
        "date_col": "time",
        "sym_col": "symbol",
        "type": "market",
    },
    {
        "table": "core.fundamentals",
        "name": "Báo cáo tài chính (BCTC)",
        "date_col": "period_end",
        "sym_col": "symbol",
        "type": "fundamentals",
    },
    {
        "table": "core.financial_notes",
        "name": "Thuyết minh BCTC chi tiết",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "fundamentals",
    },
    {
        "table": "core.corporate_events",
        "name": "Sự kiện quyền & Cổ tức",
        "date_col": "event_date",
        "sym_col": "symbol",
        "type": "events",
    },
    {
        "table": "core.news",
        "name": "Tin tức doanh nghiệp (CafeF)",
        "date_col": "published_at",
        "sym_col": "symbol",
        "type": "news",
    },
    {
        "table": "core.news_resources",
        "name": "Báo chí Tài chính & Vĩ mô",
        "date_col": "published_at",
        "sym_col": None,
        "type": "news",
    },
    {
        "table": "core.macro_economic_series",
        "name": "9 Chỉ số Kinh tế Vĩ mô",
        "date_col": "period_date",
        "sym_col": "indicator",
        "type": "macro",
    },
    {
        "table": "core.macro_rates",
        "name": "Lãi suất LH & Trái phiếu",
        "date_col": "date",
        "sym_col": "rate_type",
        "type": "macro",
    },
    {
        "table": "core.company_overview",
        "name": "Hồ sơ chuyên sâu doanh nghiệp",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "governance",
    },
    {
        "table": "core.company_shareholders",
        "name": "Cơ cấu Cổ đông lớn",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "governance",
    },
    {
        "table": "core.proprietary_flow",
        "name": "Dòng tiền Khối Tự Doanh",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "flow",
    },
    {
        "table": "core.market_foreign_flow_daily",
        "name": "Dòng tiền Khối Ngoại & Room",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "flow",
    },
]


def inspect_database_status(target_db: str) -> None:
    """Quét và in bảng Dashboard chi tiết về tình trạng Lakehouse hiện tại."""
    today = dt.date.today()
    print("\n" + "═" * 115)
    print(f"       VESTA QUANTITATIVE LAKEHOUSE — BẢNG ĐIỀU KHIỂN TRẠNG THÁI DỮ LIỆU ({today.isoformat()})")
    print(f"       Cơ sở dữ liệu: {os.path.abspath(target_db)}")
    print("═" * 115)

    try:
        con = duckdb.connect(target_db, read_only=True)
    except Exception as e:
        print(f"[!] Không thể mở database {target_db} trực tiếp: {e}")
        buf_db = str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb")
        if os.path.exists(buf_db):
            print(f"[*] Thử đọc từ cơ sở dữ liệu đệm: {buf_db}")
            try:
                con = duckdb.connect(buf_db, read_only=True)
            except Exception as e2:
                print(f"[!] Thất bại kết nối đệm: {e2}")
                return
        else:
            return

    header = (
        f"{'Phân Hệ / Bảng Dữ Liệu':<32} | "
        f"{'Số Bản Ghi':>12} | "
        f"{'Số Mã':>8} | "
        f"{'Min Date':<11} | "
        f"{'Max Date':<11} | "
        f"{'Độ Trễ / Tình Trạng'}"
    )
    print(header)
    print("─" * 115)

    for spec in TABLE_METADATA_SPECS:
        tbl = spec["table"]
        name = spec["name"]
        date_col = spec["date_col"]
        sym_col = spec["sym_col"]

        # Kiểm tra bảng có tồn tại không
        schema, table_name = tbl.split(".")
        tbl_exists = con.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table_name],
        ).fetchone()[0]

        if not tbl_exists:
            print(f"{name:<32} | {'CHƯA TẠO':>12} | {'-':>8} | {'-':<11} | {'-':<11} | [!] Bảng chưa được khởi tạo")
            continue

        try:
            sym_expr = f"COUNT(DISTINCT {sym_col})" if sym_col else "'-'"
            date_expr = f"CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR)"
            query = f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM {tbl}"
            row = con.execute(query).fetchone()

            total_rows = row[0]
            total_syms = row[1] if row[1] != "-" else "-"
            min_date = str(row[2])[:10] if row[2] else "-"
            max_date = str(row[3])[:10] if row[3] else "-"

            # Đánh giá độ trễ
            status_desc = "Trống"
            if total_rows > 0 and max_date != "-":
                try:
                    max_d = dt.date.fromisoformat(max_date)
                    gap_days = (today - max_d).days
                    if gap_days <= 1:
                        status_desc = "✅ Rất mới (T-0/T-1)"
                    elif gap_days <= 7:
                        status_desc = f"⚠️ Trễ {gap_days} ngày"
                    elif gap_days <= 95:
                        status_desc = f"⚠️ Trễ {gap_days // 30} tháng ({gap_days}d)"
                    else:
                        status_desc = f"❌ Cần cào bù ({gap_days}d)"
                except Exception:
                    status_desc = "Đã có dữ liệu"

            sym_str = f"{total_syms:,}" if isinstance(total_syms, int) else str(total_syms)
            print(
                f"{name:<32} | "
                f"{total_rows:>12,} | "
                f"{sym_str:>8} | "
                f"{min_date:<11} | "
                f"{max_date:<11} | "
                f"{status_desc}"
            )
        except Exception as ex:
            print(f"{name:<32} | {'LỖI ĐỌC':>12} | {'-':>8} | {'-':<11} | {'-':<11} | [!] {ex}")

    con.close()
    print("═" * 115 + "\n")


# =============================================================================
# 2. HELPER: LẤY DANH SÁCH MÃ
# =============================================================================

def get_target_symbols(target_db: str, symbol_arg: str = "all") -> List[str]:
    """Lấy danh sách mã chứng khoán theo lựa chọn."""
    symbol_arg = symbol_arg.strip()
    if symbol_arg.lower() == "vn30":
        return VN30_SYMBOLS.copy()

    if symbol_arg.lower() not in ("all", "all_equities"):
        return [s.strip().upper() for s in symbol_arg.split(",") if s.strip()]

    # Lấy toàn bộ 1,522 mã niêm yết từ core.dim_symbol (bỏ trái phiếu)
    query = """
        SELECT symbol 
        FROM core.dim_symbol 
        WHERE is_delisted IS NOT TRUE 
          AND length(symbol) = 3
        ORDER BY symbol
    """
    try:
        con = duckdb.connect(target_db, read_only=True)
        rows = con.execute(query).fetchall()
        con.close()
        symbols = [r[0] for r in rows]
        if symbols:
            return symbols
    except Exception:
        pass

    canonical = str(PROJECT_ROOT / "db" / "vesta.duckdb")
    if os.path.exists(canonical) and canonical != target_db:
        try:
            con = duckdb.connect(canonical, read_only=True)
            rows = con.execute(query).fetchall()
            con.close()
            symbols = [r[0] for r in rows]
            if symbols:
                return symbols
        except Exception:
            pass

    return VN30_SYMBOLS.copy()


# =============================================================================
# 3. WORKERS CHO TỪNG PHÂN HỆ (CATEGORY RUNNERS)
# =============================================================================

def run_category_ohlcv(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Giá nến OHLCV (1D hoặc 1m)."""
    from crawlers.crawl_all_ohlcv_fundamentals import crawl_ohlcv_for_symbol
    interval = getattr(args, "interval", "1D")
    start = getattr(args, "start", "2000-01-01")
    end = getattr(args, "end", None)
    delay = getattr(args, "delay", 0.4)

    logger.info(">>> [CATEGORY: OHLCV] Bắt đầu cào giá nến %s cho %d mã...", interval, len(symbols))
    total_bars = 0
    for idx, sym in enumerate(symbols, 1):
        status, cnt = crawl_ohlcv_for_symbol(sym, writer, interval=interval, start_date=start, end_date=end)
        if status == "success":
            total_bars += cnt
            logger.info("[%d/%d] %s: +%d nến %s.", idx, len(symbols), sym, cnt, interval)
        time.sleep(delay)
    return total_bars


def run_category_fundamentals(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Báo cáo tài chính (CĐKT, KQKD, LCTT, Ratios)."""
    from crawlers.crawl_all_ohlcv_fundamentals import crawl_fundamentals_for_symbol
    period = getattr(args, "period", "quarter")
    report_type = getattr(args, "report_type", "all")
    delay = getattr(args, "delay", 0.4)

    logger.info(">>> [CATEGORY: FUNDAMENTALS] Bắt đầu cào BCTC (kỳ=%s) cho %d mã...", period, len(symbols))
    total_stmts = 0
    for idx, sym in enumerate(symbols, 1):
        status, cnt = crawl_fundamentals_for_symbol(sym, writer, period=period, report_type=report_type)
        if status == "success":
            total_stmts += cnt
            logger.info("[%d/%d] %s: +%d báo cáo tài chính.", idx, len(symbols), sym, cnt)
        time.sleep(delay)
    return total_stmts


def run_category_news_stock(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Tin tức cổ phiếu CafeF với cơ chế dừng biên thông minh (Incremental)."""
    from crawlers import cafef_news
    delay = getattr(args, "delay", 0.5)
    force = getattr(args, "force", False)

    logger.info(">>> [CATEGORY: NEWS_STOCK] Bắt đầu cào tin tức doanh nghiệp cho %d mã (chế độ cào bù: %s)...", len(symbols), "Cào đè lại" if force else "Chỉ cào bài mới")
    total_articles = 0
    for idx, sym in enumerate(symbols, 1):
        try:
            cnt = cafef_news.run(sym, incremental=True, force=force)
            total_articles += cnt
            logger.info("[%d/%d] %s: +%d tin bài CafeF mới.", idx, len(symbols), sym, cnt)
        except Exception as e:
            logger.debug("Bỏ qua tin bài %s: %s", sym, e)
        time.sleep(delay)
    return total_articles


def run_category_news_macro(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Tin tức tài chính vĩ mô từ 4 nguồn báo chí hàng đầu."""
    from crawlers import baochinhphu_crawler, nhandan_crawler, thoibaotaichinh_crawler, vietnamfinance_crawler
    max_pages = getattr(args, "pages", 10)
    source = getattr(args, "source", "all")
    logger.info(">>> [CATEGORY: NEWS_MACRO] Khởi chạy kênh báo chí vĩ mô (nguồn=%s, tối đa %d trang/nguồn)...", source, max_pages)

    total = 0
    # 1. Báo Nhân Dân
    if source in ("all", "nhandan"):
        try:
            cnt1 = nhandan_crawler.crawl_nhandan(db_path=writer.target_db, start_year=2026, end_year=2025, max_articles=max_pages * 20)
            total += cnt1
            logger.info("  • Báo Nhân Dân: +%d tin bài.", cnt1)
        except Exception as e:
            logger.warning("  • Lỗi cào Báo Nhân Dân: %s", e)

    # 2. VietnamFinance
    if source in ("all", "vietnamfinance"):
        try:
            cnt2 = vietnamfinance_crawler.crawl_vietnamfinance(db_path=writer.target_db, max_pages=max_pages)
            total += cnt2
            logger.info("  • VietnamFinance: +%d tin bài.", cnt2)
        except Exception as e:
            logger.warning("  • Lỗi cào VietnamFinance: %s", e)

    # 3. Thời Báo Tài Chính Việt Nam
    if source in ("all", "thoibaotaichinh"):
        try:
            cnt3 = thoibaotaichinh_crawler.crawl_tbtc(db_path=writer.target_db, max_pages=max_pages)
            total += cnt3
            logger.info("  • Thời Báo Tài Chính: +%d tin bài.", cnt3)
        except Exception as e:
            logger.warning("  • Lỗi cào TBTC: %s", e)

    # 4. Báo Chính Phủ
    if source in ("all", "baochinhphu"):
        try:
            cnt4 = baochinhphu_crawler.crawl_baochinhphu(db_path=writer.target_db, max_pages=max_pages)
            total += cnt4
            logger.info("  • Báo Chính Phủ: +%d tin bài.", cnt4)
        except Exception as e:
            logger.warning("  • Lỗi cào Báo Chính Phủ: %s", e)

    return total


def run_category_events(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Lịch sự kiện & Cổ tức."""
    from crawlers import corporate_events
    delay = getattr(args, "delay", 0.4)

    logger.info(">>> [CATEGORY: EVENTS] Bắt đầu cào sự kiện quyền & cổ tức cho %d mã...", len(symbols))
    total_events = 0
    for idx, sym in enumerate(symbols, 1):
        try:
            cnt = corporate_events.run(sym)
            total_events += cnt
            logger.info("[%d/%d] %s: +%d sự kiện doanh nghiệp.", idx, len(symbols), sym, cnt)
        except Exception as e:
            logger.debug("Bỏ qua sự kiện %s: %s", sym, e)
        time.sleep(delay)
    return total_events


def run_category_macro(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào trọn bộ Vĩ mô (9 chỉ số vĩ mô & Lãi suất liên ngân hàng)."""
    from crawlers.macro_rates import MacroRatesCrawler
    from crawlers.vnstock_macro_series import VnstockMacroSeriesCrawler

    logger.info(">>> [CATEGORY: MACRO] Bắt đầu cào 9 chỉ số kinh tế vĩ mô & Lãi suất liên ngân hàng...")
    do_9ind = getattr(args, "macro_9ind", True)
    do_rates = getattr(args, "macro_rates", True)

    # 1. 9 Chỉ số vĩ mô
    if do_9ind:
        try:
            macro_crawler = VnstockMacroSeriesCrawler(writer=writer)
            res1 = macro_crawler.crawl_all()
            cnt1 = sum(res1.values())
            total += cnt1
            logger.info("  • 9 Chỉ số vĩ mô Vnstock: +%d mốc dữ liệu.", cnt1)
        except Exception as e:
            logger.warning("  • Lỗi cào chỉ số vĩ mô: %s", e)

    # 2. Lãi suất liên ngân hàng & TPCP
    if do_rates:
        try:
            rates_crawler = MacroRatesCrawler(db_path=writer.target_db)
            res2 = rates_crawler.run()
            cnt2 = res2.get("total_promoted", 0)
            total += cnt2
            logger.info("  • Lãi suất & Lợi suất TPCP: +%d bản ghi.", cnt2)
        except Exception as e:
            logger.warning("  • Lỗi cào lãi suất: %s", e)

    return total


def run_category_governance(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Hồ sơ doanh nghiệp & Cổ đông lớn."""
    from crawlers.vnstock_company_governance import VnstockCompanyGovernanceCrawler
    delay = getattr(args, "delay", 0.3)

    logger.info(">>> [CATEGORY: GOVERNANCE] Bắt đầu cào hồ sơ & cổ đông lớn cho %d mã...", len(symbols))
    crawler = VnstockCompanyGovernanceCrawler(writer=writer)
    res = crawler.crawl_symbols(symbols, delay_seconds=delay)
    total = res.get("overview", 0) + res.get("shareholders", 0)
    logger.info("  • Hồ sơ & Cổ đông lớn: +%d bản ghi (%d overview, %d cổ đông).", total, res.get("overview", 0), res.get("shareholders", 0))
    return total


CATEGORIES_REGISTRY = {
    "ohlcv": run_category_ohlcv,
    "fundamentals": run_category_fundamentals,
    "news": run_category_news_stock,
    "news_macro": run_category_news_macro,
    "events": run_category_events,
    "macro": run_category_macro,
    "governance": run_category_governance,
}


# =============================================================================
# 4. INCREMENTAL LATEST CRAWLER (TỰ ĐỘNG CÀO TIẾN ĐẾN HÔM NAY)
# =============================================================================

def run_latest_all(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> None:
    """Tự động phát hiện khoảng trống thời gian và cào bù dữ liệu mới nhất toàn thị trường."""
    today = dt.date.today().isoformat()
    logger.info("=" * 80)
    logger.info("BẮT ĐẦU CHẾ ĐỘ CẬP NHẬT MỚI NHẤT TOÀN THỊ TRƯỜNG (LATEST INCREMENTAL CATCH-UP)")
    logger.info("Thời điểm thực thi: %s | Danh mục: %d mã", today, len(symbols))
    logger.info("=" * 80)

    # 1. Cào giá nến ngày mới nhất
    logger.info("\n--- [1/5] CẬP NHẬT GIÁ NẾN OHLCV MỚI NHẤT ---")
    run_category_ohlcv(symbols, writer, args)

    # 2. Cào BCTC quý mới nhất
    logger.info("\n--- [2/5] CẬP NHẬT BÁO CÁO TÀI CHÍNH QUÝ MỚI NHẤT ---")
    run_category_fundamentals(symbols, writer, args)

    # 3. Cào sự kiện & cổ tức mới nhất
    logger.info("\n--- [3/5] CẬP NHẬT SỰ KIỆN DOANH NGHIỆP & CỔ TỨC ---")
    run_category_events(symbols, writer, args)

    # 4. Cào lãi suất & vĩ mô mới nhất
    logger.info("\n--- [4/5] CẬP NHẬT LÃI SUẤT LIÊN NGÂN HÀNG & CHỈ SỐ VĨ MÔ ---")
    run_category_macro(symbols, writer, args)

    # 5. Cào tin tức báo chí mới nhất 7 ngày qua
    logger.info("\n--- [5/5] CẬP NHẬT TIN TỨC BÁO CHÍ MỚI NHẤT ---")
    args.pages = 3  # Lấy các trang đầu tiên chứa tin tức nóng nhất
    run_category_news_macro(symbols, writer, args)

    # Đồng bộ bộ đệm nếu có
    writer.sync_buffer_to_target()
    logger.info("\n>>> HOÀN TẤT TOÀN BỘ TIẾN TRÌNH CẬP NHẬT DỮ LIỆU MỚI NHẤT <<<")


# =============================================================================
# 5. CLI ENTRYPOINT
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VESTA Unified Crawler Hub — Hệ Thống Cào Dữ Liệu Chứng Khoán Toàn Diện"
    )
    subparsers = parser.add_subparsers(dest="command", help="Lệnh thực thi chính")

    # 1. Lệnh status (hoặc check)
    status_parser = subparsers.add_parser("status", help="Kiểm tra độ phủ, min_date, max_date và khoảng trống dữ liệu")
    status_parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB")

    check_parser = subparsers.add_parser("check", help="Tương tự status")
    check_parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB")

    # 2. Lệnh crawl
    crawl_parser = subparsers.add_parser("crawl", help="Kích hoạt tiến trình cào dữ liệu")
    crawl_parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB")
    crawl_parser.add_argument(
        "--mode",
        choices=["latest", "category", "all"],
        default="latest",
        help="Chế độ cào: 'latest' (tự động cào bù tiến đến hôm nay), 'category' (chọn 1 danh mục), 'all' (cào toàn bộ)",
    )
    crawl_parser.add_argument(
        "--category",
        choices=list(CATEGORIES_REGISTRY.keys()),
        default="ohlcv",
        help="Danh mục dữ liệu khi chạy mode 'category': ohlcv, fundamentals, news, news_macro, events, macro, governance",
    )
    crawl_parser.add_argument(
        "--symbols",
        default="all",
        help="Danh sách mã: 'all' (1,522 mã niêm yết), 'vn30', hoặc mã cách nhau bởi dấu phẩy (VCB,TCB,FPT)",
    )
    crawl_parser.add_argument("--interval", choices=["1D", "1m"], default="1D", help="Khung thời gian nến (1D hoặc 1m)")
    crawl_parser.add_argument("--start", default="2000-01-01", help="Ngày bắt đầu (YYYY-MM-DD)")
    crawl_parser.add_argument("--end", default=None, help="Ngày kết thúc (mặc định: hôm nay)")
    crawl_parser.add_argument("--period", choices=["quarter", "year"], default="quarter", help="Kỳ BCTC")
    crawl_parser.add_argument("--report-type", default="all", help="Loại BCTC")
    crawl_parser.add_argument("--delay", type=float, default=0.4, help="Thời gian nghỉ giữa các request (giây)")
    crawl_parser.add_argument("--pages", type=int, default=5, help="Số trang tối đa cho crawler báo chí")
    crawl_parser.add_argument("--force", action="store_true", help="Bắt buộc cào đè, không dùng checkpoint bỏ qua")
    crawl_parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mã để test")

    # Tương thích nếu người dùng gõ trực tiếp --status hoặc --check
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái nhanh")
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Xử lý lệnh status / check
    if getattr(args, "status", False) or args.command in ("status", "check"):
        target_db = getattr(args, "db", DEFAULT_TARGET_DB)
        inspect_database_status(target_db)
        return 0

    # 2. Xử lý lệnh crawl
    if args.command == "crawl":
        target_db = os.path.abspath(args.db)
        os.environ["VESTA_DB_PATH"] = target_db
        db.DB_PATH = pathlib.Path(target_db)
        writer = ResilientDuckDBWriter(target_db=target_db)

        symbols = get_target_symbols(target_db, symbol_arg=args.symbols)
        if args.limit:
            symbols = symbols[: args.limit]

        # Mode: latest
        if args.mode == "latest":
            run_latest_all(symbols, writer, args)
            return 0

        # Mode: category (chạy duy nhất 1 phân hệ chọn lọc)
        if args.mode == "category":
            cat = args.category.lower()
            if cat not in CATEGORIES_REGISTRY:
                logger.error("Phân hệ '%s' không tồn tại. Lựa chọn hợp lệ: %s", cat, list(CATEGORIES_REGISTRY.keys()))
                return 1

            start_t = time.time()
            logger.info("=" * 80)
            logger.info("KHỞI CHẠY PHÂN HỆ ĐỘC LẬP: [%s] (%d mã, delay=%.2fs)", cat.upper(), len(symbols), args.delay)
            logger.info("=" * 80)
            runner = CATEGORIES_REGISTRY[cat]
            cnt = runner(symbols, writer, args)
            writer.sync_buffer_to_target()
            duration = time.time() - start_t
            logger.info("=" * 80)
            logger.info("HOÀN TẤT PHÂN HỆ [%s] TRONG %.2f GIÂY. TỔNG BẢN GHI: +%d", cat.upper(), duration, cnt)
            logger.info("=" * 80)
            return 0

        # Mode: all (tuần tự chạy tất cả categories)
        if args.mode == "all":
            start_t = time.time()
            total_all = 0
            for cat, runner in CATEGORIES_REGISTRY.items():
                logger.info("\n--- BẮT ĐẦU DANH MỤC: %s ---", cat.upper())
                try:
                    c = runner(symbols, writer, args)
                    total_all += c
                except Exception as e:
                    logger.error("Lỗi khi chạy %s: %s", cat, e)
            writer.sync_buffer_to_target()
            logger.info("\nHoàn tất cào toàn bộ danh mục trong %.2f giây. Tổng bản ghi: +%d", time.time() - start_t, total_all)
            return 0

    # Nếu không có subcommand cụ thể, hiển thị status
    inspect_database_status(getattr(args, "db", DEFAULT_TARGET_DB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
