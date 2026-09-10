import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://finance.yahoo.com',
    'referer': 'https://finance.yahoo.com/markets/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0'
}

for c in [50, 100, 200, 300, 500]:
    url = f"https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count={c}&lang=en-US&region=US"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 200:
        items = r.json().get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])
        print(f"count={c} -> returned {len(items)} items")
    else:
        print(f"count={c} -> status {r.status_code}")
