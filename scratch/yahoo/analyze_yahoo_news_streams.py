import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

with open('D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

e311 = data['log']['entries'][311]
js311 = json.loads(e311['response']['content']['text'])
notifs = js311['finance']['result'][0]['notificationsWithMeta']
print(f'Total notifications in Entry 311: {len(notifs)}')
for i, n in enumerate(notifs[:10]):
    ts = n.get('publishTs')
    dt_str = datetime.fromtimestamp(ts/1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else 'N/A'
    print(f"[{i+1}] {n.get('notificationTitle')}")
    print(f"    Published: {dt_str} ({ts})")
    print(f"    URL: {n.get('articleUrl')}")
    print(f"    ID: {n.get('id')}")

print('\nSearching for other entries with stream / article / feed / news...')
seen_urls = set()
for idx, entry in enumerate(data['log']['entries']):
    url = entry['request']['url']
    if url in seen_urls:
        continue
    seen_urls.add(url)
    text = entry['response'].get('content', {}).get('text', '')
    status = entry['response']['status']
    
    # Check if this URL might have articles or news
    if any(k in url.lower() for k in ['stream', 'listid', 'article', 'feed', 'stories', 'editorial', 'news']):
        if not any(k in url.lower() for k in ['notification', 'ads', 'telemetry', 'analytics', '.png', '.jpg', '.svg', '.gif', '.css', '.js']):
            print(f"Entry #{idx}: {entry['request']['method']} {url[:130]}")
            print(f"   Status: {status}, Response Length: {len(text)}")
            if text and len(text) > 100:
                # check if html or json
                if text.strip().startswith('{') or text.strip().startswith('['):
                    try:
                        parsed = json.loads(text)
                        print(f"   JSON Keys/Type: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}")
                    except Exception:
                        pass
                elif '<html' in text.lower():
                    print("   HTML Document (Title preview):", text[:300].replace('\n', ' '))
