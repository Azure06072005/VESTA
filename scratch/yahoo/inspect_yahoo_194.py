import requests
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://finance.yahoo.com',
    'referer': 'https://finance.yahoo.com/markets/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0'
}

url = "https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=200&lang=en-US&region=US"
r = requests.get(url, headers=headers, timeout=10)
items = r.json().get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])

print(f"Total items fetched: {len(items)}")

timestamps = [it['publishTs'] for it in items if 'publishTs' in it and it['publishTs']]
if timestamps:
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    min_dt = datetime.fromtimestamp(min_ts / 1000.0)
    max_dt = datetime.fromtimestamp(max_ts / 1000.0)
    print(f"Earliest article: {min_dt} ({min_ts})")
    print(f"Latest article:   {max_dt} ({max_ts})")

# Sample item keys and structure
if items:
    print("\nKeys in item 0:", list(items[0].keys()))
    print("Item 0 JSON:\n", json.dumps(items[0], indent=2))

# Also check how many have articleUrl
urls = [it.get('articleUrl') for it in items if it.get('articleUrl')]
print(f"\nItems with articleUrl: {len(urls)} / {len(items)}")
print(f"Unique URLs: {len(set(urls))}")
