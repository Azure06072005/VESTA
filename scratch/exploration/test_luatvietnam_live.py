import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

urls = [
    "https://luatvietnam.vn/tin-phap-luat.html",
    "https://luatvietnam.vn/van-ban-moi.html",
    "https://luatvietnam.vn/doanh-nghiep.html",
    "https://luatvietnam.vn/thue-phi.html",
    "https://luatvietnam.vn/tai-chinh.html",
    "https://luatvietnam.vn/ngan-hang.html"
]

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"URL: {url} -> Status: {r.status_code}, Length: {len(r.text)}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            title = soup.title.get_text(strip=True) if soup.title else 'No Title'
            links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.html')]
            print(f"   Title: {title}")
            print(f"   HTML Links ending in .html: {len(links)}")
            sample = [l for l in links if not l.startswith('http') and len(l) > 20][:3]
            print(f"   Sample articles: {sample}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
