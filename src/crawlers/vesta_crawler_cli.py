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
from typing import Any, Callable, Dict, List, Optional

import duckdb

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
VENV_SITE = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(1, str(VENV_SITE))

from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter  # noqa: E402
from crawlers.track_crawling_progress import VN30_SYMBOLS  # noqa: E402
from etl import db  # noqa: E402

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
        "table": "core.dim_symbol",
        "name": "Danh mục Toàn bộ Mã CK (F001)",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "reference",
    },
    {
        "table": "core.dim_icb_hierarchy",
        "name": "Phân ngành Chuẩn 4 Cấp ICB (F001)",
        "date_col": "updated_at",
        "sym_col": "icb_code",
        "type": "reference",
    },
    {
        "table": "core.symbol_exchange_history",
        "name": "Lịch sử Chuyển Sàn Liên tục (F001)",
        "date_col": "start_date",
        "sym_col": "symbol",
        "type": "reference",
    },
    {
        "table": "core.dim_symbol_cafef",
        "name": "Bổ sung Danh mục CafeF & OTC (F001b)",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "reference",
    },
    {
        "table": "core.dim_index_metadata",
        "name": "Danh mục 22 Rổ Chỉ số (F001c)",
        "date_col": "created_at",
        "sym_col": "index_code",
        "type": "reference",
    },
    {
        "table": "core.dim_index_constituents",
        "name": "Thành phần Rổ Chỉ số & Room (F001c)",
        "date_col": "effective_date",
        "sym_col": "symbol",
        "type": "reference",
    },
    {
        "table": "core.market_ohlcv_daily",
        "name": "Giá nến ngày (OHLCV 1D)",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "market",
    },
    {
        "table": "core.price_adjustment_events",
        "name": "Sự kiện Điều chỉnh Giá & CAF (F002)",
        "date_col": "ex_date",
        "sym_col": "symbol",
        "type": "market",
    },
    {
        "table": "core.symbol_caf_timeline",
        "name": "Dòng thời gian Hệ số CAF (F002)",
        "date_col": "start_date",
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
        "table": "core.cafef_disclosures",
        "name": "Công bố thông tin CafeF (F003)",
        "date_col": "published_at",
        "sym_col": "symbol",
        "type": "news",
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
    {
        "table": "core.realtime_quote_snapshot",
        "name": "Bảng giá Snapshot (1,751 mã - F007)",
        "date_col": "snapshot_at",
        "sym_col": "symbol",
        "type": "streaming",
    },
    {
        "table": "core.market_sentiment_snapshot",
        "name": "Tâm lý & Độ rộng TT 26 năm",
        "date_col": "snapshot_date",
        "sym_col": "exchange",
        "type": "sentiment",
    },
    {
        "table": "core.market_screener_snapshot",
        "name": "Bộ lọc Đa Nhân Tố 21 năm (Screener)",
        "date_col": "snapshot_date",
        "sym_col": "symbol",
        "type": "screener",
    },
    {
        "table": "core.market_derivatives_daily",
        "name": "Hợp đồng Tương lai VN30F (F073)",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "derivatives",
    },
    {
        "table": "core.market_covered_warrants_daily",
        "name": "Chứng quyền Có bảo đảm CW (F074)",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "warrants",
    },
    {
        "table": "core.market_etf_daily",
        "name": "Chứng chỉ Quỹ ETF Toàn thị trường (F075)",
        "date_col": "date",
        "sym_col": "symbol",
        "type": "etf",
    },
    {
        "table": "core.market_bonds_daily",
        "name": "Trái phiếu Niêm yết (F076)",
        "date_col": "fetched_at",
        "sym_col": "symbol",
        "type": "bonds",
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
        db.attach_ohlcv(con, read_only=True)
        db.attach_intraday(con, read_only=True)
        db.attach_news(con, read_only=True)
    except Exception as e:
        print(f"[!] Không thể mở database {target_db} trực tiếp: {e}")
        buf_db = str(PROJECT_ROOT / "db" / "admin" / "vesta_crawled_fresh.duckdb")
        if os.path.exists(buf_db):
            print(f"[*] Thử đọc từ cơ sở dữ liệu đệm: {buf_db}")
            try:
                con = duckdb.connect(buf_db, read_only=True)
                db.attach_ohlcv(con, read_only=True)
                db.attach_intraday(con, read_only=True)
                db.attach_news(con, read_only=True)
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

        # Điều hướng bảng sang news_db hoặc ohlcv_db nếu cần, có fallback an toàn
        query_tbl = tbl
        if spec.get("type") == "news":
            query_tbl = f"news_db.{tbl}"
        elif "market_ohlcv" in tbl or "market_index" in tbl or "1m" in tbl:
            query_tbl = f"ohlcv_db.{tbl}"

        row = None
        try:
            sym_expr = f"COUNT(DISTINCT {sym_col})" if sym_col else "'-'"
            date_expr = f"CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR)"
            query = f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM {query_tbl}"
            row = con.execute(query).fetchone()
        except Exception:
            # Fallback đọc trực tiếp bảng từ target_db nếu catalog alias chưa attach được
            try:
                query_fallback = f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM {tbl}"
                row = con.execute(query_fallback).fetchone()
            except Exception:
                print(f"{name:<32} | {'CHƯA TẠO':>12} | {'-':>8} | {'-':<11} | {'-':<11} | [!] Bảng chưa được khởi tạo")
                continue


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

    con.close()
    print("═" * 115 + "\n")


# =============================================================================
# 2. HELPER: LẤY DANH SÁCH MÃ
# =============================================================================

def get_target_symbols(target_db: str, symbol_arg: str = "all") -> List[str]:
    """Lấy danh sách mã chứng khoán theo lựa chọn (Đảm bảo cào toàn bộ danh mục mã khi chọn 'all')."""
    symbol_arg = symbol_arg.strip()
    if symbol_arg.lower() == "vn30":
        return VN30_SYMBOLS.copy()

    if symbol_arg.lower() not in ("all", "all_equities"):
        return [s.strip().upper() for s in symbol_arg.split(",") if s.strip()]

    # Lấy toàn bộ mã niêm yết từ core.dim_symbol (bỏ trái phiếu)
    query = """
        SELECT symbol 
        FROM core.dim_symbol 
        WHERE is_delisted IS NOT TRUE 
          AND length(symbol) = 3
        ORDER BY symbol
    """
    for db_cand in [target_db, str(PROJECT_ROOT / "db" / "admin" / "vesta_snapshot.duckdb"), str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"), str(PROJECT_ROOT / "db" / "vesta.duckdb")]:
        if os.path.exists(db_cand):
            try:
                con = duckdb.connect(db_cand, read_only=True)
                rows = con.execute(query).fetchall()
                con.close()
                symbols = [r[0] for r in rows]
                if symbols and len(symbols) > 50:
                    return symbols
            except Exception:
                pass

    # Fallback tự động lấy 1,482+ mã từ hệ thống phân cấp ưu tiên
    try:
        from crawlers.intraday_ohlcv import get_prioritized_symbols
        pri_syms = get_prioritized_symbols()
        if pri_syms and len(pri_syms) > 50:
            return pri_syms
    except Exception:
        pass

    return VN30_SYMBOLS.copy()


# =============================================================================
# 3. WORKERS CHO TỪNG PHÂN HỆ (CATEGORY RUNNERS)
# =============================================================================

def run_category_ohlcv(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy cào phân hệ Giá nến OHLCV (1D hoặc 1m) lưu vào db/vesta_ohlcv.duckdb."""
    from crawlers.crawl_all_ohlcv_fundamentals import crawl_ohlcv_for_symbol
    interval = getattr(args, "interval", "1D")
    start = getattr(args, "start", "2000-01-01")
    end = getattr(args, "end", None)
    delay = getattr(args, "delay", 0.4)

    # Đảm bảo ghi đúng hồ chuyên biệt db/vesta_ohlcv.duckdb
    ohlcv_db_path = str(db.OHLCV_DB_PATH)
    buf_first = getattr(writer, "buffer_first", True)
    ohlcv_writer = writer if hasattr(writer, "target_db") and writer.target_db == ohlcv_db_path else ResilientDuckDBWriter(ohlcv_db_path, buffer_first=buf_first)

    logger.info(">>> [CATEGORY: OHLCV] Bắt đầu cào giá nến %s cho %d mã (CSDL đích: %s)...", interval, len(symbols), ohlcv_db_path)
    total_bars = 0
    for idx, sym in enumerate(symbols, 1):
        status, cnt = crawl_ohlcv_for_symbol(sym, ohlcv_writer, interval=interval, start_date=start, end_date=end)
        if status == "success":
            total_bars += cnt
            logger.info("[%d/%d] %s: +%d nến %s.", idx, len(symbols), sym, cnt, interval)
        time.sleep(delay)

    if interval == "1D" and total_bars > 0:
        try:
            from etl import adjustments
            logger.info("  • Tự động đồng bộ hệ số điều chỉnh giá CAF & View Dual-Mode (F002 Recommendation)...")
            adjustments.build_and_sync_all_adjustments(db_path=writer.target_db, symbols=symbols)
        except Exception as e:
            logger.warning("Không thể tự động đồng bộ CAF: %s", e)

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
    """Chạy cào phân hệ Tin tức tài chính vĩ mô từ 4 nguồn báo chí hàng đầu (Lưu vào vesta_news.duckdb)."""
    from crawlers import baochinhphu_crawler, nhandan_crawler, thoibaotaichinh_crawler, vietnamfinance_crawler
    max_pages = getattr(args, "pages", 10)
    source = getattr(args, "source", "all")
    news_db_path = str(db.NEWS_DB_PATH)
    logger.info(">>> [CATEGORY: NEWS_MACRO] Khởi chạy kênh báo chí vĩ mô (nguồn=%s, tối đa %d trang/nguồn, DB=vesta_news.duckdb)...", source, max_pages)

    total = 0
    current_year = dt.date.today().year
    # 1. Báo Nhân Dân
    if source in ("all", "nhandan"):
        try:
            res1 = nhandan_crawler.run_nhandan_crawler(db_path=news_db_path, max_articles=max_pages * 15)
            cnt1 = res1.get("written", 0) if isinstance(res1, dict) else int(res1 or 0)
            total += cnt1
            logger.info("  • Báo Nhân Dân: +%d tin bài (vesta_news.duckdb).", cnt1)
        except Exception as e:
            logger.warning("  • Lỗi cào Báo Nhân Dân: %s", e)

    # 2. VietnamFinance
    if source in ("all", "vietnamfinance"):
        try:
            res2 = vietnamfinance_crawler.run_vietnamfinance_crawler(db_path=news_db_path, max_pages_per_cat=max_pages)
            cnt2 = res2.get("written", 0) if isinstance(res2, dict) else int(res2 or 0)
            total += cnt2
            logger.info("  • VietnamFinance: +%d tin bài (vesta_news.duckdb).", cnt2)
        except Exception as e:
            logger.warning("  • Lỗi cào VietnamFinance: %s", e)

    # 3. Thời Báo Tài Chính Việt Nam
    if source in ("all", "thoibaotaichinh"):
        try:
            res3 = thoibaotaichinh_crawler.run_thoibaotaichinh_crawler(db_path=news_db_path, max_offsets=max_pages)
            cnt3 = res3.get("written", 0) if isinstance(res3, dict) else int(res3 or 0)
            total += cnt3
            logger.info("  • Thời Báo Tài Chính: +%d tin bài (vesta_news.duckdb).", cnt3)
        except Exception as e:
            logger.warning("  • Lỗi cào TBTC: %s", e)

    # 4. Báo Chính Phủ
    if source in ("all", "baochinhphu"):
        try:
            res4 = baochinhphu_crawler.run_baochinhphu_crawler(db_path=news_db_path, max_pages=max_pages)
            cnt4 = res4.get("written", 0) if isinstance(res4, dict) else int(res4 or 0)
            total += cnt4
            logger.info("  • Báo Chính Phủ: +%d tin bài (vesta_news.duckdb).", cnt4)
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
    total = 0

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


def run_category_reference(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Chạy phân hệ Danh mục mã niêm yết, Phân cấp ngành ICB 4 tầng và Lịch sử chuyển sàn (F001)."""
    from crawlers import dim_icb, dim_symbol, symbol_exchange_history

    ref_mode = getattr(args, "ref_mode", "all")
    logger.info(">>> [CATEGORY: REFERENCE] Khởi chạy cập nhật danh mục tham chiếu (chế độ=%s)...", ref_mode)
    total = 0

    con = writer.get_write_connection()
    try:
        # 1. Cập nhật Danh mục mã niêm yết dim_symbol
        if ref_mode in ("all", "symbol"):
            logger.info("  • [1/4] Cập nhật danh mục mã niêm yết core.dim_symbol...")
            df_sym = dim_symbol.run(con=con)
            cnt_sym = len(df_sym) if df_sym is not None else 0
            total += cnt_sym
            logger.info("    -> Đã cập nhật %d mã niêm yết vào core.dim_symbol.", cnt_sym)

        # 2. Cập nhật Phân cấp ngành 4 tầng ICB
        if ref_mode in ("all", "icb"):
            logger.info("  • [2/4] Cập nhật từ điển phân ngành 4 cấp core.dim_icb_hierarchy...")
            cnt_icb = dim_icb.crawl_and_load_icb(con=con)
            total += cnt_icb
            logger.info("    -> Đã nạp %d mã phân ngành chuẩn ICB vào core.dim_icb_hierarchy.", cnt_icb)

        # 3. Dựng dòng thời gian chuyển sàn liên tục
        if ref_mode in ("all", "history"):
            logger.info("  • [3/4] Dựng dòng thời gian chuyển sàn liên tục core.symbol_exchange_history...")
            cnt_hist = symbol_exchange_history.build_and_load_exchange_history(con=con)
            total += cnt_hist
            logger.info("    -> Đã sinh và nạp %d mốc chuyển sàn vào core.symbol_exchange_history.", cnt_hist)

        # 4. Đồng bộ danh bạ CafeF & phân tách OTC-Subuniverse (F001b)
        if ref_mode in ("all", "cafef", "otc"):
            logger.info("  • [4/4] Đồng bộ danh bạ CafeF & phân tách OTC-Subuniverse core.dim_symbol_cafef...")
            from crawlers import cafef_symbol_directory
            cnt_cafef = cafef_symbol_directory.run(con=con)
            total += cnt_cafef
            logger.info("    -> Đã nạp %d mã (gồm 750 mã OTC cách ly) vào core.dim_symbol_cafef.", cnt_cafef)

        # 5. Cào danh mục 22 rổ chỉ số & Room ngoại (F001c)
        if ref_mode in ("all", "index", "group", "basket"):
            logger.info("  • [5/5] Cào danh mục 22 rổ chỉ số & Room ngoại core.dim_index_constituents (F001c)...")
            from crawlers import dim_index_constituents
            summary_idx = dim_index_constituents.crawl_and_sync_constituents(con=con)
            cnt_idx = sum(summary_idx.values())
            total += cnt_idx
            logger.info("    -> Đã nạp %d lượt phân bổ vào 22 rổ chỉ số.", cnt_idx)
    finally:
        writer.close_write_connection(con)

    return total


def run_category_intraday_1m(symbols: List[str], writer: Any, args: argparse.Namespace) -> int:
    """Cào bù nến 1 phút 3 năm lưu vào vesta_intraday_1m.duckdb (F002b)."""
    from crawlers import intraday_ohlcv
    con_intra = db.connect_intraday()
    total_new = 0
    try:
        for idx, sym in enumerate(symbols, 1):
            logger.info("  • [%d/%d] Cào bù nến 1m cho mã %s...", idx, len(symbols), sym)
            res = intraday_ohlcv.backfill_symbol_1m(sym, con=con_intra)
            total_new += res.get("new_bars", 0)
    finally:
        con_intra.close()
    return total_new


def run_category_snapshots(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào bảng giá thời gian thực snapshot & chỉ số định giá P/E, P/B (F007 Vietcap/CafeF Direct REST API)."""
    from crawlers import snapshots
    logger.info(">>> [CATEGORY: SNAPSHOTS] Bắt đầu cào realtime quote snapshot cho %d mã...", len(symbols))
    try:
        raw = snapshots.fetch_raw(symbols)
        if raw.empty:
            logger.warning("  • Không lấy được dữ liệu snapshot từ Vietcap/CafeF fallback.")
            return 0
        normalized = snapshots.normalize_snapshot(raw)
        total = writer.execute_with_retry(lambda con: snapshots.write_snapshot(normalized, con=con))
        logger.info("  • Đã ghi thành công +%d bản ghi snapshot vào DuckDB.", total)
        return total
    except Exception as e:
        logger.warning("  • Lỗi cào snapshot: %s", e)
        return 0


def run_category_news_comprehensive(
    symbols: List[str],
    writer: ResilientDuckDBWriter,
    args: argparse.Namespace,
    stop_check: Optional[Callable[[], bool]] = None,
) -> int:
    """Cào TOÀN BỘ dữ liệu tin tức không ngoại trừ mã nào hay chuyên mục nào, lưu vào vesta_news.duckdb (F003/F004).
    
    Bao gồm 4 phân hệ tin tức:
    1. Tin tức CafeF theo toàn bộ danh mục mã (all symbols).
    2. Tin tức chuyên mục biên tập CafeF (all category news: TT chứng khoán, Vĩ mô, Bất động sản, DN, v.v.).
    3. Công bố thông tin doanh nghiệp CafeF Disclosures (core.cafef_disclosures).
    4. Báo chí tài chính & chính sách vĩ mô (Báo Nhân Dân, TBTC, VietnamFinance, Báo Chính Phủ).
    """
    logger.info("=" * 80)
    logger.info(">>> [KHỞI CHẠY PHÂN HỆ TIN TỨC TOÀN DIỆN (NEWS COMPREHENSIVE)]")
    logger.info("    CSDL ĐÍCH CHUYÊN BIỆT: db/vesta_news.duckdb")
    logger.info("    DANH MỤC: %d mã | TOÀN BỘ CHUYÊN MỤC BIÊN TẬP & CÔNG BỐ THÔNG TIN", len(symbols))
    logger.info("=" * 80)

    total_all_news = 0

    # 1. Tin tức CafeF theo mã cổ phiếu (Tất cả các mã, không ngoại trừ mã nào)
    logger.info("\n--- [1/4] CÀO TIN TỨC DOANH NGHIỆP CAFEF THEO MÃ (%d mã) ---", len(symbols))
    from crawlers import cafef_news
    delay = getattr(args, "delay", 0.4)
    force = getattr(args, "force", False)
    stock_news_written = 0

    try:
        con_news = db.connect_news()
        try:
            for idx, sym in enumerate(symbols, 1):
                if stop_check and stop_check():
                    logger.info("[!] Nhận tín hiệu dừng từ người dùng.")
                    break
                try:
                    cnt = cafef_news.run(sym, incremental=not force, force=force, con=con_news)
                    stock_news_written += cnt
                    if cnt > 0 or idx % 50 == 0 or idx == len(symbols):
                        logger.info("[%d/%d] %s: +%d tin bài CafeF mới (vesta_news.duckdb).", idx, len(symbols), sym, cnt)
                except Exception as e:
                    logger.debug("Bỏ qua tin bài %s: %s", sym, e)
                time.sleep(delay)
        finally:
            con_news.close()
    except Exception as ex_stock:
        logger.warning("[!] Lỗi cào tin tức CafeF theo mã: %s", ex_stock)

    total_all_news += stock_news_written
    logger.info("-> [1/4 Hoàn tất]: +%d tin bài CafeF theo mã.", stock_news_written)

    if stop_check and stop_check():
        return total_all_news

    # 2. Tin tức chuyên mục biên tập CafeF (Tất cả 9 chuyên mục, không ngoại trừ chuyên mục nào)
    logger.info("\n--- [2/4] CÀO TIN TỨC CHUYÊN MỤC BIÊN TẬP CAFEF (TẤT CẢ CHUYÊN MỤC) ---")
    cat_news_written = 0
    try:
        from crawlers.cafef_category_news import CATEGORY_IDS
        from crawlers import cafef_category_orchestrator
        max_p = getattr(args, "pages", 5)
        con_news = db.connect_news()
        try:
            valid_symbols = cafef_category_orchestrator.load_valid_symbols(con_news)
            existing_urls = cafef_category_orchestrator.load_existing_source_urls(con_news)
            for c_slug in CATEGORY_IDS.keys():
                if stop_check and stop_check():
                    break
                logger.info("  • Đang cào chuyên mục: [%s] (tối đa %d trang)...", c_slug, max_p)
                try:
                    res_cat = cafef_category_orchestrator.crawl_category_streaming(
                        cat=c_slug,
                        max_pages=max_p,
                        con=con_news,
                        valid_symbols=valid_symbols,
                        existing_urls=existing_urls,
                        max_concurrency=2,
                    )
                    w = res_cat.get("written", 0)
                    cat_news_written += w
                    logger.info("    -> [%s]: +%d tin bài mới đã ghi vào vesta_news.duckdb.", c_slug, w)
                except Exception as ex_cat:
                    logger.warning("    -> [!] Lỗi cào chuyên mục %s: %s", c_slug, ex_cat)
        finally:
            con_news.close()
    except Exception as ex_catorch:
        logger.warning("[!] Lỗi cào chuyên mục CafeF: %s", ex_catorch)

    total_all_news += cat_news_written
    logger.info("-> [2/4 Hoàn tất]: +%d tin bài chuyên mục CafeF.", cat_news_written)

    if stop_check and stop_check():
        return total_all_news

    # 3. Công bố thông tin CafeF Disclosures (core.cafef_disclosures)
    logger.info("\n--- [3/4] CÀO CÔNG BỐ THÔNG TIN CAFEF DISCLOSURES TOÀN THỊ TRƯỜNG ---")
    disc_written = 0
    try:
        from crawlers import crawl_cafef_disclosures
        disc_written = crawl_cafef_disclosures.crawl_live_disclosures(
            max_pages=getattr(args, "pages", 5),
            symbol="",
            delay=0.5,
            db_path=str(db.NEWS_DB_PATH),
        )
        logger.info("-> [3/4 Hoàn tất]: +%d bản ghi công bố thông tin (vesta_news.duckdb).", disc_written)
    except Exception as ex_disc:
        logger.warning("[!] Lỗi cào công bố thông tin: %s", ex_disc)

    total_all_news += disc_written

    if stop_check and stop_check():
        return total_all_news

    # 4. Báo chí tài chính & vĩ mô chính thống (Nhân Dân, TBTC, VietnamFinance, Chính Phủ)
    logger.info("\n--- [4/4] CÀO BÁO CHÍ TÀI CHÍNH & VĨ MÔ CHÍNH THỐNG ---")
    macro_press_written = run_category_news_macro(symbols, writer, args)
    total_all_news += macro_press_written
    logger.info("-> [4/4 Hoàn tất]: +%d tin bài báo chí vĩ mô (vesta_news.duckdb).", macro_press_written)

    logger.info("\n>>> HOÀN TẤT PHÂN HỆ TIN TỨC: TỔNG CỘNG +%d BẢN GHI MỚI VÀO vesta_news.duckdb <<<", total_all_news)
    return total_all_news


def run_category_order_book_vn100(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào sổ lệnh Level 2 & tính toán chỉ số OFI cho rổ VN100 (Vietcap Direct REST API)."""
    from crawlers.order_book_depth_vietcap import crawl_order_book_vn100
    target_path = str(writer.target_db) if hasattr(writer, "target_db") else str(PROJECT_ROOT / "db" / "admin" / "vesta_snapshot.duckdb")
    res = crawl_order_book_vn100(db_path=target_path)
    return res.get("order_book_records", 0)


def run_category_deep_screener(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> int:
    """Cào bộ lọc đa nhân tố chuyên sâu cho toàn bộ cổ phiếu thị trường (Vietcap IQ Direct Screening API)."""
    from crawlers.crawl_deep_screener import crawl_deep_screener
    target_path = str(writer.target_db) if hasattr(writer, "target_db") else str(PROJECT_ROOT / "db" / "admin" / "vesta_snapshot.duckdb")
    return crawl_deep_screener(db_path=target_path)


CATEGORIES_REGISTRY = {
    "reference": run_category_reference,
    "ohlcv": run_category_ohlcv,
    "intraday_1m": run_category_intraday_1m,
    "fundamentals": run_category_fundamentals,
    "news": run_category_news_comprehensive,
    "news_stock": run_category_news_stock,
    "news_macro": run_category_news_macro,
    "news_all": run_category_news_comprehensive,
    "events": run_category_events,
    "macro": run_category_macro,
    "governance": run_category_governance,
    "snapshots": run_category_snapshots,
    "order_book_vn100": run_category_order_book_vn100,
    "deep_screener": run_category_deep_screener,
}


# =============================================================================
# 4. INCREMENTAL LATEST CRAWLER (TỰ ĐỘNG CÀO TIẾN ĐẾN HÔM NAY - F001 -> F009)
# =============================================================================

def run_latest_modular(
    scope: str,
    symbols: List[str],
    writer: ResilientDuckDBWriter,
    args: argparse.Namespace,
    stop_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, int]:
    """Tự động phát hiện khoảng trống thời gian và cào bù dữ liệu mới nhất theo từng tùy chọn mô-đun (F001 -> F009).
    
    4 Tùy chọn Scope:
    1. ohlcv 1d/1m: Cập nhật nến 1D (vesta_snapshot.duckdb) & nến 1m (vesta_intraday_1m.duckdb) cho toàn bộ mã & mốc ngày.
    2. fundamentals: Cập nhật BCTC quý mới nhất (vesta_snapshot.duckdb) cho toàn bộ mã.
    3. news: Cập nhật toàn bộ tin tức không ngoại trừ mã nào hay chuyên mục nào (vesta_news.duckdb).
    4. all: Cập nhật toàn diện tất cả các phân hệ trên theo đúng CSDL chuyên biệt của từng loại.
    """
    today = dt.date.today().isoformat()
    scope_str = str(scope).lower().strip()
    logger.info("=" * 80)
    logger.info("BẮT ĐẦU CHẾ ĐỘ CẬP NHẬT MỚI NHẤT (LATEST INCREMENTAL CATCH-UP)")
    logger.info("TÙY CHỌN: [%s] | THỜI ĐIỂM: %s | TỔNG SỐ MÃ: %d", scope.upper(), today, len(symbols))
    logger.info("CSDL ĐÍCH: 1D/BCTC -> vesta_snapshot.duckdb | 1m -> vesta_intraday_1m.duckdb | News -> vesta_news.duckdb")
    logger.info("=" * 80)

    results: Dict[str, int] = {}
    is_all = "4" in scope_str or "all" in scope_str

    # --- 1. TÙY CHỌN: OHLCV 1D/1M ---
    if is_all or "1" in scope_str or "ohlcv" in scope_str:
        logger.info("\n" + "═" * 60)
        logger.info("[PHÂN HỆ 1/4] CẬP NHẬT GIÁ NẾN 1D & 1M TOÀN THỊ TRƯỜNG")
        logger.info("═" * 60)

        # 1.1. Nến ngày 1D
        logger.info("\n--- [1.1] Cập nhật nến ngày OHLCV 1D (Toàn bộ mã & ngày -> vesta_snapshot.duckdb) ---")
        args_1d = argparse.Namespace(**vars(args))
        args_1d.interval = "1D"
        bars_1d = run_category_ohlcv(symbols, writer, args_1d)
        results["ohlcv_1d"] = bars_1d
        logger.info("[+] Đã cập nhật +%d nến ngày 1D.", bars_1d)

        # 1.2. Nến phút 1m Intraday
        if not (stop_check and stop_check()):
            logger.info("\n--- [1.2] Cập nhật nến phút Intraday 1m (Toàn bộ mã -> vesta_intraday_1m.duckdb) ---")
            bars_1m = run_category_intraday_1m(symbols, writer, args)
            results["ohlcv_1m"] = bars_1m
            logger.info("[+] Đã cập nhật +%d nến phút 1m vào vesta_intraday_1m.duckdb.", bars_1m)

    if stop_check and stop_check():
        logger.info("[!] Nhận lệnh dừng từ người dùng. Kết thúc tiến trình.")
        writer.sync_buffer_to_target()
        return results

    # --- 2. TÙY CHỌN: FUNDAMENTALS ---
    if is_all or "2" in scope_str or "fundamentals" in scope_str:
        logger.info("\n" + "═" * 60)
        logger.info("[PHÂN HỆ 2/4] CẬP NHẬT BÁO CÁO TÀI CHÍNH QUÝ MỚI NHẤT (FUNDAMENTALS)")
        logger.info("═" * 60)
        args_fund = argparse.Namespace(**vars(args))
        args_fund.period = getattr(args, "period", "quarter")
        args_fund.report_type = getattr(args, "report_type", "all")
        stmts = run_category_fundamentals(symbols, writer, args_fund)
        results["fundamentals"] = stmts
        logger.info("[+] Đã cập nhật +%d BCTC quý vào vesta_snapshot.duckdb.", stmts)

    if stop_check and stop_check():
        logger.info("[!] Nhận lệnh dừng từ người dùng. Kết thúc tiến trình.")
        writer.sync_buffer_to_target()
        return results

    # --- 3. TÙY CHỌN: NEWS (TOÀN BỘ TIN TỨC KHÔNG NGOẠI TRỪ MÃ HAY CHUYÊN MỤC) ---
    if is_all or "3" in scope_str or "news" in scope_str:
        logger.info("\n" + "═" * 60)
        logger.info("[PHÂN HỆ 3/4] CẬP NHẬT TOÀN BỘ TIN TỨC & BÁO CHÍ (NEWS COMPREHENSIVE)")
        logger.info("═" * 60)
        news_cnt = run_category_news_comprehensive(symbols, writer, args, stop_check=stop_check)
        results["news"] = news_cnt

    if stop_check and stop_check():
        logger.info("[!] Nhận lệnh dừng từ người dùng. Kết thúc tiến trình.")
        writer.sync_buffer_to_target()
        return results

    # --- 4. BỔ SUNG KHI CHẠY ALL: SỰ KIỆN DOANH NGHIỆP & VĨ MÔ LÃI SUẤT ---
    if is_all:
        logger.info("\n" + "═" * 60)
        logger.info("[PHÂN HỆ 4/4] CẬP NHẬT SỰ KIỆN QUYỀN, CỔ TỨC & CHỈ SỐ VĨ MÔ")
        logger.info("═" * 60)
        events_cnt = run_category_events(symbols, writer, args)
        results["events"] = events_cnt

        macro_cnt = run_category_macro(symbols, writer, args)
        results["macro"] = macro_cnt

    # Đồng bộ bộ đệm an toàn nếu có dữ liệu chờ nạp
    writer.sync_buffer_to_target()
    logger.info("\n" + "═" * 80)
    logger.info(">>> HOÀN TẤT TOÀN BỘ TIẾN TRÌNH CẬP NHẬT MỚI NHẤT (SCOPE: %s) <<<", scope.upper())
    for k, v in results.items():
        logger.info("    • %s: +%d bản ghi", k, v)
    logger.info("═" * 80)
    return results


def run_latest_all(symbols: List[str], writer: ResilientDuckDBWriter, args: argparse.Namespace) -> None:
    """Tương thích ngược: Chạy toàn bộ hệ thống (all)."""
    scope = getattr(args, "scope", "all")
    run_latest_modular(scope, symbols, writer, args)


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
        choices=["latest", "category", "all", "simultaneous"],
        default="latest",
        help="Chế độ cào: 'latest' (tự động cào bù tiến đến hôm nay), 'category' (chọn 1 danh mục), 'all' (cào toàn bộ), 'simultaneous' (cào đồng thời 3 CSDL tạm & tự động sáp nhập)",
    )
    crawl_parser.add_argument(
        "--scope",
        default="all",
        help="Tùy chọn cập nhật khi chạy mode 'latest': '1. ohlcv 1d/1m', '2. fundamentals', '3. news', '4. all'",
    )
    crawl_parser.add_argument(
        "--category",
        choices=list(CATEGORIES_REGISTRY.keys()),
        default="ohlcv",
        help="Danh mục dữ liệu khi chạy mode 'category': reference, ohlcv, intraday_1m, fundamentals, news, news_macro, news_all, events, macro, governance, snapshots",
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
    crawl_parser.add_argument("--pages", type=int, default=5, help="Số trang tối đa cho crawler báo chí / tin tức")
    crawl_parser.add_argument("--force", action="store_true", help="Bắt buộc cào đè, không dùng checkpoint bỏ qua")
    crawl_parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mã để test")

    # 3. Lệnh pipeline (Điều phối chuỗi F000 -> F501)
    pipeline_parser = subparsers.add_parser("pipeline", help="Điều phối toàn bộ chuỗi quy trình lượng hóa (F000 -> F501)")
    pipeline_parser.add_argument("--all", action="store_true", help="Chạy toàn bộ 5 tầng từ F000 đến F501")
    pipeline_parser.add_argument("--stage", choices=["crawl", "preprocess", "model", "serving", "arena"], default="all", help="Chạy 1 tầng cụ thể")
    pipeline_parser.add_argument("--paths", type=int, default=10, help="Số Monte Carlo paths cho F501 Arena")
    pipeline_parser.add_argument("--seed", type=int, default=20260101, help="Seed ngẫu nhiên")

    # Tương thích nếu người dùng gõ trực tiếp --status hoặc --check
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái nhanh")
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Xử lý lệnh pipeline (F000 -> F501)
    if args.command == "pipeline":
        from src.pipeline.vesta_pipeline_orchestrator import VestaPipelineOrchestrator
        target_db = getattr(args, "db", DEFAULT_TARGET_DB)
        orchestrator = VestaPipelineOrchestrator(target_db=target_db)
        if args.stage and args.stage != "all":
            if args.stage == "arena":
                orchestrator.run_stage_arena(paths_per_situation=args.paths, seed=args.seed)
            elif args.stage == "crawl":
                orchestrator.run_stage_crawl()
            elif args.stage == "preprocess":
                orchestrator.run_stage_preprocess()
            elif args.stage == "model":
                orchestrator.run_stage_model()
            elif args.stage == "serving":
                orchestrator.run_stage_serving()
        else:
            orchestrator.run_full_pipeline(paths_per_situation=args.paths)
        return 0

    # 2. Xử lý lệnh status / check
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

        # Tự động suy luận mode nếu người dùng chỉ định --category
        if "--category" in sys.argv and "--mode" not in sys.argv:
            args.mode = "category"

        # Mode: simultaneous (chạy đồng thời 3 CSDL tạm & tự động sáp nhập)
        if args.mode == "simultaneous":
            from crawlers.parallel_multidb_orchestrator import run_simultaneous_crawling_pipeline
            limit = args.limit if args.limit else (None if args.symbols == "all" else len(symbols))
            run_simultaneous_crawling_pipeline(symbol_limit=limit, auto_merge=True)
            return 0

        # Mode: latest
        if args.mode == "latest":
            scope = getattr(args, "scope", "all")
            run_latest_modular(scope, symbols, writer, args)
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
