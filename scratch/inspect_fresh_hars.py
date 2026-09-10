import pathlib
import datetime
import json
import os

today = datetime.date(2026, 9, 9)
har_files = []
for p in pathlib.Path("scratch/har").rglob("*.har"):
    mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
    if mtime.date() == today or "gdt" in str(p) or "mof" in str(p):
        har_files.append((mtime, p.stat().st_size / (1024*1024), p))

har_files.sort(key=lambda x: x[0], reverse=True)

print(f"Total fresh / today HAR files: {len(har_files)}")
print(f"{'Modified Time':<20} | {'Size':<10} | {'Path'}")
print("-" * 80)
for mtime, sz, p in har_files:
    print(f"{mtime.strftime('%Y-%m-%d %H:%M:%S'):<20} | {sz:6.2f} MB  | {p}")
