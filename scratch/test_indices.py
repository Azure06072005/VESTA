import sys
sys.stdout.reconfigure(encoding='utf-8')
from vnstock_data import Market

mkt = Market()
test_indices = [
    'VNINDEX', 'VN30', 'HNX', 'HNX-INDEX', 'UPCOM', 'VN100', 'VNMID', 
    'VNSML', 'VNDIAMOND', 'VNFINLEAD', 'HNX30', 'VNALL', 'VNX50', 'VNSI'
]

for idx in test_indices:
    try:
        df = mkt.index(idx).ohlcv(start='2024-09-01', end='2024-09-28')
        last_t = str(df['time'].iloc[-1]) if not df.empty else "empty"
        print(f"[{idx}] OK: {len(df)} rows | latest: {last_t}")
    except Exception as e:
        print(f"[{idx}] FAILED: {e}")
