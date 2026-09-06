import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

all_discovered = set()

# 1. Steering doc categories
steering_cates = [11495, 11509, 11502, 11491, 11493, 11489, 11494]
for sc in steering_cates:
    url = f"http://www.hoinongdan.org.vn/?pageid=27205&p_cate={sc}"
    r = s.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "p_steering=" in a["href"]:
            all_discovered.add((a.get_text(strip=True), a["href"]))

print(f"Discovered steering docs: {len(all_discovered)}")

# 2. News / policy categories
news_cats = ["chinh-sach", "hop-tac-xa-nong-nghiep", "khoa-hoc-cong-nghe", "tin-tuc-chinh-tri"]
news_discovered = set()
for nc in news_cats:
    url = f"http://www.hoinongdan.org.vn/{nc}"
    r = s.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        # Check if article URL pattern /{cat}/{slug}-{id}
        if f"/{nc}/" in href and len(text) > 20:
            news_discovered.add((text, href))

print(f"Discovered news/policy articles: {len(news_discovered)}")
print(f"Total discovered in initial sweep: {len(all_discovered) + len(news_discovered)}")
