import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_dir = Path("D:/VESTA/scratch/har/yahoo_finance")
har_files = sorted(har_dir.glob("*.har"), key=lambda p: p.stat().st_mtime, reverse=True)

print(f"Found {len(har_files)} HAR files:")
for hf in har_files:
    print(f"  * {hf.name:<35} | size: {hf.stat().st_size:,} bytes | mtime: {hf.stat().st_mtime}")

newest_har = har_files[0]
print(f"\n=========================================================================")
print(f">>> ANALYZING NEWEST HAR: {newest_har.name} <<<")
print(f"=========================================================================")

with open(newest_har, "r", encoding="utf-8", errors="ignore") as f:
    har_data = json.load(f)

entries = har_data.get("log", {}).get("entries", [])
print(f"Total network entries: {len(entries)}")

api_entries = []
endpoints = {}

for idx, entry in enumerate(entries):
    req = entry.get("request", {})
    resp = entry.get("response", {})
    url = req.get("url", "")
    method = req.get("method", "")
    status = resp.get("status", 0)
    mime = resp.get("content", {}).get("mimeType", "")
    
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path
    
    # Filter for relevant Yahoo Finance endpoints (JSON APIs, query endpoints, news)
    is_relevant = (
        "yahoo.com" in domain and (
            "json" in mime or 
            "api" in path or 
            "query" in domain or 
            "news" in path or 
            "stream" in path or
            "graphql" in path or
            "quote" in path
        )
    )
    
    # Exclude tracking / telemetry
    is_telemetry = any(t in url for t in ["y-adp", "gemini", "pixel", "telemetry", "beacon", "ad", "ads", "analytics", "collector"])
    
    if is_relevant and not is_telemetry:
        api_entries.append({
            "idx": idx,
            "url": url,
            "method": method,
            "status": status,
            "mime": mime,
            "domain": domain,
            "path": path,
            "query": parse_qs(parsed.query),
            "request_headers": {h["name"]: h["value"] for h in req.get("headers", [])},
            "response_size": resp.get("content", {}).get("size", 0),
            "response_text": resp.get("content", {}).get("text", "")[:500] if resp.get("content", {}).get("text") else "",
        })
        key = f"{method} {domain}{path}"
        endpoints[key] = endpoints.get(key, 0) + 1

print(f"\nFound {len(api_entries)} relevant API/JSON requests. Distinct endpoints:")
for ep, count in sorted(endpoints.items(), key=lambda x: -x[1]):
    print(f"  [{count:2d}x] {ep}")

print("\n-------------------------------------------------------------------------")
print(">>> DETAILED INSPECTION OF TOP CANDIDATE API REQUESTS <<<")
print("-------------------------------------------------------------------------")
for item in api_entries[:8]:
    print(f"\n[#{item['idx']}] {item['method']} {item['url'][:100]}")
    print(f"  Status: {item['status']} | MIME: {item['mime']} | Size: {item['response_size']} bytes")
    # Show important request headers
    for h in ["User-Agent", "Accept", "Authorization", "Cookie", "Referer", "x-crumb", "x-api-key"]:
        if h in item["request_headers"]:
            val = item["request_headers"][h]
            print(f"  Header [{h}]: {val[:80]}...")
    if item["query"]:
        print(f"  Query Params: {list(item['query'].keys())}")
    if item["response_text"]:
        print(f"  Sample Response: {item['response_text'][:200]}...")
