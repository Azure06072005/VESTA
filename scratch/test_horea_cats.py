import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

for cat in ["phap-luat-bat-dong-san", "tin-tuc"]:
    url = f"https://www.horea.org.vn/{cat}.html"
    r = s.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    p_div = soup.find("div", class_="pages")
    page_links = [a.get("href") for a in p_div.find_all("a")] if p_div else []
    print(f"Category: {cat}")
    print(f"  Page 1 status: {r.status_code}, Pager links: {page_links[:4]}")
