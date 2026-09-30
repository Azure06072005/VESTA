import urllib.request
import json
import time

results = {}

# 1. Vietcap Screener Direct
t0 = time.time()
url_vci = 'https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging'
headers_vci = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Referer': 'https://trading.vietcap.com.vn/',
    'Origin': 'https://trading.vietcap.com.vn',
}
payload_vci = {
    'page': 0,
    'pageSize': 10,
    'sortFields': [],
    'sortOrders': [],
    'filter': [
        {'name': 'exchange', 'conditionOptions': [{'type': 'value', 'value': 'hsx'}, {'type': 'value', 'value': 'hnx'}, {'type': 'value', 'value': 'upcom'}]}
    ]
}
req = urllib.request.Request(url_vci, data=json.dumps(payload_vci).encode('utf-8'), headers=headers_vci, method='POST')
with urllib.request.urlopen(req, timeout=10) as r:
    data_vci = json.loads(r.read())
el_vci = time.time() - t0
content_vci = data_vci.get('data', {}).get('content', [])
results['vietcap_screener'] = {
    'status': 'OK',
    'elapsed': round(el_vci, 3),
    'totalElements': data_vci.get('data', {}).get('totalElements'),
    'sample_columns': list(content_vci[0].keys()) if content_vci else [],
    'sample_row': content_vci[0] if content_vci else {}
}

# 2. VNDIRECT Top Stocks Direct
t0 = time.time()
url_vnd_gainer = 'https://api-finfo.vndirect.com.vn/v4/top_stocks?q=index:VNIndex~nmVolumeAvgCr20D:gte:10000~priceChgPctCr1D:gt:0&size=5&sort=priceChgPctCr1D'
headers_vnd = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
req = urllib.request.Request(url_vnd_gainer, headers=headers_vnd, method='GET')
with urllib.request.urlopen(req, timeout=10) as r:
    data_vnd = json.loads(r.read())
el_vnd = time.time() - t0
items_vnd = data_vnd.get('data', [])
results['vnd_gainers'] = {
    'status': 'OK',
    'elapsed': round(el_vnd, 3),
    'count': len(items_vnd),
    'sample_columns': list(items_vnd[0].keys()) if items_vnd else [],
    'sample_top': items_vnd[:2] if items_vnd else []
}

# 3. AseanSC Market Breadth Direct
t0 = time.time()
url_asean_breadth = 'https://asean-apigw.aseansc.com.vn/pbapi/api/mktBreadth?indexCode=HOSE'
headers_asean = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://research.aseansc.com.vn',
    'Referer': 'https://research.aseansc.com.vn/',
}
req = urllib.request.Request(url_asean_breadth, headers=headers_asean, method='GET')
with urllib.request.urlopen(req, timeout=10) as r:
    data_asean = json.loads(r.read())
el_asean = time.time() - t0
items_asean = data_asean.get('data', [])
results['asean_breadth'] = {
    'status': 'OK',
    'elapsed': round(el_asean, 3),
    'total_days': len(items_asean),
    'sample_columns': list(items_asean[0].keys()) if items_asean else [],
    'latest_day': items_asean[-1] if items_asean else {}
}

# 4. AseanSC Fear & Greed Direct
t0 = time.time()
url_asean_fg = 'https://asean-apigw.aseansc.com.vn/pbapi/api/aseanfeargreed?indexCode=HOSE'
req = urllib.request.Request(url_asean_fg, headers=headers_asean, method='GET')
with urllib.request.urlopen(req, timeout=10) as r:
    data_fg = json.loads(r.read())
el_fg = time.time() - t0
items_fg = data_fg.get('data', [])
results['asean_fear_greed'] = {
    'status': 'OK',
    'elapsed': round(el_fg, 3),
    'sample_data': items_fg[-1] if items_fg else {}
}

# 5. AseanSC Macro GDP Direct
t0 = time.time()
url_gdp = 'https://asean-apigw.aseansc.com.vn/pbapi/api/macro/gdp?startDate=01-01-2020&endDate=01-01-2026&period=Q'
req = urllib.request.Request(url_gdp, headers=headers_asean, method='GET')
with urllib.request.urlopen(req, timeout=10) as r:
    data_gdp = json.loads(r.read())
el_gdp = time.time() - t0
items_gdp = data_gdp.get('data', [])
results['asean_macro_gdp'] = {
    'status': 'OK',
    'elapsed': round(el_gdp, 3),
    'quarters_count': len(items_gdp),
    'sample_data': items_gdp[-1] if items_gdp else {}
}

# 6. AseanSC Macro Interbank Rate Direct
t0 = time.time()
url_interbank = 'https://asean-apigw.aseansc.com.vn/pbapi/api/macro/interbank?startDate=01-01-2024&endDate=01-01-2026&interestperiod=ON'
req = urllib.request.Request(url_interbank, headers=headers_asean, method='GET')
with urllib.request.urlopen(req, timeout=10) as r:
    data_ib = json.loads(r.read())
el_ib = time.time() - t0
items_ib = data_ib.get('data', [])
results['asean_interbank'] = {
    'status': 'OK',
    'elapsed': round(el_ib, 3),
    'points_count': len(items_ib),
    'sample_data': items_ib[-1] if items_ib else {}
}

print(json.dumps(results, indent=2, ensure_ascii=False))
