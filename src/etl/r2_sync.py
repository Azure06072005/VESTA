"""
VESTA Cloudflare R2 Storage Sync Utility
========================================
Quản lý đồng bộ và lưu trữ CSDL VESTA (Hot Tier & Cold Lakehouse) lên Cloudflare R2.

Tính năng:
- Upload gói CSDL nóng (db/hot/vesta_hot_tier.zip hoặc từng file .duckdb) lên Cloudflare R2.
- Download CSDL nóng từ Cloudflare R2 về server / máy cục bộ.
- Tự động tận dụng cấu hình wrangler đã đăng nhập OAuth (`npx wrangler`).
- Hỗ trợ cả bucket `vesta-data` lẫn `my-bucket`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
HOT_DIR = REPO_ROOT / "db" / "hot"
DEFAULT_BUCKET = "vesta-data"


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_wrangler_cmd(args: list[str]) -> bool:
    """Chạy lệnh npx wrangler với kiểm tra lỗi rõ ràng."""
    cmd = ["npx", "wrangler"] + args
    cmd_str = " ".join(cmd)
    log(f"Thực thi: {cmd_str}")
    try:
        res = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            shell=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if res.stdout:
            for line in res.stdout.strip().splitlines():
                print(f"  {line}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi lệnh ({e.returncode}):")
        if e.stderr:
            print(f"  {e.stderr.strip()}")
        if e.stdout:
            print(f"  {e.stdout.strip()}")
        return False


def upload_hot_package(bucket: str = DEFAULT_BUCKET, file_name: str = "vesta_hot_tier.zip") -> bool:
    """Tải gói nén CSDL nóng lên Cloudflare R2."""
    local_file = HOT_DIR / file_name
    if not local_file.exists():
        log(f"❌ Không tìm thấy file {local_file}. Hãy chạy `python src/etl/build_hot_web_db.py` trước.")
        return False

    size_mb = local_file.stat().st_size / (1024 * 1024)
    log(f"🚀 Bắt đầu upload {file_name} ({size_mb:.1f} MB) lên Cloudflare R2 bucket '{bucket}'...")
    
    # npx wrangler r2 object put {bucket}/{key} --file {local_path} --remote
    success = run_wrangler_cmd([
        "r2", "object", "put", f"{bucket}/{file_name}",
        "--file", str(local_file),
        "--remote"
    ])
    if success:
        log(f"✅ Đã tải thành công {file_name} lên R2: {bucket}/{file_name}")
    return success


def download_hot_package(bucket: str = DEFAULT_BUCKET, file_name: str = "vesta_hot_tier.zip", target_dir: Path = HOT_DIR) -> bool:
    """Tải gói CSDL nóng từ Cloudflare R2 về thư mục đích."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / file_name
    log(f"⬇️  Bắt đầu download {file_name} từ Cloudflare R2 bucket '{bucket}' về {out_file}...")

    # npx wrangler r2 object get {bucket}/{key} --file {out_path} --remote
    success = run_wrangler_cmd([
        "r2", "object", "get", f"{bucket}/{file_name}",
        "--file", str(out_file),
        "--remote"
    ])
    if success and out_file.exists():
        size_mb = out_file.stat().st_size / (1024 * 1024)
        log(f"✅ Đã tải thành công {file_name} ({size_mb:.1f} MB) về máy.")
    return success


def list_r2_buckets():
    """Liệt kê danh sách bucket R2."""
    run_wrangler_cmd(["r2", "bucket", "list"])


def main():
    parser = argparse.ArgumentParser(description="VESTA Cloudflare R2 Storage Tool")
    parser.add_argument("--upload", action="store_true", help="Upload vesta_hot_tier.zip lên Cloudflare R2")
    parser.add_argument("--download", action="store_true", help="Download vesta_hot_tier.zip từ Cloudflare R2")
    parser.add_argument("--list", action="store_true", help="Xem danh sách R2 buckets")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help=f"Tên bucket R2 (mặc định: {DEFAULT_BUCKET})")
    parser.add_argument("--file", default="vesta_hot_tier.zip", help="Tên file đồng bộ (mặc định: vesta_hot_tier.zip)")

    args = parser.parse_args()

    if args.list:
        list_r2_buckets()
    elif args.upload:
        upload_hot_package(bucket=args.bucket, file_name=args.file)
    elif args.download:
        download_hot_package(bucket=args.bucket, file_name=args.file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
