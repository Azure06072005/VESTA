import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for name, url in [
    ('CDKT', 'https://apiweb.cafef.vn/api/v2/BCTC/GetReportCDKT?symbol=HPG&pageIndex=1&pageSize=4&reportType=ALL&TypeTime=QUY'),
    ('KQKD', 'https://apiweb.cafef.vn/api/v1/BCTC/GetReportDetail?symbol=HPG&pageIndex=1&pageSize=4&reportType=KQKD&TypeTime=QUY'),
    ('LCTT', 'https://apiweb.cafef.vn/api/v1/BCTC/GetReportLCTT?symbol=HPG&pageIndex=1&pageSize=4&reportType=ALL&TypeTime=QUY'),
    ('RATIO', 'https://apiweb.cafef.vn/api/v2/BCTC/FinancialIndicators?symbol=HPG&pageIndex=1&pageSize=4'),
]:
    r = requests.get(url, headers=headers, timeout=10)
    val = r.json().get('value', {})
    print(f"\n=== {name} ===")
    print("Keys:", list(val.keys()))
    d = val.get('data', [])
    print("Data count:", len(d))
    if d and isinstance(d[0], dict):
        print("Item 0 keys:", list(d[0].keys()))
        if 'time' in d[0]:
            print("Times:", [item.get('time') for item in d if isinstance(item, dict)])
