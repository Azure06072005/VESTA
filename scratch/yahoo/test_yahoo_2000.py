import requests
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'd:/VESTA')

# 1. Test Chart API from year 2000 (timestamp for 2000-01-01 is 946684800)
p1_2000 = 946684800  # 2000-01-01
now_ts = int(datetime.now().timestamp())

print("=== 1. Testing Historical Market Data from 2000 ===")
chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?period1={p1_2000}&period2={now_ts}&interval=1d"
headers = {'User-Agent': 'Mozilla/5.0'}
r_chart = requests.get(chart_url, headers=headers)
print(f"^GSPC from 2000 -> Status: {r_chart.status_code}")
if r_chart.status_code == 200:
    data = r_chart.json()
    timestamps = data['chart']['result'][0].get('timestamp', [])
    print(f"  Total daily bars returned: {len(timestamps)}")
    if timestamps:
        t_first = datetime.fromtimestamp(timestamps[0])
        t_last = datetime.fromtimestamp(timestamps[-1])
        print(f"  First bar: {t_first} | Last bar: {t_last}")

# 2. Test News Search / Archive for older years (e.g. 2000, 2010, 2020)
print("\n=== 2. Testing News Archive by Year / Date ===")
queries = [
    "https://query1.finance.yahoo.com/v1/finance/search?q=Federal+Reserve&newsCount=50",
    "https://query1.finance.yahoo.com/v1/finance/search?q=market+crash+2008&newsCount=50",
    "https://query1.finance.yahoo.com/v1/finance/search?q=dotcom+2000&newsCount=50"
]

for q in queries:
    r = requests.get(q, headers=headers)
    print(f"Search status: {r.status_code}")
    if r.status_code == 200:
        news = r.json().get('news', [])
        print(f"  News items returned: {len(news)}")
        if news:
            dates = [n.get('providerPublishTime') for n in news if n.get('providerPublishTime')]
            if dates:
                print(f"  Min date: {datetime.fromtimestamp(min(dates))} | Max date: {datetime.fromtimestamp(max(dates))}")

# 3. Test GraphQL pagination limit on Topic Stream
print("\n=== 3. Testing GraphQL Topic Stream depth limits ===")
from src.crawlers.yahoo_all_dates_crawler import TOPIC_QUERY, GRAPHQL_HEADERS, GRAPHQL_URL

for start in [0, 50, 100, 150, 200, 250, 300, 500]:
    payload = {
        "operationName": "GetFinanceTopicStream",
        "query": TOPIC_QUERY,
        "variables": {
            "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
            "count": 50,
            "start": start,
            "listInput": {"uuid": "db1d46e0-a969-11e9-bff5-6dfdb80d79cf"},
            "imageResize": []
        }
    }
    r = requests.post(GRAPHQL_URL, headers=GRAPHQL_HEADERS, json=payload, timeout=10)
    if r.status_code == 200:
        stream = r.json().get('data', {}).get('lightyearList', {}).get('main', {}).get('stream', [])
        print(f"  start={start} -> stream items: {len(stream)}")
        if stream:
            last_date = stream[-1].get('asset', {}).get('contentAttributes', {}).get('pubDate')
            print(f"    last article date: {last_date}")
        else:
            print("    End of stream reached.")
            break
    else:
        print(f"  start={start} -> status {r.status_code}")
        break
