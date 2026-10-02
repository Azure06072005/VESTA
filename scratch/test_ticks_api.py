import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Test CafeF ThongKeKhopLenh
url_cafef = "https://s.cafef.vn/Ajax/PageNew/DataHistory/ThongKeKhopLenh.ashx?Symbol=FPT&StartDate=&EndDate="
headers = {"User-Agent": "Mozilla/5.0"}
try:
    req = urllib.request.Request(url_cafef, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print("CafeF ThongKeKhopLenh success! Keys:", list(res.keys()) if isinstance(res, dict) else len(res))
        if isinstance(res, dict) and 'Data' in res:
            print("Số lượng rows:", len(res['Data']))
            print("Mẫu row:", res['Data'][0] if len(res['Data']) > 0 else "Empty")
except Exception as e:
    print("CafeF error:", e)

# Test TCBS intraday ticks
url_tcbs = "https://apipubaws.tcbs.com.vn/stock-insight/v1/intraday/FPT/his/paging?page=0&size=50"
try:
    req = urllib.request.Request(url_tcbs, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print("\nTCBS Intraday Ticks success!")
        print("Keys:", list(res.keys()) if isinstance(res, dict) else len(res))
        if isinstance(res, dict) and 'data' in res:
            print("Số lượng ticks TCBS:", len(res['data']))
            print("Mẫu 2 ticks:", res['data'][:2])
except Exception as e:
    print("TCBS error:", e)
