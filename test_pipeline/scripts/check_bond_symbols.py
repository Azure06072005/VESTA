import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
os.environ['VNSTOCK_API_KEY'] = 'vnstock_f84ed9f3014e77c53a88e3eae1bc1be8'

from vnstock_data import Market, Reference

mkt = Market()
ref = Reference()

print("--- 1. Market.bond docstring / signature ---")
import inspect
print("mkt.bond signature:", inspect.signature(mkt.bond))
print("mkt.bond doc:", inspect.getdoc(mkt.bond))

print("\n--- 2. Trying bond with a known symbol ---")
try:
    b = mkt.bond("VN10Y")
    print("b methods:", [m for m in dir(b) if not m.startswith('_')])
    if hasattr(b, 'ohlcv'):
        print(b.ohlcv())
    if hasattr(b, 'quote'):
        print(b.quote())
except Exception as e:
    print("bond VN10Y error:", e)

print("\n--- 3. Market.index symbols ---")
try:
    idx_list = ref.index.list() if hasattr(ref, 'index') and hasattr(ref.index, 'list') else None
    print("idx_list:", idx_list)
except Exception as e:
    print("ref.index error:", e)
