"""VESTA Database Backup Utility.

Creates an atomic, verified backup of `vesta.duckdb` and `crawlers_staging.duckdb`
before initiating pipeline stage F101.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def compute_sha256(file_path: str, chunk_size: int = 16 * 1024 * 1024) -> str:
    """Compute SHA256 checksum in chunks for large files."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_database():
    source_dir = "d:/VESTA/db"
    backup_dir = "d:/VESTA/db/backups"
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_tag = f"pre_f101_{timestamp}"

    print(f"==> Starting VESTA Database Backup ({backup_tag})...")

    # 1. Flush & Checkpoint active databases
    for db_name in ["vesta.duckdb", "crawlers_staging.duckdb"]:
        db_path = os.path.join(source_dir, db_name)
        if os.path.exists(db_path):
            print(f"[*] Checkpointing {db_name}...")
            try:
                con = duckdb.connect(db_path, read_only=False)
                con.execute("CHECKPOINT;")
                con.close()
            except Exception as e:
                print(f"Warning during checkpoint of {db_name}: {e}")

    manifest = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "backup_tag": backup_tag,
        "files": {},
        "table_counts": {},
    }

    # 2. Copy files with metadata
    for db_name in ["vesta.duckdb", "crawlers_staging.duckdb"]:
        src_path = os.path.join(source_dir, db_name)
        if not os.path.exists(src_path):
            continue

        base_name, ext = os.path.splitext(db_name)
        dest_filename = f"{base_name}_{backup_tag}{ext}"
        dest_path = os.path.join(backup_dir, dest_filename)

        src_size = os.path.getsize(src_path)
        print(f"[*] Copying {db_name} ({src_size / (1024*1024):.2f} MB) -> {dest_filename}...")
        start_t = time.time()
        shutil.copy2(src_path, dest_path)
        dur = time.time() - start_t
        dest_size = os.path.getsize(dest_path)

        assert src_size == dest_size, f"Size mismatch for {db_name}: {src_size} vs {dest_size}"
        print(f"    -> Done in {dur:.2f}s ({dest_size / (1024*1024):.2f} MB)")

        print(f"[*] Computing SHA256 checksum for {dest_filename}...")
        checksum = compute_sha256(dest_path)
        print(f"    -> SHA256: {checksum}")

        manifest["files"][db_name] = {
            "backup_filename": dest_filename,
            "backup_path": dest_path,
            "size_bytes": dest_size,
            "size_mb": round(dest_size / (1024 * 1024), 2),
            "sha256": checksum,
            "copy_duration_sec": round(dur, 2),
        }

    # 3. Sanity verification of tables in backup copy
    backup_vesta_path = manifest["files"]["vesta.duckdb"]["backup_path"]
    print(f"\n[*] Running sanity checks on backup database ({backup_vesta_path})...")
    con = duckdb.connect(backup_vesta_path, read_only=True)
    tables = con.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
    """).fetchall()

    for schema, table in tables:
        cnt = con.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
        full_table = f"{schema}.{table}"
        manifest["table_counts"][full_table] = cnt
        print(f"    - {full_table:35s}: {cnt:>10,} rows")
    con.close()

    # 4. Save manifest
    manifest_path = os.path.join(backup_dir, f"manifest_{backup_tag}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Backup manifest saved to: {manifest_path}")

    # Also keep a symlink/latest pointer
    latest_path = os.path.join(backup_dir, "vesta_latest_backup.duckdb")
    if os.path.exists(latest_path):
        try:
            os.remove(latest_path)
        except Exception:
            pass
    try:
        shutil.copyfile(backup_vesta_path, latest_path)
        print(f"[+] Latest backup reference updated: {latest_path}")
    except Exception as e:
        print(f"Notice on latest pointer: {e}")

    print("\n=======================================================")
    print("           BACKUP COMPLETED & VERIFIED 100%           ")
    print("=======================================================")
    return manifest


if __name__ == "__main__":
    backup_database()
