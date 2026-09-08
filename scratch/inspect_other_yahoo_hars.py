import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_dir = 'D:/VESTA/scratch/har/yahoo_finance/'
files = ['finance.yahoo.com-markets.har', 'finance.yahoo.com-main_page.har']

for fname in files:
    fpath = os.path.join(har_dir, fname)
    print(f"\n==================================================")
    print(f"Inspecting {fname}...")
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
    entries = data['log']['entries']
    print(f"Total entries: {len(entries)}")
    seen = set()
    for entry in entries:
        url = entry['request']['url']
        if any(k in url.lower() for k in ['feed', 'stream', 'notification', 'news', 'article', 'topic', 'quote', 'screener']):
            if not any(k in url.lower() for k in ['analytics', 'ad', 'beacon', 'telemetry', '.png', '.jpg', '.css', '.js']):
                clean_url = url.split('?')[0]
                query = url.split('?')[1] if '?' in url else ''
                key = (entry['request']['method'], clean_url)
                if key not in seen:
                    seen.add(key)
                    print(f"  {key[0]} {key[1]}?{query[:60]}")
