"""src/crawlers/crawl_all_ohlcv_fundamentals.py

VESTA Dedicated All-in-One Crawler for OHLCV & Fundamentals on Vnstock.
Cào dữ liệu lịch sử giá nến (OHLCV) và Báo cáo tài chính (BCTC) cho toàn bộ mã chứng khoán:
1. OHLCV (core.market_ohlcv_daily):
   - Cào lịch sử giá nến ngày từ 2000 đến hiện tại (2026-09-18) qua VCI / vnstock_data.
   - Chuẩn hóa cột: symbol, date, open, high, low, close, volume, fetched_at.
2. Fundamentals (core.fundamentals):
   - Cào 4 phân hệ: Cân đối kế toán (balance_sheet), Kết quả kinh doanh (income_statement),
     Lưu chuyển tiền tệ (cash_flow), Chỉ số tài chính (ratio).
   - Lưu trữ theo chuẩn Point-in-Time (PIT) với kỳ báo cáo (period_end) và ngày công bố ước lượng (available_at).

CÁC TÍNH NĂNG ĐẶC BIỆT:
- Tự động nạp toàn bộ 1,522 mã niêm yết (HOSE, HNX, UPCOM) từ core.dim_symbol (lọc bỏ trái phiếu, chứng quyền).
- Hỗ trợ Checkpoint & Resume: Tự động ghi nhận vào meta.crawl_progress, chạy lại sẽ bỏ qua mã đã xong.
- Rate-Limit Guard: Tự động phát hiện lỗi hạn mức gọi API, ngủ 45 giây và thử lại tối đa 3 lần.
- Windows Lock Resilience: Tích hợp ResilientDuckDBWriter chống xung đột khóa file database.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
import time
from typing import List, Optional, Tuple

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

from crawlers import fundamentals, market_ohlcv
from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
from crawlers.track_crawling_progress import VN30_SYMBOLS
from etl import db
from etl.retry_failed_jobs import EmptyResultError

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crawl_all_ohlcv_fundamentals")


def init_progress_table(target_db: str) -> None:
    """Đảm bảo bảng theo dõi tiến độ meta.crawl_progress đã tồn tại."""
    ddl = """
    CREATE SCHEMA IF NOT EXISTS meta;
    CREATE SCHEMA IF NOT EXISTS core;
    CREATE TABLE IF NOT EXISTS meta.crawl_progress (
        dataset_name  VARCHAR NOT NULL,
        symbol        VARCHAR NOT NULL,
        status        VARCHAR NOT NULL,
        retry_count   INTEGER NOT NULL DEFAULT 0,
        last_attempt  TIMESTAMP,
        PRIMARY KEY (dataset_name, symbol)
    );
    CREATE TABLE IF NOT EXISTS core.market_ohlcv_1m (
        symbol     VARCHAR NOT NULL,
        time       TIMESTAMP NOT NULL,
        open       DOUBLE,
        high       DOUBLE,
        low        DOUBLE,
        close      DOUBLE,
        volume     BIGINT,
        fetched_at TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, time)
    );
    """
    try:
        con = duckdb.connect(target_db, read_only=False)
        con.execute(ddl)
        con.close()
    except Exception as e:
        logger.debug("Không thể tạo DDL trực tiếp trên %s: %s", target_db, e)


def record_progress(
    writer: ResilientDuckDBWriter,
    dataset_name: str,
    symbol: str,
    status: str,
    retry_count: int = 0,
) -> None:
    """Ghi nhận trạng thái cào của mã cổ phiếu vào meta.crawl_progress."""
    now = dt.datetime.now()

    def _update(con: duckdb.DuckDBPyConnection):
        con.execute(
            """
            INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                status = EXCLUDED.status,
                retry_count = EXCLUDED.retry_count,
                last_attempt = EXCLUDED.last_attempt;
            """,
            [dataset_name, symbol.upper(), status, retry_count, now],
        )

    try:
        writer.execute_with_retry(_update)
    except Exception as e:
        logger.warning("Không thể cập nhật crawl_progress cho %s/%s: %s", dataset_name, symbol, e)


def get_all_symbols(target_db: str, category: str = "all") -> List[str]:
    """Lấy danh sách mã cổ phiếu cần cào từ database."""
    category = category.strip().lower()
    if category == "vn30":
        return VN30_SYMBOLS.copy()

    if category not in ("all", "all_equities"):
        # Phân tách danh sách tùy chọn
        return [s.strip().upper() for s in category.split(",") if s.strip()]

    # Lấy toàn bộ mã cổ phiếu niêm yết (độ dài 3 ký tự, không phải trái phiếu hay mã hủy niêm yết)
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
    except Exception as e:
        logger.warning("Không thể đọc core.dim_symbol từ %s: %s. Thử đường dẫn canonical...", target_db, e)

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

    logger.warning("Không đọc được dim_symbol, fallback về danh sách VN30 (%d mã)", len(VN30_SYMBOLS))
    return VN30_SYMBOLS.copy()


def get_completed_symbols(target_db: str, dataset_name: str) -> set[str]:
    """Lấy danh sách các mã đã cào thành công để bỏ qua."""
    query = f"""
        SELECT symbol 
        FROM meta.crawl_progress 
        WHERE dataset_name = '{dataset_name}' 
          AND status IN ('success', 'empty')
    """
    try:
        con = duckdb.connect(target_db, read_only=True)
        rows = con.execute(query).fetchall()
        con.close()
        return {r[0].upper() for r in rows}
    except Exception:
        return set()


# =============================================================================
# WORKER: CÀO OHLCV
# =============================================================================

def crawl_ohlcv_for_symbol(
    symbol: str,
    writer: ResilientDuckDBWriter,
    interval: str = "1D",
    start_date: str = "2000-01-01",
    end_date: Optional[str] = None,
    max_retries: int = 3,
) -> Tuple[str, int]:
    """Cào dữ liệu nến cho một mã cổ phiếu (Hỗ trợ 1D nến ngày từ 2000 hoặc 1m nến phút)."""
    dataset_name = "market_ohlcv_daily" if interval.upper() == "1D" else "market_ohlcv_1m"
    if end_date is None:
        end_date = dt.date.today().isoformat()

    for attempt in range(1, max_retries + 1):
        try:
            if interval.upper() == "1D":
                # Lấy dữ liệu nến ngày toàn bộ lịch sử (2000 -> nay)
                raw_df = market_ohlcv.fetch_raw(symbol, start=start_date, end=end_date)
                normalized_df = market_ohlcv.normalize_ohlcv(raw_df, symbol)

                def _write_action(con: duckdb.DuckDBPyConnection) -> int:
                    return market_ohlcv.write_ohlcv(normalized_df, con=con)

                row_count = writer.execute_with_retry(_write_action)
            else:
                # Lấy nến 1 phút (1m) độ dài tối đa server cho phép (length='1Y')
                try:
                    from vnstock_data import Market
                    mkt = Market()
                    raw_df = mkt.equity(symbol).ohlcv(length="1Y", interval="1m")
                except Exception:
                    from vnstock.api.quote import Quote
                    raw_df = Quote(symbol=symbol, source="VCI").history(start=start_date, end=end_date, interval="1m")

                if raw_df is None or raw_df.empty:
                    raise EmptyResultError(f"Không có dữ liệu nến 1m cho {symbol}")

                clean_df = raw_df.copy()
                clean_df["symbol"] = symbol
                time_col = "time" if "time" in clean_df.columns else "date"
                clean_df["time"] = pd.to_datetime(clean_df[time_col])
                clean_df["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                req_cols = ["symbol", "time", "open", "high", "low", "close", "volume", "fetched_at"]
                clean_df = clean_df[req_cols].dropna(subset=["time"])

                def _write_action(con: duckdb.DuckDBPyConnection) -> int:
                    con.register("df_1m", clean_df)
                    con.execute("""
                        INSERT INTO core.market_ohlcv_1m 
                        SELECT * FROM df_1m 
                        ON CONFLICT (symbol, time) DO NOTHING;
                    """)
                    con.unregister("df_1m")
                    return len(clean_df)

                row_count = writer.execute_with_retry(_write_action)

            record_progress(writer, dataset_name, symbol, status="success", retry_count=attempt - 1)
            return "success", row_count

        except EmptyResultError:
            record_progress(writer, dataset_name, symbol, status="empty", retry_count=attempt - 1)
            return "empty", 0

        except Exception as e:
            err_msg = str(e)
            is_ratelimit = "rate limit" in err_msg.lower() or "giới hạn" in err_msg.lower() or "429" in err_msg
            if is_ratelimit:
                wait_sec = 45
                logger.warning("  -> [RateLimit] Vượt hạn mức gọi vnstock khi cào OHLCV %s. Nghỉ %ds (Thử lại %d/%d)...", symbol, wait_sec, attempt, max_retries)
                time.sleep(wait_sec)
                continue

            if attempt < max_retries:
                time.sleep(attempt * 2.0)
                continue

            logger.warning("  -> [Lỗi] Không thể cào OHLCV cho %s: %s", symbol, e)
            record_progress(writer, dataset_name, symbol, status="failed", retry_count=attempt)
            return "failed", 0

    return "failed", 0


# =============================================================================
# WORKER: CÀO BÁO CÁO TÀI CHÍNH (FUNDAMENTALS)
# =============================================================================

def crawl_fundamentals_for_symbol(
    symbol: str,
    writer: ResilientDuckDBWriter,
    period: str = "quarter",
    report_type: str = "all",
    max_retries: int = 3,
) -> Tuple[str, int]:
    """Cào BCTC (CĐKT, KQKD, LCTT, Ratios) cho một mã cổ phiếu."""
    dataset_name = f"fundamentals_{period}"
    reports_to_crawl = list(fundamentals.REPORT_TYPES.keys()) if report_type == "all" else [report_type]

    for attempt in range(1, max_retries + 1):
        try:
            total_written = 0
            any_success = False
            last_empty_err = None

            for rt in reports_to_crawl:
                try:
                    raw_df = fundamentals.fetch_raw(symbol, rt, period=period)
                    normalized_df = fundamentals.format_melted_statement(raw_df, symbol, rt)

                    def _write_action(con: duckdb.DuckDBPyConnection) -> int:
                        return fundamentals.write_statements(normalized_df, con=con)

                    cnt = writer.execute_with_retry(_write_action)
                    total_written += cnt
                    any_success = True
                except EmptyResultError as ere:
                    last_empty_err = ere
                    continue
                except Exception as ex_rt:
                    logger.debug("Lỗi mục %s cho %s: %s", rt, symbol, ex_rt)

            if any_success:
                record_progress(writer, dataset_name, symbol, status="success", retry_count=attempt - 1)
                return "success", total_written
            elif last_empty_err is not None:
                record_progress(writer, dataset_name, symbol, status="empty", retry_count=attempt - 1)
                return "empty", 0
            else:
                raise RuntimeError(f"Không có mục BCTC nào thành công cho {symbol}")

        except Exception as e:
            err_msg = str(e)
            is_ratelimit = "rate limit" in err_msg.lower() or "giới hạn" in err_msg.lower() or "429" in err_msg
            if is_ratelimit:
                wait_sec = 45
                logger.warning("  -> [RateLimit] Vượt hạn mức gọi vnstock khi cào BCTC %s. Nghỉ %ds (Thử lại %d/%d)...", symbol, wait_sec, attempt, max_retries)
                time.sleep(wait_sec)
                continue

            if attempt < max_retries:
                time.sleep(attempt * 2.0)
                continue

            logger.warning("  -> [Lỗi] Không thể cào BCTC cho %s: %s", symbol, e)
            record_progress(writer, dataset_name, symbol, status="failed", retry_count=attempt)
            return "failed", 0

    return "failed", 0


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VESTA Dedicated All-in-One Crawler for OHLCV & Fundamentals on Vnstock"
    )
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn DuckDB chính (mặc định vesta_snapshot.duckdb)")
    parser.add_argument("--mode", choices=["all", "ohlcv", "fundamentals"], default="all", help="Chế độ cào: ohlcv, fundamentals, hoặc all")
    parser.add_argument("--symbols", default="all", help="Danh sách mã: 'all' (1,522 mã niêm yết), 'vn30', hoặc danh sách cách nhau bằng dấu phẩy")
    parser.add_argument("--interval", choices=["1D", "1m"], default="1D", help="Khung thời gian nến: 1D (ngày, từ 2000 đến nay) hoặc 1m (1 phút, tối đa 1 năm)")
    parser.add_argument("--start", default="2000-01-01", help="Ngày bắt đầu lấy giá OHLCV (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="Ngày kết thúc lấy giá OHLCV (mặc định: hôm nay)")
    parser.add_argument("--period", choices=["quarter", "year"], default="quarter", help="Kỳ Báo cáo tài chính (quarter hoặc year)")
    parser.add_argument("--report-type", default="all", help="Loại BCTC: all, balance_sheet, income_statement, cash_flow, ratio")
    parser.add_argument("--delay", type=float, default=0.4, help="Thời gian nghỉ giữa các mã (giây, ví dụ: 1.0 cho 1s delay)")
    parser.add_argument("--force", action="store_true", help="Bắt buộc cào lại toàn bộ, không bỏ qua các mã đã cào trước đó")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mã cào (dùng để test)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Đồng bộ cấu hình môi trường DB
    os.environ["VESTA_DB_PATH"] = os.path.abspath(args.db)
    db.DB_PATH = pathlib.Path(os.path.abspath(args.db))
    writer = ResilientDuckDBWriter(target_db=args.db)
    init_progress_table(writer.target_db)

    symbols = get_all_symbols(writer.target_db, category=args.symbols)
    if args.limit:
        symbols = symbols[: args.limit]

    logger.info("=" * 80)
    logger.info("KHỞI ĐỘNG CRAWLER TOÀN DIỆN VNSTOCK (OHLCV & FUNDAMENTALS)")
    logger.info("Database đích: %s", writer.target_db)
    logger.info("Chế độ cào: %s | Danh mục: %s (%d mã) | Delay: %.2fs", args.mode.upper(), args.symbols, len(symbols), args.delay)
    logger.info("Cờ Force: %s", "BẬT (Cào lại đè lên)" if args.force else "TẮT (Tự động bỏ qua mã đã có)")
    logger.info("=" * 80)

    start_time = time.time()
    total_ohlcv_rows = 0
    total_fund_rows = 0

    # Phân hệ 1: Cào OHLCV
    if args.mode in ["all", "ohlcv"]:
        ohlcv_ds = "market_ohlcv_daily" if args.interval.upper() == "1D" else "market_ohlcv_1m"
        completed_ohlcv = set() if args.force else get_completed_symbols(writer.target_db, ohlcv_ds)
        to_crawl_ohlcv = [s for s in symbols if s not in completed_ohlcv]
        logger.info("\n>>> [1/2] BẮT ĐẦU CÀO OHLCV %s (Còn lại: %d/%d mã) <<<", args.interval.upper(), len(to_crawl_ohlcv), len(symbols))

        for idx, sym in enumerate(to_crawl_ohlcv, 1):
            pct = (idx / len(to_crawl_ohlcv)) * 100
            logger.info("[%d/%d] (%.1f%%) Đang cào OHLCV (%s) cho %s...", idx, len(to_crawl_ohlcv), pct, args.interval.upper(), sym)
            status, count = crawl_ohlcv_for_symbol(sym, writer, interval=args.interval, start_date=args.start, end_date=args.end)
            if status == "success":
                total_ohlcv_rows += count
                logger.info("  -> [OK] %s: +%d nến %s.", sym, count, args.interval)
            elif status == "empty":
                logger.info("  -> [Empty] %s: Không có dữ liệu giao dịch.", sym)
            else:
                logger.warning("  -> [Failed] %s: Cào thất bại.", sym)
            time.sleep(args.delay)

    # Phân hệ 2: Cào BCTC
    if args.mode in ["all", "fundamentals"]:
        fund_dataset = f"fundamentals_{args.period}"
        completed_fund = set() if args.force else get_completed_symbols(writer.target_db, fund_dataset)
        to_crawl_fund = [s for s in symbols if s not in completed_fund]
        logger.info("\n>>> [2/2] BẮT ĐẦU CÀO BÁO CÁO TÀI CHÍNH (%s) (Còn lại: %d/%d mã) <<<", args.period.upper(), len(to_crawl_fund), len(symbols))

        for idx, sym in enumerate(to_crawl_fund, 1):
            pct = (idx / len(to_crawl_fund)) * 100
            logger.info("[%d/%d] (%.1f%%) Đang cào BCTC cho %s (period=%s)...", idx, len(to_crawl_fund), pct, sym, args.period)
            status, count = crawl_fundamentals_for_symbol(sym, writer, period=args.period, report_type=args.report_type)
            if status == "success":
                total_fund_rows += count
                logger.info("  -> [OK] %s: +%d bản ghi BCTC.", sym, count)
            elif status == "empty":
                logger.info("  -> [Empty] %s: Doanh nghiệp không có BCTC.", sym)
            else:
                logger.warning("  -> [Failed] %s: Cào thất bại.", sym)
            time.sleep(args.delay)

    # Đồng bộ dữ liệu đệm nếu có
    writer.sync_buffer_to_target()

    duration = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("HOÀN TẤT TIẾN TRÌNH CÀO TRONG %.2f GIÂY", duration)
    if args.mode in ["all", "ohlcv"]:
        logger.info("  • Tổng nến OHLCV mới/cập nhật: +%d bản ghi", total_ohlcv_rows)
    if args.mode in ["all", "fundamentals"]:
        logger.info("  • Tổng Báo cáo tài chính mới/cập nhật: +%d bản ghi", total_fund_rows)
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
