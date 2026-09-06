"""Batch Equity Enhancer for Corporate Events and Fundamentals.

Quét và tự động nạp bổ sung toàn diện cho các mã cổ phiếu còn thiếu:
1. Lịch sự kiện doanh nghiệp & Cổ tức (`core.corporate_events`).
2. Báo cáo tài chính doanh nghiệp: Cân đối kế toán, Kết quả kinh doanh, Lưu chuyển tiền tệ (`core.fundamentals`).

Ưu tiên các mã có thanh khoản cao nhất năm 2026 (VN30, Large Cap, Mid Cap).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers import corporate_events
from crawlers import fundamentals
from etl import db
from etl.retry_failed_jobs import EmptyResultError

logger = logging.getLogger(__name__)


def get_active_missing_symbols(duckdb_path: str = "d:/VESTA/db/vesta.duckdb", target: str = "events") -> list[str]:
    """Tìm danh sách cổ phiếu doanh nghiệp (3 ký tự) đang giao dịch tích cực năm 2026 nhưng còn thiếu dữ liệu."""
    con = duckdb.connect(duckdb_path, read_only=True)
    if target == "events":
        query = """
            SELECT o.symbol, sum(o.volume) as total_vol
            FROM core.market_ohlcv_daily o
            LEFT JOIN core.corporate_events e ON o.symbol = e.symbol
            WHERE e.symbol IS NULL AND o.date >= '2026-01-01' AND length(o.symbol) = 3
            GROUP BY o.symbol
            ORDER BY total_vol DESC
        """
    else:
        query = """
            SELECT o.symbol, sum(o.volume) as total_vol
            FROM core.market_ohlcv_daily o
            LEFT JOIN core.fundamentals f ON o.symbol = f.symbol
            WHERE f.symbol IS NULL AND o.date >= '2026-01-01' AND length(o.symbol) = 3
            GROUP BY o.symbol
            ORDER BY total_vol DESC
        """
    rows = con.execute(query).fetchall()
    con.close()
    return [r[0] for r in rows]


def enhance_corporate_events(symbols: list[str], delay: float = 1.2) -> int:
    """Nạp sự kiện quyền và cổ tức cho danh sách mã với cơ chế chống xung đột lock và RateLimit."""
    total_events = 0
    logger.info(f"==> Bắt đầu nạp Sự kiện & Cổ tức cho {len(symbols)} mã cổ phiếu...")

    for i, sym in enumerate(symbols, 1):
        logger.info(f"[{i}/{len(symbols)}] Đang xử lý sự kiện: {sym}...")
        for attempt in range(1, 6):
            try:
                n = corporate_events.run(sym)
                total_events += n
                logger.info(f"  -> [OK] {sym}: Đã lưu +{n} sự kiện doanh nghiệp.")
                break
            except EmptyResultError:
                logger.info(f"  -> [Empty] {sym}: Không có sự kiện nào được công bố.")
                break
            except Exception as e:
                err_msg = str(e)
                if "rate limit" in err_msg.lower() or "giới hạn" in err_msg.lower():
                    logger.warning(f"  -> [RateLimit] Vượt hạn mức gọi vnstock. Tạm nghỉ 45s trước khi thử lại {sym}...")
                    time.sleep(45)
                    continue
                elif "Cannot open file" in err_msg or "being used by another process" in err_msg:
                    wait = attempt * 1.5
                    logger.warning(f"  -> [Lock retry {attempt}/5] DB bị lock khi ghi {sym}. Chờ {wait}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"  -> [Skip] Lỗi cào sự kiện {sym}: {e}")
                    break
        time.sleep(delay)

    return total_events


def enhance_fundamentals(symbols: list[str], delay: float = 1.5) -> int:
    """Nạp báo cáo tài chính (BCTC) cho danh sách mã với cơ chế chống xung đột lock và RateLimit."""
    total_records = 0
    logger.info(f"==> Bắt đầu nạp Báo cáo tài chính cho {len(symbols)} mã cổ phiếu...")

    for i, sym in enumerate(symbols, 1):
        logger.info(f"[{i}/{len(symbols)}] Đang xử lý BCTC: {sym}...")
        for attempt in range(1, 6):
            try:
                n = fundamentals.run(sym, report_type="all", period="quarter")
                total_records += n
                logger.info(f"  -> [OK] {sym}: Đã lưu +{n} bản ghi BCTC.")
                break
            except EmptyResultError:
                logger.info(f"  -> [Empty] {sym}: Dữ liệu BCTC trống.")
                break
            except Exception as e:
                err_msg = str(e)
                if "rate limit" in err_msg.lower() or "giới hạn" in err_msg.lower():
                    logger.warning(f"  -> [RateLimit] Vượt hạn mức gọi vnstock. Tạm nghỉ 45s trước khi thử lại {sym}...")
                    time.sleep(45)
                    continue
                elif "Cannot open file" in err_msg or "being used by another process" in err_msg:
                    wait = attempt * 1.5
                    logger.warning(f"  -> [Lock retry {attempt}/5] DB bị lock khi ghi {sym}. Chờ {wait}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"  -> [Skip] Lỗi cào BCTC {sym}: {e}")
                    break
        time.sleep(delay)

    return total_records


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Batch Equity Enhancer (Corporate Events & Fundamentals)")
    parser.add_argument("--mode", choices=["all", "events", "fundamentals"], default="all")
    parser.add_argument("--limit", type=int, default=50, help="Số lượng mã ưu tiên nạp trong đợt này")
    parser.add_argument("--symbols", nargs="+", help="Chỉ định danh sách mã cụ thể")
    parser.add_argument("--delay", type=float, default=1.2, help="Độ trễ giãn cách giữa các mã (giây)")

    args = parser.parse_args()

    if args.mode in ["all", "events"]:
        symbols_events = args.symbols or get_active_missing_symbols(target="events")[:args.limit]
        logger.info(f"Danh sách mã ưu tiên nạp Sự kiện ({len(symbols_events)} mã): {symbols_events[:10]}...")
        ev_count = enhance_corporate_events(symbols_events, delay=args.delay)
        print(f"Tổng số sự kiện doanh nghiệp đã nạp: {ev_count}")

    if args.mode in ["all", "fundamentals"]:
        symbols_fund = args.symbols or get_active_missing_symbols(target="fundamentals")[:args.limit]
        logger.info(f"Danh sách mã ưu tiên nạp BCTC ({len(symbols_fund)} mã): {symbols_fund[:10]}...")
        fund_count = enhance_fundamentals(symbols_fund, delay=args.delay)
        print(f"Tổng số bản ghi BCTC đã nạp: {fund_count}")


if __name__ == "__main__":
    main()
