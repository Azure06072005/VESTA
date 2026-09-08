import sys
import requests
import re
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

url = "https://www.tinnhanhchungkhoan.vn/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
resp = requests.get(url, headers=headers, timeout=10)
print("Status:", resp.status_code, "Length:", len(resp.text))

soup = BeautifulSoup(resp.text, "html.parser")
nav_links = [(a.text.strip(), a.get("href")) for a in soup.select("nav a, header a") if a.get("href")]
print("Top Nav links:")
for txt, href in nav_links[:15]:
    print(f" - {txt}: {href}")

a_url = "https://www.tinnhanhchungkhoan.vn/tw3-ngay-gdkhq-tra-co-tuc-nam-2025-bang-tien-10-post396858.html"
ra = requests.get(a_url, headers=headers, timeout=10)
soup_a = BeautifulSoup(ra.text, "html.parser")
print("All h1:", [h.text.strip() for h in soup_a.find_all("h1")])
print("Meta title:", soup_a.find("meta", property="og:title"))
candidates = [(div.get("class"), len(div.text.strip())) for div in soup_a.find_all("div") if div.get("class") and any("content" in c or "body" in c or "detail" in c or "post" in c for c in div.get("class"))]
print("Content div candidates:", candidates[:10])








