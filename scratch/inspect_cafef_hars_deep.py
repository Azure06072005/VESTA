"""scratch/inspect_cafef_hars_deep.py

Deep inspection of all 21 .har files in d:/VESTA/scratch/har/cafef
Extracts:
1. Endpoints, methods, and URL patterns
2. Query parameters for pagination and date filtering
3. Headers, user-agent, and response formats (JSON vs HTML)
"""
import os
import sys
import json
from collections import Counter
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8")

HAR_DIR = "scratch/har/cafef"
har_files = [f for f in os.listdir(HAR_DIR) if f.endswith(".har")]
print("=" * 85)
print(f"DEEP INSPECTION OF {len(har_files)} CAFEF .HAR FILES IN {HAR_DIR}")
print("=" * 85)

endpoints_summary = []

for hf in sorted(har_files):
    fpath = os.path.join(HAR_DIR, hf)
    fsize_mb = os.path.getsize(fpath) / (1024 * 1024)
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
            entries = data.get("log", {}).get("entries", [])
            
            # Group URLs
            urls = []
            api_calls = []
            for entry in entries:
                req = entry.get("request", {})
                url = req.get("url", "")
                parsed = urlparse(url)
                urls.append(parsed.netloc)
                
                # Check for XHR / API calls
                res = entry.get("response", {})
                mime = res.get("content", {}).get("mimeType", "")
                if any(ext in parsed.path for ext in [".ashx", ".aspx", "ajax", "api", "get", "list", "json"]) or "json" in mime or "javascript" in mime:
                    api_calls.append({
                        "url": url,
                        "path": parsed.path,
                        "query": parse_qs(parsed.query),
                        "mime": mime,
                        "status": res.get("status")
                    })
                    
            endpoints_summary.append({
                "file": hf,
                "size_mb": round(fsize_mb, 1),
                "total_entries": len(entries),
                "domains": Counter(urls).most_common(3),
                "api_calls_count": len(api_calls),
                "sample_apis": api_calls[:4]
            })
    except Exception as e:
        endpoints_summary.append({
            "file": hf,
            "size_mb": round(fsize_mb, 1),
            "error": str(e)
        })

for item in endpoints_summary:
    print(f"\n--- [{item['file']}] ({item['size_mb']} MB, {item.get('total_entries', 0)} requests) ---")
    if "error" in item:
        print(f"  Error: {item['error']}")
        continue
    print("  Top domains:", ", ".join(f"{d} ({c})" for d, c in item["domains"]))
    print(f"  API/XHR calls found: {item['api_calls_count']}")
    for api in item.get("sample_apis", []):
        print(f"    -> Status {api['status']} | {api['path']} | Query: {list(api['query'].keys())}")
