import duckdb
import requests

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

# 1. Kiểm tra các ETF mô phỏng chỉ số rổ room / ngành trong core.market_ohlcv_daily
etfs = ['FUEVFVND', 'FUESSVFL', 'E1VFVN30', 'FUEVN100', 'FUEMAV30', 'FUESSV30', 'FUEKIV30']
df_etf = con.execute(f"""
    SELECT symbol, min(date) as min_dt, max(date) as max_dt, count(*) as cnt 
    FROM core.market_ohlcv_daily 
    WHERE symbol IN ({','.join([repr(x) for x in etfs])})
    GROUP BY symbol
""").fetchdf()
print("=== ETFs in core.market_ohlcv_daily ===")
print(df_etf.to_string())

# 2. Kiểm tra SSI iBoard Index API cho VNDIAMOND, VNFINLEAD, VN100, VNMID, VNSML
print("\n=== Testing SSI iBoard Index API ===")
ssi_url = "https://iboard.ssi.com.vn/dchart/api/history?resolution=D&symbol=VNDIAMOND&from=1577836800&to=1790640000"
headers = {"User-Agent": "Mozilla/5.0"}
try:
    r = requests.get(ssi_url, headers=headers, timeout=5)
    print("SSI VNDIAMOND status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("SSI VNDIAMOND keys:", data.keys(), "num bars:", len(data.get('t', [])))
        if len(data.get('t', [])) > 0:
            print("Sample bar:", data['t'][-1], data['c'][-1])
except Exception as e:
    print("SSI error:", e)

# 3. Thử các mã khác trên SSI
for code in ['VNINDEX', 'VN30', 'HNXIndex', 'UpcomIndex', 'VN100', 'VNMID', 'VNSML', 'VNFINLEAD', 'VNSI']:
    try:
        url = f"https://iboard.ssi.com.vn/dchart/api/history?resolution=D&symbol={code}&from=1577836800&to=1790640000"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            d = r.json()
            cnt = len(d.get('t', []))
            print(f"SSI [{code}]: {cnt} bars")
        else:
            print(f"SSI [{code}]: status {r.status_code}")
    except Exception as e:
        print(f"SSI [{code}] err: {e}")
