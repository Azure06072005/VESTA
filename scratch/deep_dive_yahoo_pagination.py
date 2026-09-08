import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_dir = 'd:/VESTA/scratch/har/yahoo_finance'
files = [
    'finance.yahoo.com-News.har',
    'finance.yahoo.com-markets.har',
    'finance.yahoo.com-main_page.har'
]

print("=== DEEP DIVE: SCROLLING & PAGINATION IN ALL YAHOO HAR FILES ===")

all_entries = []
for f in files:
    path = os.path.join(har_dir, f)
    print(f"\nLoading {f} ({os.path.getsize(path)} bytes)...")
    with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
        data = json.load(fp)
    entries = data.get('log', {}).get('entries', [])
    print(f"Total entries: {len(entries)}")
    for e in entries:
        all_entries.append((f, e))

print(f"\nTotal combined entries across 3 files: {len(all_entries)}")

# Search for any request that might be related to loading more news / pagination / stream
keywords = ['stream', 'scroll', 'page', 'offset', 'cursor', 'start', 'count', 'more', 'content', 'cds', 'article', 'feed']

matching = []
seen_urls = set()
for fname, entry in all_entries:
    req = entry['request']
    url = req['url']
    if url in seen_urls:
        continue
    seen_urls.add(url)
    
    # Filter out static assets
    if any(k in url.lower() for k in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.css', '.woff', '.ttf', 'telemetry', 'analytics', 'doubleclick', 'gemini', 'adserver', 'yahoo-gemini', 'casale', 'openx', 'crwdcntrl', 'rubicon']):
        continue
        
    url_lower = url.lower()
    if any(k in url_lower for k in ['query', 'xhr', 'feed', 'stream', 'news', 'articles']):
        resp = entry['response']
        status = resp.get('status', 0)
        mime = resp.get('content', {}).get('mimeType', '')
        size = len(resp.get('content', {}).get('text', ''))
        matching.append((fname, req['method'], url, status, mime, size))

print(f"Found {len(matching)} candidate API/data requests across all 3 HARs:")
for fname, method, url, status, mime, size in matching:
    print(f"[{fname[:15]}] {method} {url[:100]} (Status: {status}, Size: {size})")
