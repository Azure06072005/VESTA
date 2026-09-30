"""scratch/test_f007_sources_deep.py

Test live data extraction and compare data availability for F007 across:
1. vnstock underlying sources (Vietcap, KBS, AseanSC, VNDirect)
2. CafeF
3. Vietstock
"""
import json
import urllib.request
import urllib.parse
import time

def test_url(name, url, method="GET", data=None, headers=None):
    print(f"\n--- Testing: {name} ---")
    print(f"URL: {url} [{method}]")
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
    req = urllib.request.Request(url, headers=headers, method=method)
    encoded_data = None
    if data:
        if isinstance(data, dict):
            encoded_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, str):
            encoded_data = data.encode("utf-8")
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, data=encoded_data, timeout=10) as resp:
            elapsed = time.time() - t0
            raw = resp.read()
            print(f"Status: {resp.status} (in {elapsed:.2f}s) | Raw bytes: {len(raw)}")
            try:
                parsed = json.loads(raw.decode("utf-8", errors="ignore"))
                if isinstance(parsed, list):
                    print(f"JSON Array: {len(parsed)} items")
                    if len(parsed) > 0:
                        sample = parsed[0]
                        if isinstance(sample, dict):
                            print(f"Sample keys: {list(sample.keys())[:10]}")
                            print(f"Sample item: {json.dumps(sample, ensure_ascii=False)[:200]}")
                elif isinstance(parsed, dict):
                    print(f"JSON Object keys: {list(parsed.keys())[:10]}")
                    print(f"Sample snippet: {json.dumps(parsed, ensure_ascii=False)[:250]}")
                return True, parsed
            except Exception as e:
                print(f"Not JSON or parse error: {e}")
                print(f"Text snippet: {raw[:200].decode('utf-8', errors='ignore')}")
                return True, raw
    except Exception as e:
        print(f"FAILED: {e}")
        return False, str(e)

# 1. vnstock underlying sources
# 1.1 Vietcap (VCI) Price Board
test_url(
    "Vietcap (VCI) Price Board (vnstock source)",
    "https://trading.vietcap.com.vn/api/price/symbols/getList",
    method="POST",
    data={"symbols": ["FPT", "VNM", "HPG", "TCB", "SSI"]},
    headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
)

# 1.2 KB Securities (KBS) Price Board
test_url(
    "KB Securities (KBS) Price Board (vnstock source)",
    "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/iss",
    method="POST",
    data={"stockList": "FPT,VNM,HPG"},
    headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
)

# 1.3 VNDirect Market / Top Stock
test_url(
    "VNDirect Top Stock Gainer (vnstock source)",
    "https://api-finfo.vndirect.com.vn/v4/top_stocks?q=index:VNINDEX~type:gainer&limit=10",
    method="GET"
)

# 1.4 AseanSC Market Breadth
test_url(
    "AseanSC Market Breadth (vnstock source)",
    "https://asean-apigw.aseansc.com.vn/pbapi/api/mktBreadth?exchange=HOSE",
    method="GET",
    headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://research.aseansc.com.vn",
        "Referer": "https://research.aseansc.com.vn/"
    }
)

# 2. CafeF Sources
# 2.1 CafeF RealTimeChartHeader
test_url(
    "CafeF RealTimeChartHeader",
    "https://msh-datacenter.cafef.vn/price/api/v1/CompanyCompac/RealTimeChartHeader?symbol=FPT",
    method="GET"
)

# 2.2 CafeF RealtimePricesHeader.ashx
test_url(
    "CafeF RealtimePricesHeader",
    "https://cafef.vn/du-lieu/Ajax/PageNew/RealtimePricesHeader.ashx?code=FPT",
    method="GET"
)

# 2.3 CafeF ChiSoTaiChinh (Valuation / PE / PB)
test_url(
    "CafeF ChiSoTaiChinh (PE, PB, Vốn Hóa, EPS)",
    "https://cafef.vn/du-lieu/Ajax/PageNew/ChiSoTaiChinh.ashx?code=FPT",
    method="GET"
)

# 2.4 CafeF Thong Ke Dat Lenh (Order stats)
test_url(
    "CafeF GetDataTKDL (Thong Ke Dat Lenh)",
    "https://cafef.vn/du-lieu/Ajax/PageNew/GetDataTKDL.ashx?code=FPT",
    method="GET"
)

# 3. Vietstock Sources
# 3.1 Vietstock GICS Sector Performance
test_url(
    "Vietstock GICS Sector Performance",
    "https://finance.vietstock.vn/Data/GetGICSPerformance",
    method="POST",
    data="",
    headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
)

# 3.2 Vietstock Stock Info Detail
test_url(
    "Vietstock GetStockInfoDetail",
    "https://finance.vietstock.vn/data/GetStockInfoDetail?code=FPT",
    method="GET"
)
