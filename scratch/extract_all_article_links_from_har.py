"""scratch/extract_all_article_links_from_har.py
Trích xuất tất cả các link bài viết CafeF (.chn) xuất hiện trong 23 file HAR.
"""
import sys
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

HAR_DIR = Path("scratch/har/cafef")
har_files = sorted(list(HAR_DIR.glob("*.har")))

all_article_links = set()
article_metadata = []

for h in har_files:
    try:
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        continue
    
    entries = data.get("log", {}).get("entries", [])
    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        text = resp.get("content", {}).get("text", "")
        
        # 1. Từ response của News.ashx
        if "News.ashx" in url and text:
            try:
                j = json.loads(text)
                for item in j.get("Data", []):
                    link = item.get("LinkDetail")
                    title = item.get("Title")
                    date_val = item.get("DeployDate")
                    if link and link not in all_article_links:
                        all_article_links.add(link)
                        article_metadata.append({"title": title, "link": link, "source": "News.ashx", "har": h.name})
            except Exception:
                pass
                
        # 2. Từ HTML của các trang chuyên mục trong response
        if text and ("text/html" in resp.get("content", {}).get("mimeType", "") or ".chn" in url):
            # Tìm tất cả href có đuôi -\d+.chn
            matches = re.findall(r'href=["\'](/[^"\']*-\d+\.chn(?:\?[^"\']*)?)["\']', text)
            for m in matches:
                clean_link = m.split("?")[0]
                if clean_link not in all_article_links and not clean_link.startswith("/du-lieu"):
                    all_article_links.add(clean_link)
                    article_metadata.append({"title": "", "link": clean_link, "source": "HTML link", "har": h.name})

print("=" * 80)
print(f"TỔNG SỐ ĐƯỜNG LINK BÀI BÁO CHI TIẾT TRÍCH XUẤT ĐƯỢC TỪ CÁC FILE HAR: {len(all_article_links):,}")
print("MẪU 10 LINK ĐẦU TIÊN:")
for item in article_metadata[:10]:
    print(f"  • {item['link']} ({item['har']}) - {item['title'][:60]}")
