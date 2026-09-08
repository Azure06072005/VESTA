import sys
import requests
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

url = 'https://vneconomy.vn/nhung-vung-dem-ho-tro-ty-gia-on-dinh-tu-nay-den-cuoi-nam.htm'
r = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(r.content, 'html.parser')

print('Title from meta og:title ->', soup.find('meta', property='og:title')['content'])
print('Desc from meta og:description ->', soup.find('meta', property='og:description')['content'])

# Find headline tag
for h in soup.find_all(['h1', 'h2', 'h3', 'div']):
    cls = ' '.join(h.get('class', []))
    txt = h.get_text(strip=True)
    if 'vùng đệm' in txt and len(txt) < 150:
        print(f'Tag <{h.name}> class="{cls}" -> {txt}')
        break

# Find body container
for div in soup.find_all('div'):
    cls = ' '.join(div.get('class', []))
    if any(k in cls for k in ['detail__content', 'content-detail', 'article-content', 'main-content', 'post-content']):
        print(f'Body tag class="{cls}", len text={len(div.get_text(strip=True))}')
