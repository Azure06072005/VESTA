import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

def inspect_har(har_path: str):
    print(f"\n=======================================================")
    print(f"INSPECTING HAR: {har_path}")
    print(f"=======================================================")
    p = Path(har_path)
    if not p.exists():
        print(f"File does not exist: {har_path}")
        return

    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        har_data = json.load(f)

    entries = har_data.get("log", {}).get("entries", [])
    print(f"Total entries: {len(entries)}")

    api_entries = []
    for i, entry in enumerate(entries):
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        method = req.get("method", "")
        status = resp.get("status", 0)
        mime = resp.get("content", {}).get("mimeType", "")
        size = resp.get("content", {}).get("size", 0)

        # Look for JSON responses or interesting endpoints
        if "json" in mime or "api" in url.lower() or "nganh" in url.lower() or "industry" in url.lower() or "sector" in url.lower():
            api_entries.append((i, method, url, status, mime, size))

    print(f"Found {len(api_entries)} potentially relevant API/JSON entries.")
    for idx, method, url, status, mime, size in api_entries[:25]:
        print(f"[{idx}] {method} ({status}, {size}B) {url[:120]}")

    # Inspect the largest JSON responses
    print("\n--- Top 5 Largest JSON responses ---")
    json_responses = []
    for i, entry in enumerate(entries):
        resp = entry.get("response", {})
        mime = resp.get("content", {}).get("mimeType", "")
        size = resp.get("content", {}).get("size", 0)
        text = resp.get("content", {}).get("text", "")
        url = entry.get("request", {}).get("url", "")
        if text and ("json" in mime or text.strip().startswith("{") or text.strip().startswith("[")):
            json_responses.append((size, url, text))

    json_responses.sort(key=lambda x: x[0], reverse=True)
    for sz, url, text in json_responses[:5]:
        print(f"Size: {sz}B | URL: {url[:100]}")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                print(f"  Type: List, Len: {len(parsed)}, Sample: {json.dumps(parsed[0], ensure_ascii=False)[:200]}")
            elif isinstance(parsed, dict):
                print(f"  Type: Dict, Keys: {list(parsed.keys())[:10]}")
                for k in list(parsed.keys())[:3]:
                    val = parsed[k]
                    if isinstance(val, list):
                        print(f"    Key '{k}': List len={len(val)}, Sample: {json.dumps(val[0], ensure_ascii=False)[:150] if val else 'empty'}")
                    elif isinstance(val, dict):
                        print(f"    Key '{k}': Dict keys={list(val.keys())[:5]}")
        except Exception as e:
            print(f"  Parse error: {e}")

inspect_har(r"d:\VESTA\scratch\har\vietstock\du_lieu_nganh.har")
inspect_har(r"d:\VESTA\scratch\har\anfin\du_lieu_nganh.har")
