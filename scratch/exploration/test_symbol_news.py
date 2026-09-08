import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'd:/VESTA')

from src.crawlers.yahoo_all_dates_crawler import LEAF_QUERY, GRAPHQL_HEADERS, GRAPHQL_URL

symbols_to_test = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    "BRK-B", "JNJ", "V", "WMT", "JPM", "PG", "UNH", "XOM",
    "^GSPC", "^DJI", "^IXIC", "CL=F", "GC=F", "VNM"
]

print("=== Testing Company Symbols News Stream Depth ===")
for sym in symbols_to_test[:5]:
    payload = {
        "operationName": "GetQSPLeafNewsStream",
        "query": LEAF_QUERY,
        "variables": {
            "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
            "count": 50,
            "start": 0,
            "listInput": {
                "assetTypes": ["story", "video"],
                "disableDedupe": False,
                "enableBlockedContent": False,
                "filterClientContext": False,
                "queryVariables": {"tickerSymbol": [sym]},
                "slug": "list=finance-US-en-US-ticker-all"
            },
            "imageResize": []
        }
    }
    r = requests.post(GRAPHQL_URL, headers=GRAPHQL_HEADERS, json=payload, timeout=10)
    if r.status_code == 200:
        stream = r.json().get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
        print(f"Symbol {sym:<6} -> {len(stream)} articles returned.")
        if stream:
            d_first = stream[0].get('asset', {}).get('contentAttributes', {}).get('pubDate')
            d_last = stream[-1].get('asset', {}).get('contentAttributes', {}).get('pubDate')
            print(f"   Date range: {d_first} -> {d_last}")
