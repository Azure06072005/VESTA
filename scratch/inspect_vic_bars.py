import urllib.request
import json

url = 'http://127.0.0.1:8899/api/ohlcv/VIC?timeframe=1d&limit=300'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as res:
    d = json.loads(res.read().decode('utf-8'))
    bars = d.get('bars', [])
    print(f"Total bars: {len(bars)}, source: {d.get('source')}")
    print("First 5 bars:")
    for b in bars[:5]:
        print("  ", b)
    print("Last 10 bars:")
    for b in bars[-10:]:
        print("  ", b)

    # Check price scale changes!
    opens = [b['open'] for b in bars]
    print(f"Min open: {min(opens)}, Max open: {max(opens)}")
    for i in range(1, len(bars)):
        prev = bars[i-1]['close']
        curr = bars[i]['close']
        if prev > 0 and (curr / prev > 5 or curr / prev < 0.2):
            print(f"Huge jump between {bars[i-1]['time']} (close={prev}) and {bars[i]['time']} (close={curr})!")
