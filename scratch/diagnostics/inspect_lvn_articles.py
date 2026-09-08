import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 1. Inspect articles from /tin-phap-luat.html
r1 = requests.get("https://luatvietnam.vn/tin-phap-luat.html", headers=headers, timeout=10)
soup1 = BeautifulSoup(r1.text, 'html.parser')

print("--- ARTICLES FROM TIN-PHAP-LUAT ---")
articles_tin = []
for a in soup1.find_all('a', href=True):
    href = a['href']
    title = a.get_text(strip=True)
    if '/tin-van-ban/' in href or '/tin-phap-luat/' in href or '-d1.html' in href or '-d2.html' in href:
        if len(title) > 20 and not href.endswith('-article.html'):
            articles_tin.append((title, href if href.startswith('http') else f"https://luatvietnam.vn{href}"))

print(f"Found {len(articles_tin)} candidate article links in tin-phap-luat.")
for t, u in articles_tin[:3]:
    print(f"  * {t}\n    URL: {u}")

# 2. Inspect articles from /van-ban-moi.html
r2 = requests.get("https://luatvietnam.vn/van-ban-moi.html", headers=headers, timeout=10)
soup2 = BeautifulSoup(r2.text, 'html.parser')
print("\n--- ARTICLES FROM VAN-BAN-MOI ---")
articles_vb = []
for a in soup2.find_all('a', href=True):
    href = a['href']
    title = a.get_text(strip=True)
    if ('-d1.html' in href or '-d2.html' in href or '/van-ban/' in href) and len(title) > 25:
        articles_vb.append((title, href if href.startswith('http') else f"https://luatvietnam.vn{href}"))

print(f"Found {len(articles_vb)} candidate legal document links in van-ban-moi.")
for t, u in articles_vb[:3]:
    print(f"  * {t}\n    URL: {u}")

# 3. Test fetching 1 sample from each
if articles_tin:
    sample_url = articles_tin[0][1]
    print(f"\nFetching sample tin article: {sample_url}")
    rs = requests.get(sample_url, headers=headers, timeout=10)
    print(f"Status: {rs.status_code}, Length: {len(rs.text)}")
    ss = BeautifulSoup(rs.text, 'html.parser')
    h1 = ss.find('h1')
    print("H1:", h1.get_text(strip=True) if h1 else 'None')
    time_tag = ss.find('time') or ss.find('span', class_=lambda c: c and 'date' in c) or ss.find('div', class_=lambda c: c and 'date' in c)
    print("Date element:", time_tag.get_text(strip=True) if time_tag else 'None')
    content_div = ss.find('div', class_='the-content') or ss.find('div', class_='content-detail') or ss.find('article') or ss.find('div', id='content-detail')
    if content_div:
        print("Content div found, class/id:", content_div.get('class'), content_div.get('id'))
        paras = [p.get_text(strip=True) for p in content_div.find_all('p') if len(p.get_text(strip=True)) > 25]
        print(f"Paragraphs: {len(paras)}")
        for p in paras[:2]:
            print(f"  > {p}")
