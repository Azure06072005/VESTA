"""scratch/inspect_thong_tin_bctc_har.py

Inspects newly added cafef_du-lieu_thong-tin-bctc.har
"""
import os
import sys
import json
from collections import Counter
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8")

har_path = "scratch/har/cafef/cafef_du-lieu_thong-tin-bctc.har"
print(f"Inspecting {har_path} (Size: {os.path.getsize(har_path):,} bytes)...")

with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
    data = json.load(f)

entries = data.get("log", {}).get("entries", [])
print(f"Total HTTP requests in HAR: {len(entries)}")

api_entries = []
domains = []

for idx, e in enumerate(entries):
    req = e.get("request", {})
    res = e.get("response", {})
    url = req.get("url", "")
    method = req.get("method", "")
    status = res.get("status", 0)
    mime = res.get("content", {}).get("mimeType", "")
    parsed = urlparse(url)
    domains.append(parsed.netloc)
    
    # Filter for data / api / ajax / bctc calls
    if any(k in url.lower() for k in ["bctc", "thong-tin", "ajax", "api", "ashx", "get"]):
        text = res.get("content", {}).get("text", "")
        api_entries.append({
            "idx": idx,
            "method": method,
            "url": url,
            "path": parsed.path,
            "query": parse_qs(parsed.query),
            "status": status,
            "mime": mime,
            "content_len": len(text),
            "sample_content": text[:350]
        })

print("\nTop Domains:")
for d, c in Counter(domains).most_common(5):
    print(f" - {d:<35} : {c} requests")

print(f"\nFound {len(api_entries)} relevant API/data requests:")
for item in api_entries:
    print(f"\n[{item['idx']}] {item['method']} {item['status']} | {item['url']}")
    print(f" Query params : {item['query']}")
    print(f" MimeType     : {item['mime']} | Length: {item['content_len']}")
    if item['sample_content']:
        print(f" Sample Body  : {item['sample_content'][:200]}...")
