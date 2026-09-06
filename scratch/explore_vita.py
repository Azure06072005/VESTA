import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
})

resp = s.get("https://vita.vn", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

links = set()
for a in soup.find_all("a", href=True):
    href = a["href"].strip()
    text = a.get_text(strip=True)
    if any(k in href.lower() for k in ["tin-tuc", "hoat-dong", "su-kien", "chinh-sach", "van-ban", "hoi-vien"]):
        links.add((text, href))

print(f"VITA links found: {len(links)}")
for t, h in list(links)[:15]:
    print(f"  {t} -> {h}")
