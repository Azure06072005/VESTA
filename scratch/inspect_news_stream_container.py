import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for e in data['log']['entries']:
    url = e['request']['url']
    if 'NewsStreamContainer' in url:
        print(f"Found NewsStreamContainer: {url}")
        text = e['response'].get('content', {}).get('text', '')
        print(f"Content length: {len(text)}")
        # Search for API urls, fetch, axios, endpoints, xhr
        endpoints = re.findall(r'["\'](/xhr/[^"\']+|https://[^"\']+|/ws/[^"\']+|/v\d+/[^"\']+)["\']', text)
        print("Discovered endpoints in NewsStreamContainer:")
        for ep in set(endpoints):
            print("  *", ep)
        
        # Search for stream or pagination keywords
        keywords = re.findall(r'(\b[a-zA-Z0-9_]+Stream[a-zA-Z0-9_]*|\b[a-zA-Z0-9_]*pagination[a-zA-Z0-9_]*|\b[a-zA-Z0-9_]*Articles[a-zA-Z0-9_]*|\blistId\b|\bstreamId\b)', text, re.IGNORECASE)
        print("\nKeywords in chunk:")
        print("  ", list(set(keywords))[:20])
