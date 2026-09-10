import json
import requests
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

with open('d:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

# Find topic query and headers
topic_query = None
topic_headers = None
for e in data['log']['entries']:
    pd = e['request'].get('postData', {}).get('text', '')
    if 'GetFinanceTopicStream' in pd:
        js = json.loads(pd)
        topic_query = js['query']
        topic_headers = {h['name']: h['value'] for h in e['request']['headers'] if not h['name'].startswith(':')}
        break

topics_to_test = [
    ("stock-market-news", "db1d46e0-a969-11e9-bff5-6dfdb80d79cf"),
    ("economic-news", "7ce2bfb8-c363-4498-930b-b6d86ae4dccf"),
    ("latest-news", "530aec16-61ed-4c8e-8fd8-f60d01bd0722"),
    ("tech", "dffbd430-02a2-11e7-bcfc-437e9432ca73"),
    ("earnings", "04d9350a-bbd1-4787-95be-740cc5ee8852"),
    ("ai", "b9b66d9c-c3ac-473a-98f2-59a2ab749b60"),
    ("businesswire", "61f79c40-2f61-11e7-aaf7-a51cd0c0a187")
]

all_articles = {}
url = "https://nexus-gateway-prod.media.yahoo.com/"

for tname, tuuid in topics_to_test:
    print(f"\n--- Crawling Topic: {tname} ({tuuid}) ---")
    topic_count = 0
    for start in [0, 25, 50, 75, 100]:
        payload = {
            "operationName": "GetFinanceTopicStream",
            "query": topic_query,
            "variables": {
                "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
                "count": 25,
                "start": start,
                "listInput": {"uuid": tuuid},
                "imageResize": []
            }
        }
        try:
            r = requests.post(url, headers=topic_headers, json=payload, timeout=10)
            if r.status_code == 200:
                res = r.json()
                stream = res.get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
                if not stream:
                    print(f"  start={start}: no more items.")
                    break
                topic_count += len(stream)
                for item in stream:
                    asset = item.get('asset', {})
                    aid = asset.get('id')
                    attrs = asset.get('contentAttributes', {})
                    art_url = attrs.get('canonicalUrl') or attrs.get('clickthroughUrl')
                    title = asset.get('title')
                    pub_date = attrs.get('pubDate')
                    if art_url and title:
                        all_articles[art_url] = {
                            "id": aid,
                            "title": title,
                            "pub_date": pub_date,
                            "summary": attrs.get('summary') or "",
                            "provider": (attrs.get('provider') or {}).get('displayName') or "Yahoo Finance"
                        }
            else:
                print(f"  start={start}: status {r.status_code}")
                break
        except Exception as e:
            print(f"  start={start}: error {e}")
            break
    print(f"  Topic {tname} total raw items fetched: {topic_count}")

print(f"\n==================================================")
print(f"TOTAL UNIQUE ARTICLES COLLECTED ACROSS TEST TOPICS: {len(all_articles)}")
dates = [a['pub_date'] for a in all_articles.values() if a.get('pub_date')]
if dates:
    print(f"Earliest article date: {min(dates)}")
    print(f"Latest article date:   {max(dates)}")
