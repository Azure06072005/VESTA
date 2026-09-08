import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

r = requests.get("https://luatvietnam.vn/tin-phap-luat.html", headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

print("All menu/category links on luatvietnam.vn/tin-phap-luat.html:")
categories = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if any(k in href for k in ['/doanh-nghiep', '/thue', '/tai-chinh', '/ngan-hang', '/chung-khoan', '/dat-dai', '/xuat-nhap-khau', '/tin-phap-luat/']):
        if len(text) > 3 and not href.endswith('-article.html'):
            categories.append((text, href if href.startswith('http') else f"https://luatvietnam.vn{href}"))

seen = set()
for t, u in categories:
    if u not in seen:
        seen.add(u)
        print(f"  * {t} -> {u}")
