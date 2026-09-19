"""src/etl/merge_news_staging.py

Công cụ đồng bộ và hợp nhất dữ liệu tin tức từ cơ sở dữ liệu tạm thời
(d:/VESTA/db/vesta_news_staging.duckdb) vào cơ sở dữ liệu chính (d:/VESTA/db/vesta_snapshot.duckdb).
Bảo đảm tính toàn vẹn, không ghi đè, và chống xung đột khóa (ON CONFLICT DO NOTHING).
"""

import argparse
import logging
import sys
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("merge_news_staging")


from src.crawlers.db_writer import ResilientDuckDBWriter


def merge_staging_to_snapshot(
    staging_db: str = "d:/VESTA/db/vesta_news_staging.duckdb",
    target_db: str = "d:/VESTA/db/vesta_snapshot.duckdb",
) -> int:
    """Hợp nhất các bảng tin tức từ database tạm sang database chính với cơ chế chống khóa."""
    logger.info("=== BẮT ĐẦU HỢP NHẤT DỮ LIỆU TIN TỨC ===")
    logger.info("Nguồn tạm (Source): %s", staging_db)
    logger.info("Đích đến (Target) : %s", target_db)

    writer = ResilientDuckDBWriter(target_db=target_db)

    def _do_merge(con: duckdb.DuckDBPyConnection) -> int:
        con.execute(f"ATTACH '{staging_db}' AS staging (READ_ONLY)")
        total = 0
        try:
            res = con.execute("""
                INSERT INTO core.news_resources
                SELECT * FROM staging.core.news_resources
                ON CONFLICT (source_url) DO NOTHING
                RETURNING source_url
            """).fetchall()
            total = len(res)
            logger.info("-> [core.news_resources]: Đã hợp nhất +%d bài viết mới.", total)
        except Exception as e:
            logger.warning("Lỗi hợp nhất core.news_resources: %s", e)

        try:
            con.execute("""
                INSERT INTO core.macro_policy
                SELECT * FROM staging.core.macro_policy
                ON CONFLICT (source_url) DO NOTHING
            """)
        except Exception:
            pass

        con.execute("DETACH staging")
        return total

    try:
        merged = writer.execute_with_retry(_do_merge)
        logger.info("=== HOÀN TẤT: Tổng cộng +%d bài viết đã được đưa vào kho chính ===", merged)
        return merged
    except Exception as e:
        logger.warning("Database chính vẫn đang bận. Các bài viết đã được bảo vệ tại %s và sẽ hợp nhất sau: %s", staging_db, e)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge News Staging DB into Snapshot DB")
    parser.add_argument("--source", default="d:/VESTA/db/vesta_news_staging.duckdb", help="Staging DB path")
    parser.add_argument("--target", default="d:/VESTA/db/vesta_snapshot.duckdb", help="Target DB path")
    args = parser.parse_args()

    merge_staging_to_snapshot(staging_db=args.source, target_db=args.target)


if __name__ == "__main__":
    main()
