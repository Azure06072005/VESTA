import json
from urllib.parse import urlparse
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

print('Inspecting News HAR entries...')
seen = set()
for entry in data['log']['entries']:
    url = entry['request']['url']
    if any(k in url.lower() for k in ['notification', 'news', 'article', 'feed', 'stream', 'content', 'story', 'quote']):
        if not any(t in url for t in ['y-adp', 'gemini', 'pixel', 'ad', 'analytics', 'telemetry', 'beacon']):
            parsed = urlparse(url)
            endpoint = f"{entry['request']['method']} {parsed.netloc}{parsed.path}"
            if endpoint not in seen:
                seen.add(endpoint)
                print(f"\n{endpoint}?{parsed.query[:80]}")
                resp = entry['response'].get('content', {})
                text = resp.get('text', '')
                if text and len(text) > 50:
                    print('   Status:', entry['response']['status'], 'Content size:', len(text))
                    print('   Sample:', text[:250].replace('\n', ' '))
