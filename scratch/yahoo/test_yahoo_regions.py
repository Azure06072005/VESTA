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

regions = ['US', 'GB', 'CA', 'AU', 'SG', 'VN']
for r in regions:
    url = f"https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=50&lang=en-US&region={r}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
        items = resp.json().get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])
        print(f"region={r} -> {len(items)} items. Sample: {items[0]['notificationTitle'] if items else 'None'}")
    else:
        print(f"region={r} -> status {resp.status_code}")

# Also test pagination: e.g. before / publishTs / cursor / offset
min_ts = 1786118485000
for param in ['before', 'publishTs', 'cursor', 'offset', 'since']:
    url = f"https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=50&lang=en-US&region=US&{param}={min_ts}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
        items = resp.json().get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])
        if items and items[-1]['publishTs'] < min_ts:
            print(f"PAGINATION SUCCESS with {param}={min_ts}! Returned older items down to {items[-1]['publishTs']}")
