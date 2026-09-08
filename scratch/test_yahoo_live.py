import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://finance.yahoo.com',
    'referer': 'https://finance.yahoo.com/markets/',
    'sec-ch-ua': '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0'
}

url = "https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=50&lang=en-US&region=US"
print(f"Testing live fetch: {url}")

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Response size: {len(resp.content)} bytes")
    if resp.status_code == 200:
        data = resp.json()
        items = data.get('finance', {}).get('result', [{}])[0].get('notificationsWithMeta', [])
        print(f"Successfully fetched {len(items)} live notifications/news items!")
        for idx, item in enumerate(items[:5]):
            print(f"[{idx+1}] {item.get('notificationTitle')}")
            print(f"    URL: {item.get('articleUrl')}")
            print(f"    PublishTs: {item.get('publishTs')}")
    else:
        print(resp.text[:500])
except Exception as e:
    print("Error:", e)
