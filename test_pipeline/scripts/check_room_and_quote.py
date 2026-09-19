import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
os.environ['VNSTOCK_API_KEY'] = 'vnstock_f84ed9f3014e77c53a88e3eae1bc1be8'

from vnstock_data import Market, Fundamental, Reference

mkt = Market()
ref = Reference()

print("--- 1. mkt.equity('VCB').price_board() ---")
try:
    pb = mkt.equity('VCB').price_board()
    if hasattr(pb, 'columns'):
        print("Columns:", pb.columns.tolist())
        print(pb.to_string())
    else:
        print(pb)
except Exception as e:
    print("price_board error:", e)

print("\n--- 2. mkt.equity('VCB').quote() ---")
try:
    q = mkt.equity('VCB').quote()
    print(q)
except Exception as e:
    print("quote error:", e)

print("\n--- 3. ref.company('VCB').info() ---")
try:
    info = ref.company('VCB').info()
    if hasattr(info, 'columns'):
        print("Columns:", info.columns.tolist())
        print(info.to_string())
    else:
        print(info)
except Exception as e:
    print("info error:", e)

print("\n--- 4. mkt.equity('VCB').intraday() ---")
try:
    intra = mkt.equity('VCB').intraday()
    if hasattr(intra, 'columns'):
        print("Columns:", intra.columns.tolist())
        print(intra.head(5).to_string())
    else:
        print(intra)
except Exception as e:
    print("intraday error:", e)
