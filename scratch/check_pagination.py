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

resp = s.get("https://sbv.gov.vn/vi/tin-tuc-su-kien", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Find any links with 'cur=' or 'page=' or pagination ul/li
p_links = soup.find_all("a", href=lambda h: h and any(k in h for k in ["cur=", "page=", "delta=", "p_p_id="]))
print(f"Pagination links found: {len(p_links)}")
for a in p_links:
    print(a.get_text(strip=True), "->", a.get("href"))

# Also find pagination lists
paginations = soup.find_all(class_=lambda c: c and "pagination" in c.lower())
print(f"Pagination elements found: {len(paginations)}")
for p in paginations:
    print(p.prettify()[:500])
