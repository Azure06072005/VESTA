import json
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for GetFinanceTopicStream query in the HAR files
har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

topic_query = None
topic_headers = None
for e in data['log']['entries']:
    post_data = e['request'].get('postData', {}).get('text', '')
    if 'GetFinanceTopicStream' in post_data:
        js = json.loads(post_data)
        topic_query = js['query']
        topic_headers = {h['name']: h['value'] for h in e['request']['headers'] if not h['name'].startswith(':')}
        break

if not topic_query:
    print("GetFinanceTopicStream query not found in News.har, checking other HARs...")
    for hname in ['finance.yahoo.com-markets.har', 'finance.yahoo.com-main_page.har']:
        with open(f'd:/VESTA/scratch/har/yahoo_finance/{hname}', 'r', encoding='utf-8', errors='ignore') as f:
            d2 = json.load(f)
        for e in d2['log']['entries']:
            pd = e['request'].get('postData', {}).get('text', '')
            if 'GetFinanceTopicStream' in pd:
                js = json.loads(pd)
                topic_query = js['query']
                topic_headers = {h['name']: h['value'] for h in e['request']['headers'] if not h['name'].startswith(':')}
                print(f"Found in {hname}!")
                break
        if topic_query:
            break

print("Topic query found:", bool(topic_query))
if topic_query:
    print("Query preview:\n", topic_query[:250])
    
    # Test calling with listId db1d46e0-a969-11e9-bff5-6dfdb80d79cf (stock-market-news)
    url = "https://nexus-gateway-prod.media.yahoo.com/"
    for start in [0, 25, 50, 100, 200]:
        payload = {
            "operationName": "GetFinanceTopicStream",
            "query": topic_query,
            "variables": {
                "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
                "count": 25,
                "start": start,
                "listInput": {"uuid": "db1d46e0-a969-11e9-bff5-6dfdb80d79cf"},
                "imageResize": []
            }
        }
        r = requests.post(url, headers=topic_headers, json=payload, timeout=10)
        print(f"Topic Stream start={start} -> Status {r.status_code}")
        if r.status_code == 200:
            res = r.json()
            stream = res.get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
            print(f"  Items: {len(stream)}")
            if stream:
                d0 = stream[0].get('asset', {}).get('contentAttributes', {}).get('pubDate')
                d_last = stream[-1].get('asset', {}).get('contentAttributes', {}).get('pubDate')
                t0 = stream[0].get('asset', {}).get('title')
                print(f"  Span: {d0} -> {d_last} | Sample: {t0[:60]}")
