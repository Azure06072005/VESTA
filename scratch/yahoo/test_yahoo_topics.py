import requests
from bs4 import BeautifulSoup
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

topic_urls = [
    "https://finance.yahoo.com/topic/latest-news/",
    "https://finance.yahoo.com/topic/stock-market-news/",
    "https://finance.yahoo.com/economy/"
]

for url in topic_urls:
    print(f"\nFetching {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Find all article links
        links = soup.find_all('a', href=True)
        articles = []
        for a in links:
            href = a['href']
            # typical yahoo finance article format: /news/..., /markets/article/..., /economy/article/...
            if any(p in href for p in ['/news/', '/article/', '/live/']) and href.endswith('.html'):
                full_url = href if href.startswith('http') else f"https://finance.yahoo.com{href}"
                title = a.get_text(strip=True)
                if len(title) > 20:
                    articles.append((title, full_url))
        
        # deduplicate
        seen = set()
        deduped = []
        for t, u in articles:
            if u not in seen:
                seen.add(u)
                deduped.append((t, u))
                
        print(f"Found {len(deduped)} distinct articles:")
        for idx, (t, u) in enumerate(deduped[:5]):
            print(f"  [{idx+1}] {t[:75]}...")
            print(f"      {u}")
    except Exception as e:
        print("Error:", e)
