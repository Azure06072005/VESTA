import requests
from bs4 import BeautifulSoup
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

r = requests.get("http://www.hoinongdan.org.vn/chinh-sach", headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "html.parser")

scripts = soup.find_all("script")
print(f"Scripts on page: {len(scripts)}")
for s in scripts:
    text = s.get_text()
    if any(k in text for k in ["pagination", "page-number", "data-page", "ajax", "fetch", "/api/"]):
        print("--- Matching Script ---")
        print(text[:500])
