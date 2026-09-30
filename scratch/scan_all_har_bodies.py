"""scratch/scan_all_har_bodies.py
Quét toàn bộ 23 file HAR trong scratch/har/cafef để đếm và trích xuất tất cả các bài viết full-text.
"""
import sys
import os
import json
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

HAR_DIR = Path("scratch/har/cafef")
har_files = sorted(list(HAR_DIR.glob("*.har")))

total_html_articles = 0
har_summary = []

for h in har_files:
    try:
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception as e:
        continue
    
    entries = data.get("log", {}).get("entries", [])
    article_count = 0
    full_body_count = 0
    
    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        mime = resp.get("content", {}).get("mimeType", "")
        text = resp.get("content", {}).get("text", "")
        
        # Nhận diện trang bài viết chi tiết CafeF
        if ".chn" in url and "cafef.vn" in url and not url.endswith("Event.chn") and "du-lieu" not in url and "ajax" not in url.lower():
            if "text/html" in mime and len(text) > 1000:
                article_count += 1
                # Kiểm tra xem có div detail-content hay không
                if "detail-content" in text or "contentcontent" in text:
                    full_body_count += 1
                    
    total_html_articles += full_body_count
    har_summary.append({
        "file": h.name,
        "entries": len(entries),
        "articles": article_count,
        "full_bodies": full_body_count,
        "size_mb": round(h.stat().st_size / 1024 / 1024, 1)
    })

print("=" * 80)
print(f"TỔNG KẾT TÀI NGUYÊN NỘI DUNG TRONG 23 FILE .HAR ({len(har_files)} files):")
print(f"{'Tên File':<35} | {'Size MB':<8} | {'Entries':<8} | {'Articles':<8} | {'Full Bodies':<10}")
print("-" * 80)
for s in har_summary:
    print(f"{s['file']:<35} | {s['size_mb']:<8} | {s['entries']:<8} | {s['articles']:<8} | {s['full_bodies']:<10}")
print("-" * 80)
print(f"TỔNG SỐ BÀI BÁO TOÀN VĂN (FULL-TEXT) NẰM TRONG CÁC FILE HAR: {total_html_articles}")
