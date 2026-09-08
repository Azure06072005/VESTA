import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': 'application/graphql-response+json, application/graphql+json, application/json',
    'content-type': 'application/json',
    'origin': 'https://finance.yahoo.com',
    'referer': 'https://finance.yahoo.com/markets/world-indices/',
    'sec-ch-ua': '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0',
    'x-yahoo-cg-client-name': 'finance',
    'x-yahoo-cg-client-version': '0.1.14418.1788543794',
    'y-rid': '6bbjmtll9tl5q'
}

# Extract full query from Entry 355
with open('d:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

e355 = data['log']['entries'][355]
post_json = json.loads(e355['request']['postData']['text'])
query_str = post_json['query']

print("=== Testing Nexus Gateway GraphQL Pagination ===")

url = "https://nexus-gateway-prod.media.yahoo.com/"

for start in [0, 20, 50, 100, 200, 500]:
    payload = {
        "operationName": "GetQSPLeafNewsStream",
        "query": query_str,
        "variables": {
            "clientContext": {
                "device": "desktop",
                "lang": "en-US",
                "region": "US",
                "site": "finance"
            },
            "count": 20,
            "start": start,
            "listInput": {
                "assetTypes": ["story", "video"],
                "disableDedupe": False,
                "enableBlockedContent": False,
                "filterClientContext": False,
                "queryVariables": {
                    "tickerSymbol": ["^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX", "CL=F", "GC=F", "DX-Y.NYB"]
                },
                "slug": "list=finance-US-en-US-ticker-all"
            },
            "imageResize": []
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        print(f"start={start} -> Status: {resp.status_code}")
        if resp.status_code == 200:
            res_data = resp.json()
            stream = res_data.get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
            print(f"   Items returned: {len(stream)}")
            if stream:
                first_date = stream[0].get('asset', {}).get('contentAttributes', {}).get('pubDate')
                last_date = stream[-1].get('asset', {}).get('contentAttributes', {}).get('pubDate')
                first_title = stream[0].get('asset', {}).get('title')
                print(f"   Date span: {first_date} -> {last_date}")
                print(f"   First title: {first_title[:70]}...")
        else:
            print(f"   Error: {resp.text[:200]}")
    except Exception as e:
        print(f"start={start} -> Exception: {e}")
