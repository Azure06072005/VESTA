"""src/crawlers/update_remaining_fundamentals.py

Tiến trình cập nhật toàn diện Báo cáo tài chính F005 cho toàn bộ thị trường:
- Nguồn: Direct CafeF BCTC REST API (apiweb.cafef.vn)
- Đầy đủ 5 phân hệ: Cân đối kế toán (balance_sheet), Kết quả kinh doanh (income_statement),
  Lưu chuyển tiền tệ (cash_flow), Chỉ số tài chính (ratio), Sức khỏe tài chính (financial_health).
- Tự động bỏ qua các mã đã có đầy đủ 5 phân hệ (không cào trùng lặp).
- Thứ tự ưu tiên: HOSE (375 mã) -> HNX (299 mã) -> UPCOM (818 mã).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
import time

import duckdb

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers import fundamentals
from etl import db
from etl.retry_failed_jobs import EmptyResultError

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_remaining_fundamentals")


def get_symbols_to_update(target_db: str, exchange: str | None = None) -> list[str]:
    """Lấy danh sách các mã cổ phiếu đang niêm yết chưa có dữ liệu financial_health."""
    con = duckdb.connect(target_db, read_only=True)
    
    # 1. Lấy danh sách đã hoàn tất
    done_rows = con.execute("SELECT DISTINCT symbol FROM core.fundamentals WHERE report_type = 'financial_health';").fetchall()
    done_set = {r[0].upper() for r in done_rows}

    # 2. Lấy danh sách mã theo sàn
    ex_filter = f"AND exchange = '{exchange.upper()}'" if exchange and exchange.lower() != "all" else ""
    query = f"""
        SELECT symbol 
        FROM core.dim_symbol 
        WHERE is_delisted IS NOT TRUE 
          AND length(symbol) = 3
          {ex_filter}
        ORDER BY symbol;
    """
    rows = con.execute(query).fetchall()
    con.close()

    candidates = [r[0].upper() for r in rows if r[0].upper() not in done_set]
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Cập nhật toàn bộ BCTC F005 cho các mã còn lại")
    parser.add_argument("--db", default=str(db.DB_PATH), help="Đường dẫn file DuckDB chính")
    parser.add_argument("--exchange", default="HOSE", help="Sàn cần cập nhật: HOSE, HNX, UPCOM, hoặc all")
    parser.add_argument("--delay", type=float, default=0.3, help="Thời gian nghỉ giữa các mã (giây)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng mã chạy thử")
    args = parser.parse_args()

    os.environ["VESTA_DB_PATH"] = os.path.abspath(args.db)
    db.DB_PATH = pathlib.Path(os.path.abspath(args.db))

    symbols = get_symbols_to_update(args.db, exchange=args.exchange)
    if args.limit:
        symbols = symbols[:args.limit]

    logger.info("=" * 80)
    logger.info("TIẾN TRÌNH CẬP NHẬT BCTC F005 CHO CÁC MÃ CÒN LẠI")
    logger.info("Database: %s", args.db)
    logger.info("Sàn lựa chọn: %s | Số mã cần cào: %d mã | Delay: %.2fs", args.exchange.upper(), len(symbols), args.delay)
    logger.info("=" * 80)

    if not symbols:
        logger.info("Toàn bộ các mã trên sàn %s đã có đầy đủ dữ liệu F005. Không cần cào thêm!", args.exchange.upper())
        return 0

    total_symbols = len(symbols)
    success_count = 0
    empty_count = 0
    failed_count = 0
    total_records = 0
    start_time = time.time()

    for idx, sym in enumerate(symbols, 1):
        pct = (idx / total_symbols) * 100
        logger.info("[%d/%d] (%.1f%%) Đang nạp BCTC cho %s...", idx, total_symbols, pct, sym)
        try:
            cnt = fundamentals.run(sym, report_type="all", period="quarter")
            if cnt > 0:
                success_count += 1
                total_records += cnt
                logger.info("  -> [OK] %s: +%d bản ghi BCTC mới.", sym, cnt)
            else:
                success_count += 1
                logger.info("  -> [OK] %s: Dữ liệu đã đồng bộ sẵn (+0).", sym)
        except EmptyResultError:
            empty_count += 1
            logger.info("  -> [Empty] %s: Doanh nghiệp chưa công bố BCTC.", sym)
        except Exception as e:
            failed_count += 1
            logger.warning("  -> [Lỗi] %s: %s", sym, e)

        time.sleep(args.delay)

    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("HOÀN TẤT ĐỢT CẬP NHẬT TRONG %.1f GIÂY (%.2f PHÚT)", duration, duration / 60)
    logger.info("  • Thành công: %d mã | Rỗng: %d mã | Lỗi: %d mã", success_count, empty_count, failed_count)
    logger.info("  • Tổng số bản ghi BCTC mới đã ghi: +%d bản ghi", total_records)
    logger.info("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
