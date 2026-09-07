import sys
import requests
import re
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://vasep.com.vn/san-pham-xuat-khau/tom/xuat-nhap-khau/gsf-2026-tang-tieu-thu-tom-tai-eu-tu-thay-doi-san-pham-va-cach-tiep-can-thi-truong-38101.html"
resp = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(resp.text, "html.parser")
title = soup.find("h1")
pub_time = soup.find("meta", property="article:published_time") or soup.find("time")
body = soup.select_one(".content-detail, .detail-content, .entry-content, #content, .content")
print("Title:", title.text.strip() if title else None)
print("Meta title:", soup.find("meta", property="og:title"))
print("Pub time:", pub_time.get("content") if pub_time and pub_time.name == "meta" else pub_time.text.strip() if pub_time else None)
print("Body length:", len(body.text.strip()) if body else 0)
print("Body snippet:", body.text.strip()[:200] if body else None)




