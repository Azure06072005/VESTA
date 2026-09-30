"""src/crawlers/update_corporate_events.py

Crawl and update corporate actions & events across the Vietnamese stock market:
- Source: Vietstock Direct REST API (https://finance.vietstock.vn/data/eventstypedata)
- Zero vnstock dependency, zero API key requirement.
- Ingests structured cash dividend, stock dividend, bonus issues, and AGMs.
- Automatically calculates `payout_delay_days` to capture enterprise liquidity risks.
"""
from __future__ import annotations

import argparse
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

from crawlers import corporate_events  # noqa: E402
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_corporate_events")


def get_target_symbols(target_db: str, exchange: str | None = None, force: bool = False) -> list[str]:
    """Retrieves target equity symbols to crawl."""
    con = duckdb.connect(target_db, read_only=True)

    done_set = set()
    if not force:
        # Check symbols already having events with payout_delay_days calculated
        try:
            rows = con.execute("""
                SELECT DISTINCT symbol 
                FROM core.corporate_events 
                WHERE payout_delay_days IS NOT NULL;
            """).fetchall()
            done_set = {r[0].upper() for r in rows}
        except Exception:
            pass

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
    parser = argparse.ArgumentParser(description="Update corporate events and payout delay from Vietstock")
    parser.add_argument("--db", default=str(db.DB_PATH), help="Target DuckDB file path")
    parser.add_argument("--exchange", default="VN30", help="Exchange: VN30, HOSE, HNX, UPCOM, or all")
    parser.add_argument("--delay", type=float, default=0.25, help="Polite delay between requests (seconds)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of symbols to run")
    parser.add_argument("--force", action="store_true", help="Force re-crawl even if events exist")
    args = parser.parse_args()

    os.environ["VESTA_DB_PATH"] = os.path.abspath(args.db)
    db.DB_PATH = pathlib.Path(os.path.abspath(args.db))

    if args.exchange.upper() == "VN30":
        # Canonical VN30 list
        vn30_constituents = {
            "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
            "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
            "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
        }
        symbols = sorted(list(vn30_constituents))
    else:
        symbols = get_target_symbols(args.db, exchange=args.exchange, force=args.force)

    if args.limit:
        symbols = symbols[:args.limit]

    logger.info("=" * 80)
    logger.info("TIẾN TRÌNH CẬP NHẬT SỰ KIỆN DOANH NGHIỆP & ĐỘ TRỄ CỔ TỨC (F006)")
    logger.info("Nguồn dữ liệu: Vietstock Direct Events API (Hoàn toàn mở, không cần API Key)")
    logger.info("Database: %s", args.db)
    logger.info("Phạm vi: %s | Số mã cần cào: %d mã | Delay: %.2fs", args.exchange.upper(), len(symbols), args.delay)
    logger.info("=" * 80)

    if not symbols:
        logger.info("Toàn bộ các mã trong phạm vi đã có đầy đủ dữ liệu sự kiện mới. Không cần cào thêm!")
        return 0

    total_symbols = len(symbols)
    success_count = 0
    empty_count = 0
    failed_count = 0
    total_events = 0
    start_time = time.time()

    for idx, sym in enumerate(symbols, 1):
        pct = (idx / total_symbols) * 100
        logger.info("[%d/%d] (%.1f%%) Đang nạp sự kiện cho %s...", idx, total_symbols, pct, sym)
        try:
            cnt = corporate_events.run(sym)
            if cnt > 0:
                success_count += 1
                total_events += cnt
                logger.info("  -> [OK] %s: +%d sự kiện doanh nghiệp (cổ tức, ĐHCĐ).", sym, cnt)
            else:
                empty_count += 1
                logger.info("  -> [Empty] %s: Doanh nghiệp không có sự kiện phát sinh.", sym)
        except EmptyResultError:
            empty_count += 1
            logger.info("  -> [Empty] %s: Doanh nghiệp chưa có sự kiện nào.", sym)
        except Exception as e:
            failed_count += 1
            logger.warning("  -> [Lỗi] %s: %s", sym, e)

        time.sleep(args.delay)

    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("HOÀN TẤT ĐỢT CẬP NHẬT TRONG %.1f GIÂY (%.2f PHÚT)", duration, duration / 60)
    logger.info("  • Thành công: %d mã | Rỗng: %d mã | Lỗi: %d mã", success_count, empty_count, failed_count)
    logger.info("  • Tổng số sự kiện doanh nghiệp đã nạp: +%d bản ghi", total_events)
    logger.info("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
