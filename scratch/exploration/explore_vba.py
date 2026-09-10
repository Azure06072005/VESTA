import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
})

resp = s.get("https://vba.com.vn", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

print("VBA Homepage Title:", soup.title.string if soup.title else "None")

# Find menus / categories
categories = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if any(k in href.lower() for k in ["tin-tuc", "chinh-sach", "van-ban", "hoat-dong", "hoi-nhap", "doanh-nghiep"]):
        categories.append((text, href))

print(f"\nUnique category candidates: {len(set(categories))}")
for t, h in list(set(categories))[:15]:
    print(f"  {t} -> {h}")
