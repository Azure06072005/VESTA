import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

categories = ["gdt", "mof", "tienphong", "tuoitre", "vietnamfinance", "vietstock", "vneconomy"]

summary = {}
for cat in categories:
    cat_dir = Path("scratch/har") / cat
    if not cat_dir.exists():
        continue
    har_files = list(cat_dir.glob("*.har"))
    summary[cat] = {"files": len(har_files), "articles": []}
    
    for h in har_files:
        try:
            with open(h, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            entries = data.get("log", {}).get("entries", [])
            for e in entries:
                mime = e.get("response", {}).get("content", {}).get("mimeType", "")
                text = e.get("response", {}).get("content", {}).get("text", "")
                url = e.get("request", {}).get("url", "")
                if "html" in mime and len(text) > 1000:
                    soup = BeautifulSoup(text, "html.parser")
                    # Look for article links
                    for a in soup.find_all("a"):
                        t = a.get_text(strip=True)
                        hr = a.get("href", "")
                        if len(t) > 30 and hr and not hr.startswith("javascript"):
                            summary[cat]["articles"].append((t, hr, h.name))
                elif "json" in mime and len(text) > 200:
                    # check if json has news
                    summary[cat]["articles"].append((f"JSON API response ({len(text)} bytes)", url, h.name))
        except Exception as err:
            print(f"Error parsing {h}: {err}")

print(f"{'Category / Source':<20} | {'HAR Files':<10} | {'Extracted Links/Entries'}")
print("-" * 65)
for cat, info in summary.items():
    uniq_titles = len(set(t[0] for t in info["articles"]))
    print(f"{cat:<20} | {info['files']:<10} | {len(info['articles'])} total ({uniq_titles} unique)")
    for t, hr, src_f in info["articles"][:3]:
        print(f"   [{src_f}] {t[:60]} -> {hr[:50]}")
