import json
import glob
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

for har in glob.glob('d:/VESTA/scratch/har/yahoo_finance/*.har'):
    with open(har, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
    for e in data['log']['entries']:
        u = e['request']['url']
        if 'NewsStream.' in u:
            print(f"Found {u} in {har}")
            txt = e['response'].get('content', {}).get('text', '')
            print("Length:", len(txt))
            # Find fetch calls or endpoint strings
            endpoints = re.findall(r'["\'](/xhr/[^"\']+|https?://[^"\']+|/ws/[^"\']+|/v\d+/[^"\']+)["\']', txt)
            for ep in set(endpoints):
                if not any(k in ep for k in ['w3.org', 'schema.org', '.css', '.js']):
                    print("  Endpoint:", ep)
            # Find loadMore / pagination logic
            func_matches = re.findall(r'(?:loadMore|fetchStream|getMore|paginate)[a-zA-Z0-9_]*', txt, re.IGNORECASE)
            print("  Functions:", set(func_matches))
            # Print snippet around loadMore or listId
            for match in re.finditer(r'(?:loadMoreParams|listId|offset|fetch\()', txt):
                start = max(0, match.start() - 100)
                end = min(len(txt), match.end() + 200)
                print("  --- Context snippet ---")
                print(txt[start:end])
                break
