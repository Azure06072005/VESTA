import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('d:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for e in data['log']['entries']:
    if 'loadNewsStream' in e['request']['url']:
        txt = e['response'].get('content', {}).get('text', '')
        print("=== loadNewsStream.js Content ===")
        print(txt)
