import json
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

topic_query = None
leaf_query = None
graphql_headers = None

for e in data['log']['entries']:
    pd = e['request'].get('postData', {}).get('text', '')
    if pd and pd.strip().startswith('{'):
        try:
            js = json.loads(pd)
            op = js.get('operationName')
            if op == 'GetFinanceTopicStream' and not topic_query:
                topic_query = js['query']
                graphql_headers = {h['name']: h['value'] for h in e['request']['headers'] if not h['name'].startswith(':')}
            elif op == 'GetQSPLeafNewsStream' and not leaf_query:
                leaf_query = js['query']
        except Exception:
            pass

print("Found topic_query:", bool(topic_query))
print("Found leaf_query:", bool(leaf_query))

# Test topic_query
url = "https://nexus-gateway-prod.media.yahoo.com/"
r1 = requests.post(url, headers=graphql_headers, json={
    "operationName": "GetFinanceTopicStream",
    "query": topic_query,
    "variables": {
        "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
        "count": 25,
        "start": 0,
        "listInput": {"uuid": "db1d46e0-a969-11e9-bff5-6dfdb80d79cf"},
        "imageResize": []
    }
}, timeout=10)
print(f"Topic query status: {r1.status_code}")
if r1.status_code == 200:
    items = r1.json().get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
    print(f"Topic stream items: {len(items)}")

# Test leaf_query
r2 = requests.post(url, headers=graphql_headers, json={
    "operationName": "GetQSPLeafNewsStream",
    "query": leaf_query,
    "variables": {
        "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
        "count": 25,
        "start": 0,
        "listInput": {
            "assetTypes": ["story", "video"],
            "disableDedupe": False,
            "enableBlockedContent": False,
            "filterClientContext": False,
            "queryVariables": {"tickerSymbol": ["^GSPC", "^DJI", "CL=F", "GC=F"]},
            "slug": "list=finance-US-en-US-ticker-all"
        },
        "imageResize": []
    }
}, timeout=10)
print(f"Leaf query status: {r2.status_code}")
if r2.status_code == 200:
    items2 = r2.json().get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
    print(f"Leaf stream items: {len(items2)}")

# Save queries to files
with open('d:/VESTA/src/crawlers/get_finance_topic_stream.graphql', 'w', encoding='utf-8') as f:
    f.write(topic_query)
with open('d:/VESTA/src/crawlers/get_qsp_leaf_news_stream.graphql', 'w', encoding='utf-8') as f:
    f.write(leaf_query)
print("Saved both .graphql query files successfully!")
