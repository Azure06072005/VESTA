import urllib.request
import json

test_symbols = ['VNINDEX', 'VCB', 'FPT', 'VN30F1M', 'E1VFVN30']
for sym in test_symbols:
    for tf in ['1D', '1m', '5m', '1h', '1y', '5y']:
        url = f"http://127.0.0.1:8899/api/ohlcv/{sym}?timeframe={tf}&limit=5"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as res:
                d = json.loads(res.read().decode('utf-8'))
                bars = d.get('bars', [])
                print(f"{sym} ({tf}): count={len(bars)}, source={d.get('source')}")
                if bars:
                    print(f"   first bar: {bars[0]}")
                    print(f"   last bar:  {bars[-1]}")
        except Exception as e:
            print(f"ERROR {sym} ({tf}): {e}")
