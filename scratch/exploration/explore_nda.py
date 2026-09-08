import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
})

try:
    resp = s.get("https://nda.org.vn", timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    print("NDA Title:", soup.title.string if soup.title else "None")
    
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        if len(text) > 10 and not href.startswith("javascript") and not href.startswith("#"):
            links.add((text, href))
            
    print(f"Unique links on NDA: {len(links)}")
    for t, h in list(links)[:15]:
        print(f"  {t[:50]} -> {h}")
except Exception as e:
    print(f"Error accessing NDA: {e}")
