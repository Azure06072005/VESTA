import json
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

with open(r"d:\VESTA\scratch\har\vietstock\du_lieu_nganh.har", "r", encoding="utf-8", errors="ignore") as f:
    har = json.load(f)

print("=== ALL VIETSTOCK JSON RESPONSES ===")
for i, entry in enumerate(har.get("log", {}).get("entries", [])):
    req = entry.get("request", {})
    resp = entry.get("response", {})
    url = req.get("url", "")
    content = resp.get("content", {})
    text = content.get("text", "")
    size = content.get("size", 0)
    mime = content.get("mimeType", "")

    if text and ("json" in mime or text.strip().startswith("{") or text.strip().startswith("[")):
        print(f"[{i}] {req.get('method')} {url[:100]} ({size} bytes)")
        try:
            d = json.loads(text)
            if isinstance(d, list):
                print(f"    List len={len(d)}, sample={json.dumps(d[0], ensure_ascii=False)[:150]}")
            elif isinstance(d, dict):
                print(f"    Dict keys={list(d.keys())[:8]}")
        except Exception as e:
            print(f"    Parse error: {e}")
