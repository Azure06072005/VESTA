import sys
sys.stdout.reconfigure(encoding='utf-8')
from vnstock_data import Market

mkt = Market()

# 1. Thử các mã chuẩn trên KBS / vnstock_data
kbs_codes = ['VNINDEX', 'VN30', 'HNXINDEX', 'HNX30', 'UPCOMINDEX', 'VN100']
print("=== Checking vnstock_data (KBS) ===")
for code in kbs_codes:
    try:
        df = mkt.index(code).ohlcv(start='2010-01-01', end='2026-09-28')
        print(f"[{code}] Total rows: {len(df)} | Start: {df['time'].iloc[0]} | End: {df['time'].iloc[-1]}")
    except Exception as e:
        print(f"[{code}] Failed: {e}")

# 2. Thử nguồn Vietcap qua REST API (hoặc chart OHLCV của Vietcap)
print("\n=== Checking Vietcap Index API ===")
import requests
import json

vietcap_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/"
}

# Thử truy vấn historical bars từ Vietcap cho VNDIAMOND, VNFINLEAD, VNMID, VNSML
test_indices = ['VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX', 'VN100', 'VNMID', 'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'VNSI']
# URL chart Vietcap: https://trading.vietcap.com.vn/api/chart/v2/history?symbol=VNINDEX&resolution=D&from=...&to=...
import time
now_ts = int(time.time())
from_ts = int(time.mktime(time.strptime("2015-01-01", "%Y-%m-%d")))

for sym in test_indices:
    # URL phổ biến của Chart Vietcap
    url = f"https://trading.vietcap.com.vn/api/chart/v2/history?symbol={sym}&resolution=D&from={from_ts}&to={now_ts}"
    try:
        r = requests.get(url, headers=vietcap_headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if 't' in data and len(data['t']) > 0:
                print(f"[Vietcap Chart] {sym}: OK! {len(data['t'])} bars. Latest timestamp: {data['t'][-1]}")
            else:
                print(f"[Vietcap Chart] {sym}: Empty bars response")
        else:
            print(f"[Vietcap Chart] {sym}: Status {r.status_code}")
    except Exception as e:
        print(f"[Vietcap Chart] {sym}: Error {e}")
