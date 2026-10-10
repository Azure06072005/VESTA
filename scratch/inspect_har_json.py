import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

hars = [
    "scratch/har/vietstock/du_lieu_nganh.har",
    "scratch/har/vietstock/trang_chu.har",
    "scratch/har/vietstock/tong_quan.har"
]

for har_path in hars:
    print(f"\n==================== JSON/POST in {har_path} ====================")
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har_data = json.load(f)
    entries = har_data.get("log", {}).get("entries", [])
    for e in entries:
        req = e.get("request", {})
        res = e.get("response", {})
        url = req.get("url", "")
        mime = res.get("content", {}).get("mimeType", "")
        text = res.get("content", {}).get("text", "")
        if "application/json" in mime or "json" in url.lower() or req.get("method") == "POST":
            preview = text[:150] if text else "EMPTY"
            print(f"[{req.get('method')}] {url}")
            print(f"  Response: {preview}\n")
