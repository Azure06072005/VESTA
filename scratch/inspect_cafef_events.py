import urllib.request
import re
import sys
import json
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

url = 'https://cafef.vn/du-lieu/lich-su-kien.chn'
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as res:
    html = res.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')

print("Page Title:", soup.title.string if soup.title else "No title")

# Check for table
tables = soup.find_all('table')
print(f"Tables count: {len(tables)}")
for i, table in enumerate(tables):
    rows = table.find_all('tr')
    print(f"Table {i}: {len(rows)} rows")
    if rows:
        headers_row = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
        print(f"  Headers: {headers_row}")
        if len(rows) > 1:
            sample_row = [td.get_text(strip=True) for td in rows[1].find_all('td')]
            print(f"  Sample row 1: {sample_row}")

# Check for scripts and form elements
scripts = soup.find_all('script')
for s in scripts:
    text = s.get_text()
    if 'ajax' in text.lower() or 'ashx' in text.lower():
        for line in text.split('\n'):
            line_s = line.strip()
            if any(k in line_s.lower() for k in ['url:', 'ashx', 'api', 'pageindex', 'sukien']):
                print("Script line:", line_s)
