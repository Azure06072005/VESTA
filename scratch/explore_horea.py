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

# 1. Inspect categories on HoREA
resp = s.get("https://www.horea.org.vn", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

menus = []
for a in soup.find_all("a", href=True):
    text = a.get_text(strip=True)
    href = a["href"]
    if any(k in href for k in ["hoat-dong-horea", "phap-luat", "tin-tuc", "thi-truong-bat-dong-san", "nghien-cuu"]):
        menus.append((text, href))

print("HoREA Key Menus:")
for text, href in set(menus):
    print(f"  {text} -> {href}")

# 2. Check pagination on 'hoat-dong-horea.html'
resp_act = s.get("https://www.horea.org.vn/hoat-dong-horea.html", timeout=15)
soup_act = BeautifulSoup(resp_act.text, "html.parser")

pagers = soup_act.find_all("a", href=lambda h: h and ("trang-" in h or "page=" in h or "p=" in h))
print(f"\nPagination links on hoat-dong-horea.html: {len(pagers)}")
for p in pagers[:10]:
    print(f"  {p.get_text(strip=True)} -> {p.get('href')}")
