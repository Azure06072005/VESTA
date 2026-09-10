import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
print(f"Loading {har_path}...")
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

entries = data['log']['entries']
print(f"Total entries: {len(entries)}")

interesting = []
for idx, entry in enumerate(entries):
    req = entry['request']
    url = req['url']
    resp = entry['response']
    status = resp.get('status', 0)
    mime = resp.get('content', {}).get('mimeType', '')
    text = resp.get('content', {}).get('text', '')
    
    if status == 200 and text and ('query' in url or 'xhr' in url or 'news' in url or 'notification' in url):
        if 'json' in mime or text.strip().startswith('{') or text.strip().startswith('['):
            try:
                js = json.loads(text)
                interesting.append((idx, req, resp, js))
            except Exception:
                pass

print(f"Found {len(interesting)} interesting JSON responses:\n")
for idx, req, resp, js in interesting:
    url = req['url']
    method = req['method']
    headers = {h['name']: h['value'] for h in req.get('headers', [])}
    cookies = {c['name']: c['value'] for c in req.get('cookies', [])}
    
    print(f"--- Entry #{idx} ---")
    print(f"URL: {method} {url}")
    print(f"Headers count: {len(headers)}, Cookies count: {len(cookies)}")
    if isinstance(js, dict):
        print(f"Root keys: {list(js.keys())}")
        # Look for news-like structures
        for k in ['data', 'finance', 'items', 'notificationsWithMeta', 'stream', 'articles', 'news', 'result', 'body']:
            if k in js:
                val = js[k]
                if isinstance(val, list):
                    print(f"  Field '{k}' has list of {len(val)} items. First item preview: {str(val[0])[:200]}")
                elif isinstance(val, dict):
                    print(f"  Field '{k}' has dict with keys: {list(val.keys())[:10]}")
    elif isinstance(js, list):
        print(f"Root is list of {len(js)} items.")
        if len(js) > 0:
            print(f"  First item preview: {str(js[0])[:200]}")
    print()
