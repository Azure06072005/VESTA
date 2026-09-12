"""VESTA Automated Tuổi Trẻ Deep Historical Backfill Runner.

Waits for any active DuckDB write locks (such as the ongoing Tiền Phong crawler)
to release, then automatically executes the deep historical timeline backfill of
Báo Tuổi Trẻ across specified zones (11: Kinh doanh, 89: Bất động sản, 10: Thế giới, 3: Thời sự).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
import sys
import time

# Workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers.tuoitre_crawler import crawl_tuoitre_deep, get_safe_db_connection

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tuoitre_auto_runner")


def wait_for_lock_and_run(
    start_page: int = 881,
    max_pages: int = 500,
    zones: list[int] = [11, 89, 10, 3],
    workers: int = 8,
) -> int:
    logger.info("Checking DuckDB availability for Tuổi Trẻ historical backfill...")
    con = None
    attempt = 0
    while con is None:
        try:
            con = get_safe_db_connection()
            logger.info("Successfully acquired DuckDB write lock! Starting Tuổi Trẻ crawl.")
        except Exception as e:
            attempt += 1
            if attempt % 6 == 1:
                logger.info(f"Database currently locked by previous crawler ({e}). Waiting 10s...")
            time.sleep(10)

    try:
        t0 = time.time()
        logger.info(f"Starting Tuổi Trẻ Zone {zones} crawl from Page {start_page} up to {start_page + max_pages - 1}...")
        total_saved = crawl_tuoitre_deep(
            con,
            start_page=start_page,
            max_pages=max_pages,
            target_zones=zones,
            fetch_body=True,
            workers=workers,
        )
        elapsed = time.time() - t0
        logger.info(f"TUỔI TRẺ HISTORICAL CRAWL COMPLETED: {total_saved} articles saved in {elapsed:.2f} seconds.")
        return total_saved
    finally:
        con.close()
        logger.info("DuckDB connection closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tuổi Trẻ Auto Backfill Runner")
    parser.add_argument("--start-page", type=int, default=881, help="Page to resume from (e.g. 881)")
    parser.add_argument("--max-pages", type=int, default=500, help="Max pages to crawl per zone")
    parser.add_argument("--zones", type=str, default="11,89,10,3", help="Comma-separated zones (11,89,10,3)")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent detail worker threads")
    args = parser.parse_args()

    target_zones = [int(z.strip()) for z in args.zones.split(",") if z.strip().isdigit()]
    wait_for_lock_and_run(
        start_page=args.start_page,
        max_pages=args.max_pages,
        zones=target_zones,
        workers=args.workers,
    )
