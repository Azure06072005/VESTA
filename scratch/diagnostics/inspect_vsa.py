import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get("https://vsa.com.vn", headers=headers, timeout=10)
soup = BeautifulSoup(r.text, "html.parser")

nav_links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if text and "vsa.com.vn" in href:
        nav_links.append((text, href))

print("Nav links on VSA (Thép):")
for t, h in list(set(nav_links))[:30]:
    if len(t) > 3:
        print(f"  {h} -> {t}")
