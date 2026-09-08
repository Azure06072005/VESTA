import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

url = "https://luatvietnam.vn/xuat-nhap-khau/thong-tu-41-2026-tt-bct-danh-muc-phe-lieu-va-hang-hoa-tam-ngung-kinh-doanh-441401-d1.html"
r = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

# Look for tables or attributes
tables = soup.find_all('table')
print(f"Total tables found: {len(tables)}")
for i, t in enumerate(tables[:3]):
    rows = t.find_all('tr')
    print(f"\nTable #{i+1} has {len(rows)} rows:")
    for r in rows[:8]:
        cols = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
        if cols:
            print("   | " + " | ".join(cols))

# Check any meta tags or property tags
meta_props = {m.get('property') or m.get('name'): m.get('content') for m in soup.find_all('meta') if m.get('content')}
for k, v in meta_props.items():
    if any(term in str(k).lower() for term in ['date', 'time', 'publish', 'title', 'description']):
        print(f"Meta: {k} -> {v}")
