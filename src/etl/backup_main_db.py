"""src/etl/backup_main_db.py

Hạ tầng sao lưu & khôi phục dữ liệu tự động cho CSDL VESTA (F000).
- Duy trì đúng 1 CSDL chính (db/vesta.duckdb) làm nguồn sự thật duy nhất (Single Source of Truth).
- Tự động tạo bản sao lưu dự phòng (db/vesta_backup.duckdb) mà không gây khóa tiến trình (Zero-lock).
- Cung cấp cơ chế khôi phục khẩn cấp (Disaster Recovery) khi CSDL chính gặp sự cố hỏng hóc hoặc xung đột PID.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import shutil
import sys
import time
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backup_main_db")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_DB_PATH = PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"
BACKUP_DB_PATH = PROJECT_ROOT / "db" / "vesta_backup.duckdb"
ARCHIVE_BACKUP_DIR = PROJECT_ROOT / "db" / "backups"

CORE_TABLES_TO_VERIFY = [
    "core.market_ohlcv_daily",
    "core.market_ohlcv_1m",
    "core.news",
    "core.fundamentals",
    "core.corporate_events",
    "core.market_foreign_flow_daily",
    "core.macro_policy",
    "core.financial_notes",
    "core.proprietary_flow",
    "core.price_adjustment_events",
    "core.macro_rates",
    "core.dim_symbol",
    "core.cafef_disclosures",
    "core.company_overview",
    "core.company_shareholders",
    "core.news_resources",
    "core.macro_economic_series",
]


def backup_database(
    src_path: pathlib.Path = MAIN_DB_PATH,
    dst_path: pathlib.Path = BACKUP_DB_PATH,
    rotate_archive: bool = False,
) -> Dict[str, Any]:
    """Sao lưu CSDL an toàn từ src_path sang dst_path."""
    if not src_path.exists():
        raise FileNotFoundError(f"CSDL nguồn không tồn tại: {src_path}")

    start_time = time.perf_counter()
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    src_size_mb = src_path.stat().st_size / (1024 * 1024)
    logger.info(f"Bắt đầu sao lưu CSDL chính: {src_path.name} ({src_size_mb:.2f} MB) -> {dst_path.name}")

    # Kiểm tra tính toàn vẹn của CSDL nguồn trước khi copy
    con_src = duckdb.connect(str(src_path), read_only=True)
    table_counts_src: Dict[str, int] = {}
    try:
        for tbl in CORE_TABLES_TO_VERIFY:
            try:
                cnt = con_src.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                table_counts_src[tbl] = cnt
            except Exception:
                table_counts_src[tbl] = 0
    finally:
        con_src.close()

    # Thực hiện sao lưu an toàn qua file copy
    temp_dst = dst_path.with_suffix(".tmp")
    try:
        shutil.copyfile(str(src_path), str(temp_dst))
        if dst_path.exists():
            dst_path.unlink()
        temp_dst.rename(dst_path)
    except Exception as e:
        if temp_dst.exists():
            temp_dst.unlink()
        raise RuntimeError(f"Lỗi khi copy file CSDL: {e}")

    # Lưu thêm 1 bản archive có timestamp nếu được yêu cầu
    if rotate_archive:
        timestamp_str = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = ARCHIVE_BACKUP_DIR / f"vesta_backup_{timestamp_str}.duckdb"
        shutil.copyfile(str(dst_path), str(archive_file))
        logger.info(f"Đã lưu bản sao lưu lưu trữ: {archive_file.name}")

    # Xác thực tính toàn vẹn của CSDL đích
    con_dst = duckdb.connect(str(dst_path), read_only=True)
    table_counts_dst: Dict[str, int] = {}
    mismatches: List[str] = []
    try:
        for tbl in CORE_TABLES_TO_VERIFY:
            try:
                cnt = con_dst.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                table_counts_dst[tbl] = cnt
                if cnt != table_counts_src.get(tbl, 0):
                    mismatches.append(f"{tbl}: src={table_counts_src.get(tbl, 0)} vs dst={cnt}")
            except Exception as e:
                mismatches.append(f"{tbl}: {e}")
    finally:
        con_dst.close()

    elapsed = time.perf_counter() - start_time
    if mismatches:
        raise ValueError(f"Dữ liệu bản sao lưu không khớp với CSDL nguồn: {mismatches}")

    logger.info(f"Sao lưu CSDL hoàn tất thành công trong {elapsed:.2f}s! ({len(table_counts_dst)} bảng xác thực khớp 100%)")
    return {
        "status": "SUCCESS",
        "elapsed_sec": round(elapsed, 2),
        "source": str(src_path),
        "destination": str(dst_path),
        "source_size_mb": round(src_size_mb, 2),
        "tables_verified": table_counts_dst,
    }


def restore_database(
    backup_path: pathlib.Path = BACKUP_DB_PATH,
    target_path: pathlib.Path = MAIN_DB_PATH,
) -> bool:
    """Khôi phục CSDL chính từ bản sao lưu khi gặp sự cố."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Không tìm thấy bản sao lưu: {backup_path}")

    logger.warning(f"CẢNH BÁO: Bắt đầu khôi phục CSDL chính từ bản sao lưu: {backup_path.name} -> {target_path.name}")
    con_test = duckdb.connect(str(backup_path), read_only=True)
    con_test.close()

    temp_target = target_path.with_suffix(".restoring")
    shutil.copyfile(str(backup_path), str(temp_target))

    if target_path.exists():
        corrupted_name = target_path.with_suffix(f".corrupted_{int(time.time())}")
        target_path.rename(corrupted_name)
        logger.info(f"Đã đổi tên CSDL hỏng thành: {corrupted_name.name}")

    temp_target.rename(target_path)
    logger.info(f"Khôi phục CSDL chính thành công từ bản sao lưu: {target_path.name}")
    return True


def check_status() -> None:
    """Kiểm tra tình trạng sức khỏe của CSDL chính và bản sao lưu."""
    print("=" * 80)
    print("                 VESTA DATABASE STATUS & HEALTH CHECK")
    print("=" * 80)

    for name, path in [("MAIN DATABASE", MAIN_DB_PATH), ("BACKUP DATABASE", BACKUP_DB_PATH)]:
        print(f"\n[{name}] {path.name}:")
        if not path.exists():
            print("  Trạng thái: CHƯA TỒN TẠI")
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  Dung lượng : {size_mb:.2f} MB")
        try:
            con = duckdb.connect(str(path), read_only=True)
            print("  Khóa file  : MỞ THÀNH CÔNG (Unlocked)")
            print("  Dữ liệu cốt lõi:")
            for tbl in CORE_TABLES_TO_VERIFY:
                try:
                    cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                    print(f"    - {tbl:<32}: {cnt:>10,}")
                except Exception:
                    pass
            con.close()
        except Exception as e:
            print(f"  Khóa file  : ĐANG BỊ KHÓA HOẶC LỖI ({e})")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VESTA Single Main Database Backup & Recovery Utility")
    parser.add_argument("--backup", action="store_true", help="Thực hiện sao lưu từ main DB sang backup DB")
    parser.add_argument("--restore", action="store_true", help="Khôi phục main DB từ backup DB khi gặp sự cố")
    parser.add_argument("--archive", action="store_true", help="Lưu thêm bản backup có timestamp vào db/backups/")
    parser.add_argument("--check", action="store_true", help="Kiểm tra trạng thái sức khỏe CSDL")

    args = parser.parse_args()

    if args.restore:
        restore_database()
    elif args.backup:
        backup_database(rotate_archive=args.archive)
    else:
        check_status()
