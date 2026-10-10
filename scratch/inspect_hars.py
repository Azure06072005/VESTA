import json
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

hars = [
    "scratch/har/vietstock/du_lieu_nganh.har",
    "scratch/har/vietstock/trang_chu.har",
    "scratch/har/vietstock/tong_quan.har"
]

for har_path in hars:
    if not os.path.exists(har_path):
        print(f"File not found: {har_path}")
        continue
    print(f"\n==================== {har_path} ====================")
    try:
        with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
            har_data = json.load(f)
        entries = har_data.get("log", {}).get("entries", [])
        print(f"Total network entries: {len(entries)}")
        
        # Look for API requests (xhr/fetch, json, post/get with interesting URLs)
        api_urls = []
        for e in entries:
            req = e.get("request", {})
            res = e.get("response", {})
            url = req.get("url", "")
            mime = res.get("content", {}).get("mimeType", "")
            size = res.get("content", {}).get("size", 0)
            if any(k in url.lower() for k in ["api", "data", "ajax", "json", "get", "du-lieu", "sector", "index", "market", "stock"]):
                if not any(ext in url.lower() for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".gif"]):
                    api_urls.append((req.get("method"), url, mime, size))
        
        print(f"Found {len(api_urls)} relevant endpoints:")
        for m, u, mime, sz in api_urls[:20]:
            print(f"  [{m}] {u} ({mime}, {sz} bytes)")
    except Exception as ex:
        print(f"Error parsing {har_path}: {ex}")
