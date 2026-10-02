import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}

# Thêm filters bao gồm cả các điều kiện để API include các trường kỹ thuật và cơ bản
payload = {
    "page": 0,
    "pageSize": 5,
    "sortFields": ["marketCap"],
    "sortOrders": ["DESC"],
    "filter": [
        {"name": "exchange", "conditionOptions": [{"type": "value", "value": "hsx"}, {"type": "value", "value": "hnx"}, {"type": "value", "value": "upcom"}]},
        {"name": "ttmPe", "conditionOptions": [{"type": "range", "min": 0, "max": 999}]},
        {"name": "ttmPb", "conditionOptions": [{"type": "range", "min": 0, "max": 999}]},
        {"name": "ttmRoe", "conditionOptions": [{"type": "range", "min": -100, "max": 999}]},
        {"name": "rsi", "conditionOptions": [{"type": "range", "min": 0, "max": 100}]},
    ]
}

req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")

with urllib.request.urlopen(req, timeout=12) as resp:
    data = json.loads(resp.read().decode('utf-8'))

content = data.get("data", {}).get("content", [])
print(f"Nhận được {len(content)} items với deep filter!")
if content:
    print("Danh sách keys của item đầu tiên:")
    print(list(content[0].keys()))
    print("\nMẫu giá trị:")
    item0 = content[0]
    for k in ['ticker', 'exchange', 'marketPrice', 'ttmPe', 'ttmPb', 'ttmRoe', 'rsi', 'macd', 'grossMargin', 'netMargin']:
        print(f"  {k}: {item0.get(k)}")
