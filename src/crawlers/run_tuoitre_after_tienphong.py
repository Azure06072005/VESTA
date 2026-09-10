"""VESTA Automated Tuổi Trẻ Deep Historical Backfill Runner.

Waits for any active DuckDB write locks (such as the ongoing Tiền Phong crawler)
to release, then automatically executes the full historical backfill of
Báo Tuổi Trẻ Zone 11 (Kinh doanh) from Page 31 up to Page 4,000 (~2009 boundary).
"""
import sys
import time
import logging
from pathlib import Path

# Workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers.deep_portal_crawler import get_db_connection, crawl_tuoitre

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tuoitre_auto_runner")

import argparse

def wait_for_lock_and_run(start_page: int = 100, max_pages: int = 3900, zones: list[int] = [11]) -> None:
    logger.info("Checking DuckDB availability for Tuổi Trẻ historical backfill...")
    con = None
    attempt = 0
    while con is None:
        try:
            con = get_db_connection()
            logger.info("Successfully acquired DuckDB write lock! Starting Tuổi Trẻ crawl.")
        except Exception as e:
            attempt += 1
            if attempt % 6 == 1:
                logger.info(f"Database currently locked by previous crawler (attempt {attempt}). Waiting 10s...")
            time.sleep(10)

    try:
        t0 = time.time()
        logger.info(f"Starting Tuổi Trẻ Zone {zones} crawl from Page {start_page} up to {start_page + max_pages - 1}...")
        total_saved = crawl_tuoitre(con, max_pages=max_pages, fetch_body=True, start_page=start_page, target_zones=zones)
        elapsed = time.time() - t0
        logger.info(f"TUỔI TRẺ HISTORICAL CRAWL COMPLETED: {total_saved} articles saved in {elapsed:.2f} seconds.")
    finally:
        con.close()
        logger.info("DuckDB connection closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tuổi Trẻ Auto Backfill Runner")
    parser.add_argument("--start-page", type=int, default=100, help="Page to resume from")
    parser.add_argument("--max-pages", type=int, default=3901, help="Max pages to crawl")
    parser.add_argument("--zones", type=str, default="11", help="Zones to crawl")
    args = parser.parse_args()
    target_zones = [int(z.strip()) for z in args.zones.split(",") if z.strip().isdigit()]
    wait_for_lock_and_run(start_page=args.start_page, max_pages=args.max_pages, zones=target_zones)
