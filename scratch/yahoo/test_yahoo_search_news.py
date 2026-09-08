import requests
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://finance.yahoo.com',
    'referer': 'https://finance.yahoo.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0'
}

queries = ['Fed', 'interest rates', 'inflation', 'Vietnam', 'oil', 'tariffs', 'stocks']
for q in queries:
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&newsCount=20&listsCount=0&quotesCount=0"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        news = data.get('news', [])
        print(f"Query '{q}': found {len(news)} news articles.")
        if news:
            n0 = news[0]
            pub_ts = n0.get('providerPublishTime')
            dt_str = datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M:%S') if pub_ts else 'N/A'
            print(f"   [0] {n0.get('title')}")
            print(f"       Published: {dt_str} | Publisher: {n0.get('publisher')}")
            print(f"       Link: {n0.get('link')}")
    else:
        print(f"Query '{q}': status {resp.status_code}")
