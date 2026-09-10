import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

har_dir = Path("scratch/har/vietnamfinance")
har_files = list(har_dir.glob("*.har"))
print(f"VietnamFinance HAR files: {len(har_files)}")

articles = []
seen = set()

# Process first 3 HAR files as sample
for h in har_files[:4]:
    print(f"Reading {h.name}...")
    with open(h, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        resp = e.get("response", {}).get("content", {}).get("text", "")
        if not resp:
            continue
        if "vietnamfinance.vn" in url and "html" in e.get("response", {}).get("content", {}).get("mimeType", ""):
            soup = BeautifulSoup(resp, "html.parser")
            for a in soup.find_all("a"):
                t = a.get_text(strip=True)
                hr = a.get("href", "")
                # vietnamfinance articles typically have -d\d+.html
                if len(t) > 25 and hr and ("-d" in hr or "vietnamfinance.vn" in hr or hr.endswith(".html")):
                    full_url = f"https://vietnamfinance.vn{hr}" if hr.startswith("/") else hr
                    if full_url not in seen and not any(skip in full_url for skip in ["/chuyen-muc", "/tag", "/video", "/media"]):
                        seen.add(full_url)
                        articles.append({
                            "source": "vietnamfinance",
                            "issuing_body": "VietnamFinance",
                            "headline": t,
                            "url": full_url,
                            "file": h.name
                        })

print(f"VietnamFinance unique articles extracted from 4 files: {len(articles)}")
for r in articles[:5]:
    print(f"[{r['file']}] {r['headline'][:65]} -> {r['url']}")
