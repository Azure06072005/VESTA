import json
from pathlib import Path
from bs4 import BeautifulSoup
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

targets = [
    ("tinnhanhchungkhoan", "scratch/har/tinnhanhchungkhoan/chung_khoan.har"),
    ("thoibaotaichinh", "scratch/har/thoibaotaichinh/chungkhoan.har"),
    ("thoibaonganhang", "scratch/har/thoibaonganhang/kinhte.har"),
    ("nguoiquansat", "scratch/har/nguoiquansat/chungkhoan.har"),
    ("nhandan", "scratch/har/nhandan/kinhte.har"),
    ("vietnamfinance", "scratch/har/vietnamfinance/tai_chinh.har"),
    ("mof", "scratch/har/mof/tin-tuc-tai-chinh.har"),
    ("gdt", "scratch/har/gdt/tin-tuc.har")
]

for label, har_file in targets:
    p = Path(har_file)
    if not p.exists():
        print(f"File not found: {p}")
        continue
    print(f"\n{'='*60}\nPROBING {label.upper()} ({p.name})\n{'='*60}")
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    entries = data.get("log", {}).get("entries", [])
    
    article_links = set()
    api_calls = []
    
    for e in entries:
        req_url = e.get("request", {}).get("url", "")
        resp = e.get("response", {})
        mime = resp.get("content", {}).get("mimeType", "")
        text = resp.get("content", {}).get("text", "")
        status = resp.get("status", 0)
        
        if "api" in req_url or "ajax" in req_url or "json" in mime:
            if len(text) > 200:
                api_calls.append((req_url, len(text), text[:150]))
                
        if ("html" in mime or len(text) > 2000) and text:
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if len(title) > 25:
                    article_links.add((href, title))
                    
    print(f"Total entries: {len(entries)}")
    print(f"Unique title+link articles discovered: {len(article_links)}")
    print("Sample article links:")
    for h, t in list(article_links)[:4]:
        print(f"   * [{t[:60]}] -> {h[:70]}")
    if api_calls:
        print(f"Discovered APIs ({len(api_calls)}):")
        for u, sz, snip in api_calls[:3]:
            print(f"   API: {u[:80]} (size: {sz})")
            print(f"        Snippet: {snip[:100]}...")
