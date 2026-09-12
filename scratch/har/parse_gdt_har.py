import json
import sys
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with open("scratch/har/gdt/tin-tuc.har", "r", encoding="utf-8", errors="ignore") as f:
    data = json.load(f)

for entry in data.get("log", {}).get("entries", []):
    mime = entry.get("response", {}).get("content", {}).get("mimeType", "")
    if "html" in mime:
        text = entry.get("response", {}).get("content", {}).get("text", "")
        soup = BeautifulSoup(text, "html.parser")
        links = soup.find_all("a")
        print(f"HTML text length: {len(text)}, links found: {len(links)}")
        articles = []
        for a in links:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if len(title) > 15:
                articles.append((title, href))
        print(f"Found {len(articles)} potential articles:")
        for t, h in articles:
            print(f"  - {t} --> {h}")
