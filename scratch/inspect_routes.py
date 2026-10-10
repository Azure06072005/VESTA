import re

with open('src/service/console_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

routes = re.findall(r'@app\.(get|post|put|delete)\([\'\"]([^\'\"]+)', content)
print(f"Total routes found: {len(routes)}")
for m, r in routes:
    if any(k in r.lower() for k in ['ohlcv', 'candlestick', 'symbol', 'dashboard']):
        print(f"{m.upper()}: {r}")
