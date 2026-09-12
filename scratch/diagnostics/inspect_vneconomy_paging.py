import requests
import re
from bs4 import BeautifulSoup

r = requests.get('https://vneconomy.vn/tai-chinh.htm', headers={'User-Agent': 'Mozilla/5.0'})
soup = BeautifulSoup(r.text, 'html.parser')

scripts = soup.find_all('script')
for s in scripts:
    src = s.get('src', '')
    if src:
        print('Script src:', src)
    elif s.string and any(k in s.string for k in ['zone', 'page', 'category', 'api', 'ajax']):
        for line in s.string.splitlines():
            if any(k in line.lower() for k in ['zone', 'page', 'api', 'load', 'url', 'id']):
                print(' Inline JS:', line.strip()[:100])
