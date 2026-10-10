import urllib.request
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

endpoints = [
    '/health',
    '/api/status',
    '/api/dashboard/overview',
    '/api/dashboard/heatmap?limit=5',
    '/api/dashboard/foreign_flow?limit=5',
    '/api/dashboard/multi_asset',
    '/api/dashboard/events?limit=5',
    '/api/dashboard/news?page=1&limit=3',
    '/api/ohlcv/VNINDEX?timeframe=1d&limit=3',
    '/api/ohlcv/VN30F1M?timeframe=1d&limit=3',
    '/api/ohlcv/E1VFVN30?timeframe=1d&limit=3',
    '/api/symbol/FPT/detail?news_page=1&news_limit=3&ohlcv_limit=3'
]

for ep in endpoints:
    url = f"http://127.0.0.1:8899{ep}"
    try:
        res = urllib.request.urlopen(url)
        d = json.loads(res.read().decode('utf-8'))
        print(f"=== {ep} [200 OK] ===")
        if ep == '/api/dashboard/overview':
            print("  trading_date:", d.get("latest_trading_date"))
            print("  summary:", d.get("market_summary"))
            print("  indices count:", len(d.get("indices", [])))
        elif ep == '/api/dashboard/multi_asset':
            print("  derivatives count:", len(d.get("derivatives", [])))
            print("  first deriv:", d.get("derivatives", [])[0] if d.get("derivatives") else "none")
            print("  etfs count:", len(d.get("etfs", [])))
            print("  first etf:", d.get("etfs", [])[0] if d.get("etfs") else "none")
            print("  CWs count:", len(d.get("covered_warrants", [])))
        elif ep.startswith('/api/dashboard/foreign_flow'):
            print("  count:", d.get("count"))
            print("  latest row:", d.get("data", [])[-1] if d.get("data") else "none")
        elif ep.startswith('/api/dashboard/heatmap'):
            print("  count:", d.get("count"), "date:", d.get("date"))
            print("  first item:", d.get("data", [])[0] if d.get("data") else "none")
        elif ep.startswith('/api/ohlcv/'):
            print("  count:", d.get("count"), "source:", d.get("source"), "latest bar:", d.get("bars", [])[-1] if d.get("bars") else "none")
        elif ep.startswith('/api/symbol/'):
            print("  symbol:", d.get("symbol"))
            print("  price:", d.get("ohlcv", {}).get("metrics", {}).get("current_price"))
            print("  company:", d.get("overview", {}).get("company_name"))
        else:
            print("  response keys:", list(d.keys()) if isinstance(d, dict) else len(d))
    except Exception as e:
        print(f"=== {ep} [ERROR]: {e} ===")
