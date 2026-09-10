import json
from pathlib import Path

har_path = Path("scratch/har/gdt/tin-tuc.har")
with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
    data = json.load(f)

entries = data.get("log", {}).get("entries", [])
print(f"File: {har_path} | Total entries: {len(entries)}")

urls = []
api_calls = []
for entry in entries:
    req = entry.get("request", {})
    resp = entry.get("response", {})
    url = req.get("url", "")
    method = req.get("method", "")
    status = resp.get("status", 0)
    mime = resp.get("content", {}).get("mimeType", "")
    size = resp.get("content", {}).get("size", 0)
    text = resp.get("content", {}).get("text", "")
    
    urls.append((method, url, status, mime, size, len(text)))
    if "api" in url.lower() or "json" in mime.lower() or "service" in url.lower() or "ajax" in url.lower() or "tintuc" in url.lower() or "tin-tuc" in url.lower():
        api_calls.append((method, url, status, mime, size, len(text)))

print(f"Total relevant calls: {len(api_calls)}")
print("Sample relevant calls:")
for item in api_calls[:15]:
    print(f"{item[0]} | {item[2]} | {item[3]:<30} | {item[4]:<8} | {item[1]}")
