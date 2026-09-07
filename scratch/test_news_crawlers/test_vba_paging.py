import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

for cat in ["chinh-sach-1.html", "hoat-dong-hiep-hoi.html"]:
    url = f"https://vba.com.vn/{cat}"
    resp = s.get(url, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    print(f"\n--- Category: {cat} (Status: {resp.status_code}) ---")
    
    # Pagination
    pagers = soup.find_all(class_=lambda c: c and any(k in c.lower() for k in ["page", "paging", "pagination"]))
    print(f"Pagers found: {len(pagers)}")
    for p in pagers:
        print(p.prettify()[:400])
        
    # Article links
    articles = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if href.endswith(".html") and len(text) > 25 and not any(k in href for k in ["chinh-sach", "hoat-dong", "doanh-nghiep", "tin-tuc", "gioi-thieu"]):
            articles.append((text, href))
            
    print(f"Article candidates: {len(articles)}")
    for t, h in articles[:3]:
        print(f"  {t[:60]} -> {h}")
