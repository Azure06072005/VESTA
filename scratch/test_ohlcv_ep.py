import urllib.request
import json

for sym in ['VNINDEX', 'VN30', 'FPT', 'VNM']:
    try:
        url = f"http://127.0.0.1:8899/api/ohlcv/{sym}?timeframe=1d&limit=5"
        res = urllib.request.urlopen(url)
        d = json.loads(res.read())
        print(f"=== OHLCV {sym} ===")
        print("source:", d.get("source"), "count:", d.get("count"))
        if d.get("bars"):
            print("latest bar:", d["bars"][-1])
    except Exception as e:
        print(f"=== OHLCV {sym} ERROR: {e} ===")
