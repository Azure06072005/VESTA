import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

url = "http://www.hoinongdan.org.vn/chinh-sach"
resp = s.get(url, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

print("Status:", resp.status_code)
print("Title:", soup.title.string if soup.title else "None")

# Find pagination
pagers = soup.find_all(class_=lambda c: c and any(k in c.lower() for k in ["page", "paging", "pagination"]))
print(f"Pagers found: {len(pagers)}")
for p in pagers:
    print(p.prettify()[:400])

# Also look for a tags with p= or page=
p_links = soup.find_all("a", href=lambda h: h and any(k in h for k in ["page", "p=", "trang", "chinh-sach/"]))
print(f"P links: {len(p_links)}")
for a in p_links[:10]:
    print(f"  {a.get_text(strip=True)} -> {a.get('href')}")
