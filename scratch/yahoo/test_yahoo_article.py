import requests
from bs4 import BeautifulSoup
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'sec-ch-ua': '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0'
}

# 1. Test count=100
url_feed = "https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=100&lang=en-US&region=US"
r1 = requests.get(url_feed, headers=headers, timeout=10)
print(f"Feed count=100 status: {r1.status_code}")
if r1.status_code == 200:
    items = r1.json().get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])
    print(f"Returned {len(items)} items with count=100")

# 2. Test article HTML fetch
article_url = "https://finance.yahoo.com/markets/article/why-nvidia-wants-hugging-face-to-keep-helping-its-rivals-chart-of-the-day-132655037.html"
print(f"\nFetching article: {article_url}")
r2 = requests.get(article_url, headers=headers, timeout=10)
print(f"Article status: {r2.status_code}, content size: {len(r2.content)}")

if r2.status_code == 200:
    soup = BeautifulSoup(r2.text, 'html.parser')
    h1 = soup.find('h1')
    print(f"H1 Title: {h1.get_text(strip=True) if h1 else 'None'}")
    
    # Try finding article body
    article_tag = soup.find('article') or soup.find('div', class_=lambda c: c and 'body' in c) or soup.find('div', class_='caas-body')
    if article_tag:
        paras = [p.get_text(strip=True) for p in article_tag.find_all('p') if p.get_text(strip=True)]
        print(f"Article tag found! Paragraph count: {len(paras)}")
        print("Sample body (first 2 paras):")
        for p in paras[:2]:
            print(f"  {p}")
    else:
        # Fallback to all p tags
        paras = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 40]
        print(f"Fallback paragraph count: {len(paras)}")
        print("Sample body (first 2 paras):")
        for p in paras[:2]:
            print(f"  {p}")
