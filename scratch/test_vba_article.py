import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

url = "https://vba.com.vn/vba-gop-y-du-thao-luat-an-toan-thuc-pham-de-nghi-giam-tien-kiem-tang-tinh-kha-thi.html"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

detail = soup.find("div", class_="wrap-blog-detail-main")
if detail:
    # Look at previous siblings
    prev = detail.find_previous_siblings()
    print("Previous siblings count:", len(prev))
    for p in prev:
        print(f"  <{p.name} class='{p.get('class')}'> {p.get_text(strip=True)[:100]}")
