import requests
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

# Test Commodities & Asian Indices
macro_candidates = [
    # Asian Indices
    ("^N225", "Nikkei 225"),
    ("^HSI", "Hang Seng Index"),
    ("000001.SS", "SSE Composite Index"),
    ("^KS11", "KOSPI Composite Index"),
    ("^TWII", "TSEC weighted index"),
    ("^STI", "Straits Times Index"),
    # Commodities & Agriculture
    ("KC=F", "Coffee 'C' Futures"),
    ("ZR=F", "Rough Rice Futures"),
    ("TIO=F", "Iron Ore 62% Fe CFR China"),
    ("HRC=F", "Steel HRC Futures"),
    ("ZC=F", "Corn Futures"),
    ("ZS=F", "Soybean Futures"),
    ("ZW=F", "Wheat Futures"),
    ("SB=F", "Sugar #11 Futures"),
    ("CT=F", "Cotton #2 Futures"),
]

# Test Mag7
mag7_symbols = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META"]

p1 = 946684800  # 2000-01-01
p2 = int(datetime.now().timestamp())

print("=== 1. Testing Macro Commodities & Asian Indices ===")
valid_macro = []
for sym, name in macro_candidates:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            res = r.json().get('chart', {}).get('result', [])
            if res:
                ts = res[0].get('timestamp', [])
                if ts:
                    d_start = datetime.fromtimestamp(ts[0]).date()
                    d_end = datetime.fromtimestamp(ts[-1]).date()
                    print(f"[OK] {sym:<10} ({name}): {len(ts):,} bars ({d_start} -> {d_end})")
                    valid_macro.append((sym, name))
                else:
                    print(f"[EMPTY] {sym:<10} ({name}): 0 bars")
            else:
                print(f"[NO RES] {sym:<10} ({name})")
        else:
            print(f"[ERR {r.status_code}] {sym:<10} ({name})")
    except Exception as e:
        print(f"[EXC] {sym}: {e}")

print("\n=== 2. Testing Magnificent 7 Tech Stocks ===")
valid_mag7 = []
for sym in mag7_symbols:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            res = r.json().get('chart', {}).get('result', [])
            if res:
                ts = res[0].get('timestamp', [])
                if ts:
                    d_start = datetime.fromtimestamp(ts[0]).date()
                    d_end = datetime.fromtimestamp(ts[-1]).date()
                    print(f"[OK] {sym:<10}: {len(ts):,} bars ({d_start} -> {d_end})")
                    valid_mag7.append(sym)
    except Exception as e:
        print(f"[EXC] {sym}: {e}")
