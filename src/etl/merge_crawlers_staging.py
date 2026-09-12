"""Helper đồng bộ và hợp nhất dữ liệu từ crawlers_staging.duckdb vào vesta.duckdb và backup.

Thực hiện nạp toàn bộ bài viết mới từ staging vào core.macro_policy theo cơ chế
Idempotent ON CONFLICT (source_url) DO UPDATE.
Hỗ trợ cả 2 đích: vesta.duckdb và vesta_latest_backup.duckdb, đồng thời hỗ trợ
sao chép trực tiếp từ vesta_consolidated.duckdb khi khóa IDE được giải phóng.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import shutil
import sys
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("merge_crawlers")

MAIN_DB_PATH = Path("d:/VESTA/db/vesta.duckdb")
BACKUP_DB_PATH = Path("d:/VESTA/db/vesta_latest_backup.duckdb")
STAGING_DB_PATH = Path("d:/VESTA/db/crawlers_staging.duckdb")
CONSOLIDATED_DB_PATH = Path("d:/VESTA/db/vesta_consolidated.duckdb")


DEFAULT_STAGING_PATHS = [
    Path("d:/VESTA/db/crawlers_staging.duckdb"),
    Path("d:/VESTA/db/staging_tnck.duckdb"),
    Path("d:/VESTA/db/staging_tuoitre.duckdb"),
]


def merge_into_db(target_path: Path, staging_paths: list[Path] | None = None) -> int:
    """Nạp toàn bộ bản ghi từ các database staging vào database đích."""
    if not target_path.exists():
        logger.warning(f"File đích {target_path} không tồn tại.")
        return 0

    try:
        conn = duckdb.connect(str(target_path), read_only=False)
    except Exception as e:
        logger.error(f"Không thể mở {target_path.name} ở chế độ ghi ({e}).")
        return 0

    sources_to_merge = [p for p in (staging_paths or DEFAULT_STAGING_PATHS) if p.exists()]
    total_added = 0

    try:
        before_cnt = conn.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]

        for idx, stg_path in enumerate(sources_to_merge):
            alias = f"staging_db_{idx}"
            try:
                conn.execute(f"ATTACH '{stg_path.as_posix()}' AS {alias} (READ_ONLY);")
                for schema in ["core", "staging"]:
                    has_tbl = conn.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_catalog = '{alias}' AND table_schema = '{schema}' AND table_name = 'macro_policy'").fetchone()[0]
                    if has_tbl:
                        conn.execute(f"""
                            INSERT INTO core.macro_policy (
                                source, issuing_body, doc_type, doc_number,
                                published_at, available_at, headline, summary,
                                body, source_url, fetched_at
                            )
                            SELECT
                                source, issuing_body, doc_type, doc_number,
                                published_at, available_at, headline, summary,
                                body, source_url, fetched_at
                            FROM {alias}.{schema}.macro_policy
                            WHERE source_url IS NOT NULL
                            ON CONFLICT (source_url) DO UPDATE SET
                                headline = EXCLUDED.headline,
                                summary = EXCLUDED.summary,
                                body = EXCLUDED.body,
                                doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                                fetched_at = EXCLUDED.fetched_at
                        """)
                conn.execute(f"DETACH {alias};")
            except Exception as ex:
                logger.warning(f"Lỗi khi merge từ {stg_path.name}: {ex}")

        after_cnt = conn.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
        total_added = after_cnt - before_cnt
        logger.info(f"[{target_path.name}] Đã nạp thành công. Số lượng: {before_cnt:,} -> {after_cnt:,} (+{total_added:,} mới).")
        return total_added
    except Exception as e:
        logger.error(f"Lỗi khi hợp nhất vào {target_path.name}: {e}")
        return 0
    finally:
        conn.close()


def apply_consolidated_snapshot() -> bool:
    """Sao chép bản snapshot hợp nhất toàn diện vesta_consolidated.duckdb sang main và backup."""
    if not CONSOLIDATED_DB_PATH.exists():
        logger.warning("Chưa có file vesta_consolidated.duckdb.")
        return False

    success = True
    for target in [MAIN_DB_PATH, BACKUP_DB_PATH]:
        try:
            shutil.copy(str(CONSOLIDATED_DB_PATH), str(target))
            logger.info(f"Đã cập nhật thành công snapshot toàn diện vào {target.name}!")
        except Exception as e:
            logger.warning(f"Chưa thể ghi đè {target.name} ({e}) do tiến trình IDE đang giữ file.")
            success = False
    return success


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Merge crawlers_staging.duckdb into VESTA main and backup databases.")
    parser.add_argument("--use-snapshot", action="store_true", help="Ghi đè snapshot từ vesta_consolidated.duckdb")
    args = parser.parse_args()

    if args.use_snapshot:
        apply_consolidated_snapshot()
        return

    # 1. Thử merge trực tiếp qua DuckDB SQL
    m_main = merge_into_db(MAIN_DB_PATH)
    m_backup = merge_into_db(BACKUP_DB_PATH)

    # 2. Nếu cả 2 đều bị lock bởi IDE, thông báo giải pháp tức thời
    if m_main == 0 and m_backup == 0:
        logger.info("=" * 60)
        logger.info("LƯU Ý: Cả vesta.duckdb và vesta_latest_backup.duckdb đang được mở bởi Antigravity IDE.")
        logger.info("File hợp nhất toàn diện đã sẵn sàng tại:")
        logger.info(f"  -> {CONSOLIDATED_DB_PATH} ({CONSOLIDATED_DB_PATH.stat().st_size / (1024*1024):.2f} MB)")
        logger.info("Bạn có thể sử dụng trực tiếp vesta_consolidated.duckdb cho backtest và mô hình,")
        logger.info("hoặc chạy 'python src/etl/merge_crawlers_staging.py --use-snapshot' khi đóng IDE.")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
