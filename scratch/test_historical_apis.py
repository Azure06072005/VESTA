import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Test Vietcap IQ Screener with historical date
url_vci = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging"
headers_vci = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}

payload_test = {
    "page": 0,
    "pageSize": 5,
    "filter": [
        {"name": "exchange", "conditionOptions": [{"type": "value", "value": "hsx"}]},
        {"name": "tradingDate", "conditionOptions": [{"type": "value", "value": "2024-01-02"}]}
    ]
}

try:
    req = urllib.request.Request(url_vci, data=json.dumps(payload_test).encode('utf-8'), headers=headers_vci, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print("Vietcap date test response total:", res.get("data", {}).get("totalElements"))
except Exception as e:
    print("Vietcap date test error:", e)

# 2. Test VNDIRECT FINFO Ratios with historical date
url_vnd = "https://api-finfo.vndirect.com.vn/v4/ratios?q=code:FPT~reportDate:gte:2020-01-01&size=5"
headers_vnd = {"User-Agent": "Mozilla/5.0"}
try:
    req2 = urllib.request.Request(url_vnd, headers=headers_vnd)
    with urllib.request.urlopen(req2, timeout=10) as resp:
        res2 = json.loads(resp.read().decode('utf-8'))
        print("\nVNDIRECT FINFO Ratios history response:")
        print("Keys:", list(res2.keys()) if isinstance(res2, dict) else len(res2))
        if isinstance(res2, dict) and 'data' in res2:
            print("Số lượng rows lịch sử VNDIRECT:", len(res2['data']))
            print("Mẫu row:", res2['data'][0] if res2['data'] else "Empty")
except Exception as e:
    print("VNDIRECT error:", e)
