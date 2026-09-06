"""Helper đồng bộ dữ liệu cào từ crawlers_staging.duckdb vào vesta.duckdb chính."""

from __future__ import annotations

import logging
from pathlib import Path
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MAIN_DB_PATH = Path("d:/VESTA/db/vesta.duckdb")
STAGING_DB_PATH = Path("d:/VESTA/db/crawlers_staging.duckdb")


def merge_staging_to_main() -> int:
    """Nạp toàn bộ bản ghi từ crawlers_staging.duckdb vào vesta.duckdb."""
    if not STAGING_DB_PATH.exists():
        logger.info("Không tìm thấy crawlers_staging.duckdb.")
        return 0

    try:
        main_conn = duckdb.connect(str(MAIN_DB_PATH), read_only=False)
    except Exception as e:
        logger.error(f"Không thể mở vesta.duckdb ở chế độ ghi ({e}). Vui lòng ngắt kết nối trình xem DB trước.")
        return 0

    try:
        main_conn.execute(f"ATTACH '{STAGING_DB_PATH}' AS staging_db (READ_ONLY);")

        # Merge vào core.macro_policy
        result = main_conn.execute("""
            INSERT INTO core.macro_policy (
                source, issuing_body, doc_type, doc_number,
                published_at, available_at, headline, summary,
                body, source_url, fetched_at
            )
            SELECT
                source, issuing_body, doc_type, doc_number,
                published_at, available_at, headline, summary,
                body, source_url, fetched_at
            FROM staging_db.core.macro_policy
            ON CONFLICT (source_url) DO UPDATE SET
                headline = EXCLUDED.headline,
                summary = EXCLUDED.summary,
                body = EXCLUDED.body,
                doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                fetched_at = EXCLUDED.fetched_at
        """)

        # Đếm số bản ghi đã nạp
        count_staging = main_conn.execute("SELECT count(*) FROM staging_db.core.macro_policy").fetchone()[0]
        main_conn.execute("DETACH staging_db;")
        main_conn.close()

        logger.info(f"Đã đồng bộ thành công {count_staging} bản ghi từ staging vào vesta.duckdb!")
        return count_staging
    except Exception as e:
        logger.error(f"Lỗi trong quá trình đồng bộ: {e}")
        return 0


if __name__ == "__main__":
    merge_staging_to_main()
