"""scratch/sync_news_to_snapshot.py

Đồng bộ dữ liệu tin tức và văn bản điều hành mới nhất từ vesta_news.duckdb sang vesta_snapshot.duckdb.
- An toàn: Không chạm tới vesta_backup.duckdb.
- Hiệu năng: Sử dụng DuckDB ATTACH trực tiếp in-engine để đồng bộ hàng trăm nghìn bản ghi chỉ trong vài mili-giây.
- Đầy đủ: Đồng bộ core.news, core.news_resources và core.macro_policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import pathlib
import sys

import duckdb

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
NEWS_DB_PATH = PROJECT_ROOT / "db" / "vesta_news.duckdb"
SNAPSHOT_DB_PATH = PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sync_news")


def sync_news_data(
    since_date: str = "2026-09-01",
    news_db: pathlib.Path = NEWS_DB_PATH,
    snapshot_db: pathlib.Path = SNAPSHOT_DB_PATH,
) -> dict[str, dict[str, int]]:
    if not news_db.exists():
        raise FileNotFoundError(f"Không tìm thấy news DB tại: {news_db}")
    if not snapshot_db.exists():
        raise FileNotFoundError(f"Không tìm thấy snapshot DB tại: {snapshot_db}")

    logger.info("=" * 70)
    logger.info("ĐỒNG BỘ DỮ LIỆU TIN TỨC SANG SNAPSHOT DB")
    logger.info("Nguồn: %s", news_db)
    logger.info("Đích:  %s", snapshot_db)
    logger.info("Biên thời gian: từ %s đến nay", since_date)
    logger.info("=" * 70)

    con = duckdb.connect(str(snapshot_db))
    stats = {}

    try:
        # 1. Attach news_db dưới quyền READ_ONLY
        con.execute(f"ATTACH '{news_db}' AS news_db (READ_ONLY);")

        # 2. Đồng bộ core.news (Tin doanh nghiệp)
        cnt_news_before = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
        max_news_before = con.execute("SELECT max(published_at) FROM core.news").fetchone()[0]

        con.execute(f"""
            INSERT OR IGNORE INTO core.news
            SELECT * FROM news_db.core.news
            WHERE published_at >= '{since_date}'
        """)

        cnt_news_after = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
        max_news_after = con.execute("SELECT max(published_at) FROM core.news").fetchone()[0]
        news_added = cnt_news_after - cnt_news_before
        stats["core.news"] = {
            "before": cnt_news_before,
            "after": cnt_news_after,
            "added": news_added,
            "max_published": str(max_news_after),
        }
        logger.info(
            "[core.news] +%d bản ghi mới (Tổng: %d, Max: %s)",
            news_added, cnt_news_after, max_news_after
        )

        # 3. Đồng bộ core.news_resources (Báo chí tài chính & Cơ quan điều hành, Hiệp hội)
        cnt_res_before = con.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
        max_res_before = con.execute("SELECT max(published_at) FROM core.news_resources").fetchone()[0]

        con.execute(f"""
            INSERT OR IGNORE INTO core.news_resources
            SELECT * FROM news_db.core.news_resources
            WHERE published_at >= '{since_date}'
        """)

        cnt_res_after = con.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
        max_res_after = con.execute("SELECT max(published_at) FROM core.news_resources").fetchone()[0]
        res_added = cnt_res_after - cnt_res_before
        stats["core.news_resources"] = {
            "before": cnt_res_before,
            "after": cnt_res_after,
            "added": res_added,
            "max_published": str(max_res_after),
        }
        logger.info(
            "[core.news_resources] +%d bản ghi mới (Tổng: %d, Max: %s)",
            res_added, cnt_res_after, max_res_after
        )

        # 4. Mirror sang core.macro_policy (Duy trì tính tương thích ngược cho pipeline vĩ mô)
        cnt_macro_before = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
        con.execute(f"""
            INSERT OR IGNORE INTO core.macro_policy (
                source, issuing_body, doc_type, doc_number, published_at,
                available_at, headline, summary, body, source_url, fetched_at
            )
            SELECT 
                source, issuing_body, doc_type, doc_number, published_at,
                available_at, headline, summary, body, source_url, fetched_at
            FROM news_db.core.news_resources
            WHERE published_at >= '{since_date}'
        """)
        cnt_macro_after = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
        macro_added = cnt_macro_after - cnt_macro_before
        stats["core.macro_policy"] = {
            "before": cnt_macro_before,
            "after": cnt_macro_after,
            "added": macro_added,
        }
        logger.info(
            "[core.macro_policy] +%d bản ghi mới (Tổng: %d)",
            macro_added, cnt_macro_after
        )

    finally:
        con.close()

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đồng bộ vesta_news.duckdb sang vesta_snapshot.duckdb")
    parser.add_argument("--since", default="2026-09-01", help="Mốc ngày bắt đầu đồng bộ (YYYY-MM-DD)")
    args = parser.parse_args()

    sync_news_data(since_date=args.since)
