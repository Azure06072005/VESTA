import requests
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

target_indices = [
    # Nhóm quy mô vốn hóa
    'VN30', 'VN100', 'VNMID', 'VNSML', 'VNALL', 'VNX50', 'VNXALL',
    # Nhóm room ngoại & đầu tư
    'VNDIAMOND', 'VNFINLEAD', 'VNFINSELECT', 'VNSI', 'VNDIVIDEND', 'VN50GROWTH',
    # Nhóm ngành ICB
    'VNFIN', 'VNREAL', 'VNMAT', 'VNIND', 'VNCONS', 'VNCOND', 'VNHEAL', 'VNENE', 'VNUTI', 'VNIT', 'VNMITECH'
]

now_ts = int(time.time())
from_ts = int(now_ts - 365 * 5 * 86400) # 5 năm gần nhất

print(f"=== KIỂM TRA CÁC NGUỒN CUNG CẤP DỮ LIỆU CHỈ SỐ NHÓM (GROUP ROOMS) ===")

# 1. Thử nguồn VNDIRECT DChart API
print("\n--- 1. Thử VNDIRECT DChart API ---")
vnd_base = "https://dchart-api.vndirect.com.vn/dchart/history"
for sym in ['VN30', 'VN100', 'VNMID', 'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'VNREAL', 'VNFIN']:
    url = f"{vnd_base}?resolution=D&symbol={sym}&from={from_ts}&to={now_ts}"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            bars = len(data.get('t', []))
            print(f"  VNDirect [{sym}]: OK -> {bars} phiên")
        else:
            print(f"  VNDirect [{sym}]: HTTP {r.status_code}")
    except Exception as e:
        print(f"  VNDirect [{sym}]: Lỗi {e}")

# 2. Thử nguồn SSI iBoard DChart API
print("\n--- 2. Thử SSI iBoard DChart API ---")
ssi_base = "https://iboard.ssi.com.vn/dchart/api/history"
ssi_headers = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://iboard.ssi.com.vn",
    "Referer": "https://iboard.ssi.com.vn/"
}
for sym in ['VN30', 'VN100', 'VNMID', 'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'VNREAL', 'VNFIN']:
    url = f"{ssi_base}?resolution=D&symbol={sym}&from={from_ts}&to={now_ts}"
    try:
        r = requests.get(url, headers=ssi_headers, timeout=5)
        if r.status_code == 200:
            try:
                data = r.json()
                bars = len(data.get('t', []))
                print(f"  SSI [{sym}]: OK -> {bars} phiên")
            except Exception:
                print(f"  SSI [{sym}]: Trả về non-JSON")
        else:
            print(f"  SSI [{sym}]: HTTP {r.status_code}")
    except Exception as e:
        print(f"  SSI [{sym}]: Lỗi {e}")

# 3. Thử nguồn TCBS / TCinvest
print("\n--- 3. Thử TCBS API ---")
# TCBS endpoint: https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?ticker=VN30&type=index&count=1000
tcbs_base = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
for sym in ['VN30', 'VN100', 'VNMID', 'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'VNREAL', 'VNFIN']:
    url = f"{tcbs_base}?ticker={sym}&type=index&count=1000"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            data_list = data.get('data', [])
            print(f"  TCBS [{sym}]: OK -> {len(data_list)} phiên")
        else:
            print(f"  TCBS [{sym}]: HTTP {r.status_code}")
    except Exception as e:
        print(f"  TCBS [{sym}]: Lỗi {e}")

# 4. Thử nguồn DNSE Chart API
print("\n--- 4. Thử DNSE Chart API ---")
dnse_base = "https://services.entrade.com.vn/chart-api/v2/ohlcs"
# DNSE params: symbol=VN30&from=...&to=...&resolution=1D
for sym in ['VN30', 'VN100', 'VNMID', 'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'VNREAL', 'VNFIN']:
    url = f"{dnse_base}/index?symbol={sym}&from={from_ts}&to={now_ts}&resolution=1D"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            bars = len(data.get('t', []))
            print(f"  DNSE [{sym}]: OK -> {bars} phiên")
        else:
            # Thử không có /index
            url2 = f"{dnse_base}/stock?symbol={sym}&from={from_ts}&to={now_ts}&resolution=1D"
            r2 = requests.get(url2, headers=headers, timeout=5)
            if r2.status_code == 200:
                data2 = r2.json()
                print(f"  DNSE stock [{sym}]: OK -> {len(data2.get('t', []))} phiên")
            else:
                print(f"  DNSE [{sym}]: HTTP {r.status_code} / {r2.status_code}")
    except Exception as e:
        print(f"  DNSE [{sym}]: Lỗi {e}")

# 5. Thử nguồn Vietstock
print("\n--- 5. Thử Vietstock Index API ---")
# Vietstock: finance.vietstock.vn
