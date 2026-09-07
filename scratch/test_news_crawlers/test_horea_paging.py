import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
})

resp = s.get("https://www.horea.org.vn/hoat-dong-horea.html", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Look for pagination containers, ul, div class
pagers = soup.find_all(class_=lambda c: c and any(k in c.lower() for k in ["page", "paging", "pagination", "nav"]))
print(f"Pagers found: {len(pagers)}")
for p in pagers:
    print(p.name, p.get("class"))
    print(p.prettify()[:400])

# Look for all articles in hoat-dong-horea
articles = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if "/hoat-dong-horea/" in href and len(text) > 20:
        articles.append((text, href))

print(f"\nArticles on page 1 of hoat-dong-horea: {len(articles)}")
for t, h in articles[:5]:
    print(f"  {t[:60]} -> {h}")
