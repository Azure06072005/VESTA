import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open('D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for idx, entry in enumerate(data['log']['entries']):
    req = entry['request']
    url = req['url']
    resp = entry['response']
    mime = resp.get('content', {}).get('mimeType', '')
    text = resp.get('content', {}).get('text', '')
    status = resp['status']
    
    if 'text/html' in mime and status == 200 and text:
        print(f"==================================================")
        print(f"HTML Doc #{idx}: {url}")
        print(f"HTML size: {len(text)} bytes")
        
        soup = BeautifulSoup(text, 'html.parser')
        title = soup.title.string if soup.title else 'No title'
        print(f"Title: {title}")
        
        # Check for embedded script data (like window.__INITIAL_STATE__, etc.)
        scripts = soup.find_all('script')
        for s in scripts:
            stext = s.string or ''
            for marker in ['root.App.main', '__INITIAL_STATE__', 'YFINANCE_CONFIG', 'STREAM', 'initialStore', 'preloadedState']:
                if marker in stext:
                    print(f"  Found script marker '{marker}' (length: {len(stext)})")
        
        # Check for article links
        links = soup.find_all('a', href=True)
        news_links = [a['href'] for a in links if '/news/' in a['href'] or '/article/' in a['href'] or '/m/' in a['href']]
        print(f"Total links: {len(links)}, News/Article links: {len(news_links)}")
        if news_links:
            print(f"Sample news links: {news_links[:5]}")
