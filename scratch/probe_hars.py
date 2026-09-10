import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def probe_har(fpath):
    print(f"\n==========================================")
    print(f"PROBING: {fpath}")
    print(f"==========================================")
    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    entries = data.get("log", {}).get("entries", [])
    print(f"Total entries: {len(entries)}")
    
    html_entries = []
    json_entries = []
    for e in entries:
        mime = e.get("response", {}).get("content", {}).get("mimeType", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        url = e.get("request", {}).get("url", "")
        if "html" in mime and len(text) > 2000:
            html_entries.append((url, len(text), text))
        elif "json" in mime and len(text) > 500:
            json_entries.append((url, len(text), text))
            
    print(f"HTML responses: {len(html_entries)}, JSON responses: {len(json_entries)}")
    for url, sz, text in html_entries[:2]:
        soup = BeautifulSoup(text, "html.parser")
        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(strip=True) if title else "No title"
        print(f"  [HTML] URL: {url[:70]}")
        print(f"         Title: {title_text[:80]}")
    for url, sz, text in json_entries[:2]:
        print(f"  [JSON] URL: {url[:70]} | Size: {sz} bytes")

probe_har(Path("scratch/har/tienphong/kinh_te.har"))
probe_har(Path("scratch/har/tuoitre/kinh_doanh.har"))
probe_har(Path("scratch/har/vneconomy/chung_khoan.har"))
probe_har(Path("scratch/har/vietstock/chung_khoan.har"))
